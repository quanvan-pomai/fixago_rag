#!/usr/bin/env python3
"""
server.py
---------
Flask entry point for the Fixago RAG server.
Optimized for ultra-low latency & early cache returns.
"""
import os
import uuid

from dotenv import load_dotenv
from flask import Flask, jsonify, request, send_file

import rag_engine
from core.cache_policy import make_cache_key, should_cache_response
from core.guardrails import guardrail_response, is_prompt_injection
from core.intent_router import detect_user_language
from core.memory.memory_retriever import MemoryRetriever, format_memory_block
from core.memory.memory_store import MemoryStore
from core.memory.memory_writer import get_default_writer
from core.memory.memory_policy import mask_pii
from core.orchestrator import (
    persist_session, run_legacy_fast_path,
    run_legacy_tool_path, run_native_tool_path,
)
from core.policy import PolicyType, ResponsePolicy
from core.prompt_builder import build_system_prompt, compact_history, load_system_prompt
from core.rag_enrichment import rewrite_for_rag
from core.retrieval import should_retrieve_context
from core.session import SessionManager
from core.tracer import RequestTrace, mask_phone, set_current_trace_id
from tools.handlers import (
    fetch_raw_groups, format_groups_for_llm,
    init_cache as _init_tools_cache,
)

load_dotenv()

# Inject shared cache into tools so API responses are cached automatically
_init_tools_cache(rag_engine.cache)
_memory_retriever = MemoryRetriever()
_memory_writer = get_default_writer()

ENABLE_NATIVE_TOOL_CALL = os.environ.get("ENABLE_NATIVE_TOOL_CALL", "1") in ("1", "true", "yes")
print(f"[SERVER INIT] ENABLE_NATIVE_TOOL_CALL={ENABLE_NATIVE_TOOL_CALL}", flush=True)

app = Flask(__name__)


# ── Flask routes ──────────────────────────────────────────────────────────────

@app.route("/", methods=["GET"])
def index():
    return send_file("demo.html")


@app.route("/api/v1/rag/ingest", methods=["POST"])
def ingest():
    data   = request.json or {}
    doc_id = data.get("doc_id")
    text   = data.get("text")
    if doc_id is None or not text:
        return jsonify({"status": "error", "message": "Missing 'doc_id' or 'text'"}), 400
    try:
        rag_engine.ingest_document(int(doc_id), text)
        return jsonify({"status": "success", "message": f"Document {doc_id} ingested successfully"})
    except Exception as exc:
        return jsonify({"status": "error", "message": str(exc)}), 500


@app.route("/api/v1/rag/retrieve", methods=["POST"])
def retrieve():
    data  = request.json or {}
    query = data.get("query")
    top_k = data.get("top_k", 5)
    if not query:
        return jsonify({"status": "error", "message": "Missing 'query'"}), 400
    try:
        context = rag_engine.retrieve_context(rag_engine.normalize_query(query), top_k=int(top_k))
        return jsonify({"status": "success", "context": context})
    except Exception as exc:
        return jsonify({"status": "error", "message": str(exc)}), 500


@app.route("/api/v1/memory/debug", methods=["GET"])
def memory_debug():
    if os.environ.get("FIXAGO_DEBUG") != "1":
        return jsonify({"status": "error", "message": "Not found"}), 404
    expected = os.environ.get("FIXAGO_ADMIN_TOKEN", "")
    if not expected or request.headers.get("X-Admin-Token") != expected:
        return jsonify({"status": "error", "message": "Unauthorized"}), 401

    session_id = request.args.get("session_id")
    user_id = request.args.get("user_id")
    store = MemoryStore()
    entries = store.list(session_id=session_id, user_id=user_id)
    return jsonify({
        "status": "success",
        "entries": [
            {
                "id": e.id,
                "scope": e.scope.value,
                "type": e.type.value,
                "source": e.source,
                "confidence": e.confidence,
                "created_at": e.created_at,
                "updated_at": e.updated_at,
                "expires_at": e.expires_at,
                "tags": e.tags,
                "pii_level": e.pii_level.value,
                "allowed_for_prompt": e.allowed_for_prompt,
                "content_preview": mask_pii(e.content[:160]),
            }
            for e in entries
        ],
    })


