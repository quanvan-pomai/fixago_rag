#!/usr/bin/env python3
"""
server.py
---------
Flask entry point for the Fixago RAG server.
All business logic lives in core/ and dedicated modules:
  core/session.py          — session management
  core/prompt_builder.py   — system prompt, few-shot, history
  core/guardrails.py       — injection detection, static fallbacks
  core/intent_router.py    — tool intent detection
  core/rag_enrichment.py   — query rewriting for RAG
  core/output_validator.py — LLM output validation
  core/query_processor.py  — multi-question splitting, tool data fetching
  core/orchestrator.py     — orchestration paths + session persistence
  booking/                 — booking flow
  tools/handlers.py        — backend API fetch/format
  llm_client/client.py     — LLM calls
  db/                      — vector store + cache
"""
import hashlib
import os
import uuid

from dotenv import load_dotenv
from flask import Flask, jsonify, request, send_file

import rag_engine
from core.guardrails import guardrail_response, is_prompt_injection
from core.intent_router import detect_tool_intent
from core.orchestrator import (
    persist_session, run_legacy_fast_path,
    run_legacy_tool_path, run_native_tool_path,
)
from core.prompt_builder import build_system_prompt, compact_history, load_system_prompt
from core.rag_enrichment import rewrite_for_rag
from core.session import SessionManager
from tools.handlers import (
    fetch_raw_groups, format_groups_for_llm,
    init_cache as _init_tools_cache,
)

load_dotenv()

# Inject shared cache into tools so API responses are cached automatically
_init_tools_cache(rag_engine.cache)

# Set ENABLE_NATIVE_TOOL_CALL=1 when cheese-server is started with --jinja.
ENABLE_NATIVE_TOOL_CALL = os.environ.get("ENABLE_NATIVE_TOOL_CALL", "0") in ("1", "true", "yes")

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


@app.route("/api/v1/rag/query", methods=["POST"])
def query_rag():
    data       = request.json or {}
    query      = data.get("query")
    use_cache  = data.get("use_cache", False)
    session_id = data.get("session_id")

    if not query:
        return jsonify({"status": "error", "message": "Missing 'query'"}), 400

    if is_prompt_injection(query):
        return jsonify(guardrail_response())

    try:
        # ── Session ──────────────────────────────────────────────────────────
        if not session_id:
            session_id = str(uuid.uuid4())

        session  = SessionManager.get(session_id)
        client_h = compact_history(data.get("history", []))
        if client_h and not session.get("history"):
            session["history"] = client_h
        history = session.get("history", [])

        # ── Prefetch service catalog once per session ─────────────────────────
        if not session.get("catalog_prefetched"):
            try:
                _grps = fetch_raw_groups()
                if _grps.ok and _grps.data:
                    session["catalog_summary"] = format_groups_for_llm(_grps.data)
                    session["catalog_prefetched"] = True
            except Exception:
                pass

        # ── System prompt ─────────────────────────────────────────────────────
        base_prompt   = load_system_prompt()
        _early_intent = detect_tool_intent(query)
        _catalog      = session.get("catalog_summary", "")
        system        = build_system_prompt(
            base_prompt, session.get("booking_state", {}),
            ENABLE_NATIVE_TOOL_CALL, _early_intent, _catalog,
        )

        # ── Fast path ─────────────────────────────────────────────────────────
        used_tools: list = []
        if not ENABLE_NATIVE_TOOL_CALL and not use_cache:
            fast_messages = [{"role": "system", "content": system}]
            fast_messages.extend(compact_history(history, max_items=6))
            fast_messages.append({"role": "user", "content": query})
            fast_answer = run_legacy_fast_path(query, history, fast_messages, used_tools)
            if fast_answer is not None:
                persist_session(session_id, session, query, fast_answer)
                return jsonify({
                    "status": "success",
                    "session_id": session_id,
                    "response": fast_answer,
                    "source": "llm",
                    "tool_calls": used_tools,
                    "cache_metrics": {"hit": False, "cached_tokens": 0, "savings_ratio": 0.0},
                })

        # ── RAG context ───────────────────────────────────────────────────────
        rag_context = ""
        _skip_rag   = bool(_early_intent and "get_services" in _early_intent)
        if not _skip_rag:
            try:
                _rewritten  = rewrite_for_rag(query, _early_intent)
                rag_context = rag_engine.retrieve_context(
                    rag_engine.normalize_query(_rewritten),
                    top_k=2,
                    max_len=2000,
                )
            except Exception as exc:
                print(f"RAG retrieval failed: {exc}")

        # ── Cache key ─────────────────────────────────────────────────────────
        history_text = "\n".join(
            f"{m.get('role')}: {m.get('content', '')}"
            for m in compact_history(history)
        )
        cache_seed = f"System:{system}\nHistory:{history_text}\nContext:{rag_context}\nQ:{query}"
        tokens     = []
        cache_key  = ""

        if use_cache:
            try:
                tokens    = rag_engine.tokenize_text(cache_seed)
                cache_key = f"pomai_cache:response:{hashlib.sha256(cache_seed.encode()).hexdigest()}"
                cached = rag_engine.cache.get(cache_key)
                p_res  = rag_engine.cache.prompt_get(tokens) if cached else None
                if cached:
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

        # ── Build messages ────────────────────────────────────────────────────
        messages = [{"role": "system", "content": system}]
        messages.extend(compact_history(history, max_items=6))
        messages.append({
            "role": "user",
            "content": (
                f"Ngữ cảnh tham khảo:\n{rag_context}\n\nCâu hỏi của khách:\n{query}"
                if rag_context else query
            ),
        })

        # ── Orchestrate ───────────────────────────────────────────────────────
        answer = (
            run_native_tool_path(query, history, messages, used_tools)
            if ENABLE_NATIVE_TOOL_CALL
            else run_legacy_tool_path(query, history, messages, used_tools)
        )

        # ── Persist session ───────────────────────────────────────────────────
        persist_session(session_id, session, query, answer)

        # ── Write cache ───────────────────────────────────────────────────────
        if use_cache:
            try:
                if not cache_key:
                    tokens    = rag_engine.tokenize_text(cache_seed)
                    cache_key = f"pomai_cache:response:{hashlib.sha256(cache_seed.encode()).hexdigest()}"
                rag_engine.cache.set(cache_key, answer.encode("utf-8"), ttl_ms=600_000)
                rag_engine.cache.prompt_put(tokens, answer.encode("utf-8"), ttl_ms=600_000)
            except Exception as exc:
                print(f"Cache write failed: {exc}")

        return jsonify({
            "status": "success",
            "session_id": session_id,
            "response": answer,
            "source": "llm",
            "tool_calls": used_tools,
            "cache_metrics": {"hit": False, "cached_tokens": 0, "savings_ratio": 0.0},
        })

    except Exception as exc:
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