@app.route("/api/v1/admin/reload-prompt", methods=["POST"])
def reload_prompt():
    if os.environ.get("FIXAGO_DEBUG") != "1":
        return jsonify({"status": "error", "message": "Not found"}), 404
    expected = os.environ.get("FIXAGO_ADMIN_TOKEN", "")
    if not expected or request.headers.get("X-Admin-Token") != expected:
        return jsonify({"status": "error", "message": "Unauthorized"}), 401
    from core.prompt_builder import reload_system_prompt
    new_prompt = reload_system_prompt()
    return jsonify({"status": "success", "prompt_length": len(new_prompt)})


@app.route("/api/v1/rag/query", methods=["POST"])
def query_rag():
    data       = request.json or {}
    query      = data.get("query")
    use_cache  = data.get("use_cache", False)
    session_id = data.get("session_id")
    user_id    = data.get("user_id")

    if not query:
        return jsonify({"status": "error", "message": "Missing 'query'"}), 400

    trace = RequestTrace()
    trace.query_preview = mask_phone(query[:80])

    if is_prompt_injection(query):
        trace.path = "guardrail"
        trace.emit()
        return jsonify(guardrail_response())

    try:
        # ── Session ──────────────────────────────────────────────────────────
        if not session_id:
            session_id = str(uuid.uuid4())
        trace.session_id = session_id
        set_current_trace_id(trace.trace_id)

        session  = SessionManager.get(session_id)
        client_h = compact_history(data.get("history", []), max_items=5)
        if client_h and not session.get("history"):
            session["history"] = client_h
        history = session.get("history", [])

        # ── OPTIMIZATION 1: Skip Catalog Prefetch for Native Mode ────────────
        if not ENABLE_NATIVE_TOOL_CALL and not session.get("catalog_prefetched"):
            try:
                _grps = fetch_raw_groups()
                if _grps.ok and _grps.data:
                    session["catalog_summary"] = format_groups_for_llm(_grps.data)
                    session["catalog_prefetched"] = True
            except Exception:
                pass

        # ── System prompt ─────────────────────────────────────────────────────
        # detect_tool_intent / classify_intent are stubs (return None / LOW).
        # policy always falls through to GENERAL_FIXAGO_QA — skip the call.
        base_prompt = load_system_prompt()
        _policy     = ResponsePolicy(
            policy_type=PolicyType.GENERAL_FIXAGO_QA,
            should_cache=True,
            retrieve_rag=True,
            temperature=0.2,
        )
        trace.detected_intent   = ""
        trace.intent_confidence = "low"
        trace.policy_type       = _policy.policy_type.value

        _catalog = session.get("catalog_summary", "") if not ENABLE_NATIVE_TOOL_CALL else ""
        system   = build_system_prompt(
            base_prompt, session.get("booking_state", {}),
            ENABLE_NATIVE_TOOL_CALL, None, _catalog,
        )

        # ── OPTIMIZATION 2: Early Cache Check (Before DB calls) ──────────────
        history_text = "\n".join(
            f"{m.get('role')}: {m.get('content', '')}"
            for m in compact_history(history, max_items=5)
        )
        tokens    = []
        cache_key = ""
        _use_cache_this_req = use_cache and should_cache_response(_policy, trace.backend_ok)

        if _use_cache_this_req:
            try:
                # Pass "" to rag_context to look up instantly without waiting for RAG
                cache_key = make_cache_key(system, history_text, "", "", query)
                tokens    = rag_engine.tokenize_text(cache_key)
                cached    = rag_engine.cache.get(cache_key)
                p_res     = rag_engine.cache.prompt_get(tokens) if cached else None
                if cached:
                    trace.path = "cache_hit"
                    trace.cache_hit = True
                    trace.emit()
                    return jsonify({
                        "status": "success",
                        "session_id": session_id,
                        "response": cached.decode("utf-8"),
                        "source": "cache",
                        "tool_calls": [],
                        "cache_metrics": p_res or {
                            "hit": True, "cached_tokens": len(tokens), "savings_ratio": 1.0
                        },
                    })
            except Exception as exc:
                print(f"Cache lookup failed: {exc}")

        # ── Fast path (Legacy Only) ──────────────────────────────────────────
        used_tools: list = []
        if not ENABLE_NATIVE_TOOL_CALL and not use_cache:
            fast_messages = [{"role": "system", "content": system}]
            fast_messages.extend(compact_history(history, max_items=5))
            fast_messages.append({"role": "user", "content": query})
            fast_answer = run_legacy_fast_path(query, history, fast_messages, used_tools)
            if fast_answer is not None:
                persist_session(session_id, session, query, fast_answer)
                trace.path = "static_fallback"
                trace.tools_called = used_tools
                trace.emit()
                return jsonify({
                    "status": "success",
                    "session_id": session_id,
                    "response": fast_answer,
                    "source": "llm",
                    "tool_calls": used_tools,
                    "cache_metrics": {"hit": False, "cached_tokens": 0, "savings_ratio": 0.0},
                })

        # ── Memory Retrieval (Deferred until Cache Miss) ──────────────────────
        memory_result = _memory_retriever.retrieve(
            query=query,
            policy=_policy,
            session_id=session_id,
            user_id=user_id,
        )
        trace.memory_retrieval_enabled = memory_result.enabled
        trace.memory_entries_selected_count = len(memory_result.entries)
        trace.memory_scopes_used = sorted({m.entry.scope.value for m in memory_result.entries})
        trace.memory_token_budget_used = memory_result.token_budget_used
        memory_block = format_memory_block(memory_result.entries)

        # ── RAG context (Deferred until Cache Miss) ───────────────────────────
        rag_context = ""
        _do_rag = should_retrieve_context(
            query,
            tool_name=None,
            booking_state=session.get("booking_state", {}),
        )
        trace.retrieve_context = _do_rag
        if _do_rag:
            try:
                _rewritten  = rewrite_for_rag(query, None)
                rag_context = rag_engine.retrieve_context(
                    rag_engine.normalize_query(_rewritten),
                    top_k=2,
                    max_len=2000,
                )
            except Exception as exc:
                print(f"RAG retrieval failed: {exc}")

        # ── Build LLM messages ────────────────────────────────────────────────
        messages = [{"role": "system", "content": system}]
        messages.extend(compact_history(history, max_items=5))
        
        context_parts = []
        if memory_block:
            context_parts.append(memory_block)
        if rag_context:
            context_parts.append(f"Ngữ cảnh tham khảo:\n{rag_context}")
        
        context_prefix = "\n\n".join(context_parts)
        user_msg_content = f"{context_prefix}\n\nCâu hỏi của khách:\n{query}" if context_prefix else query
        
        messages.append({
            "role": "user",
            "content": user_msg_content.strip(),
        })

        # ── Orchestrate LLM Call ──────────────────────────────────────────────
        answer = (
            run_native_tool_path(query, history, messages, used_tools)
            if ENABLE_NATIVE_TOOL_CALL
            else run_legacy_tool_path(query, history, messages, used_tools)
        )
        trace.path = "native_tool" if ENABLE_NATIVE_TOOL_CALL else "legacy_tool"
        trace.tools_called = used_tools
        trace.llm_called = True

        # ── Persist session & Save Memory ─────────────────────────────────────
        persist_session(session_id, session, query, answer)
        trace.memory_write_count = _memory_writer.update_after_turn(
            query=query,
            response=answer,
            tool_calls=used_tools,
            session=session,
            session_id=session_id,
            user_id=user_id,
            trace_id=trace.trace_id,
        )
        trace.memory_write_rejected_reason = _memory_writer.last_rejected_reason

        # ── Write cache ───────────────────────────────────────────────────────
        if _use_cache_this_req:
            try:
                rag_engine.cache.set(cache_key, answer.encode("utf-8"), ttl_ms=600_000)
                rag_engine.cache.prompt_put(tokens, answer.encode("utf-8"), ttl_ms=600_000)
            except Exception as exc:
                print(f"Cache write failed: {exc}")

        trace.emit()
        return jsonify({
            "status": "success",
            "session_id": session_id,
            "response": answer,
            "source": "llm",
            "tool_calls": used_tools,
            "cache_metrics": {"hit": False, "cached_tokens": 0, "savings_ratio": 0.0},
        })

    except Exception as exc:
        trace.path = trace.path or "error"
        trace.emit()
        return jsonify({"status": "error", "message": f"LLM query failed: {exc}"}), 500

# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    port = int(os.environ.get("RAG_PORT", 8081))
    print(f"Starting RAG server on port {port}...")
    try:
        from waitress import serve
        print(f"Serving on http://0.0.0.0:{port} with Waitress (threads=20)")
        serve(app, host="0.0.0.0", port=port, threads=20)
    except ImportError:
        print("WARNING: Waitress not found. Falling back to Flask dev server.")
        app.run(host="0.0.0.0", port=port, debug=False, threaded=True)