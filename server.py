#!/usr/bin/env python3
"""
server.py - Simplified RAG server for experiment branch

Pure LLM-driven flow:
- No keyword checks, no deterministic guardrails
- Everything controlled by system_prompt
- Data-only caching (API responses cached, not LLM responses)
- LLM decides tool calling, gets cached data, responds based on data
"""
import os
import uuid
import logging

from dotenv import load_dotenv
from flask import Flask, jsonify, request, send_file

import rag_engine
from core.orchestrator_simple import run_pure_llm_path
from core.prompt_builder import load_system_prompt
from core.session import SessionManager
from core.tracer import RequestTrace, set_current_trace_id
from tools.handlers import init_cache as _init_tools_cache

load_dotenv()

# Setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_init_tools_cache(rag_engine.cache)
_session_mgr = SessionManager()

app = Flask(__name__)
RAG_PORT = int(os.environ.get("RAG_PORT", 8081))


# ── Routes ──────────────────────────────────────────────────────────────────────

@app.route("/", methods=["GET"])
def index():
    return send_file("demo.html")


@app.route("/api/v1/rag/query", methods=["POST"])
def rag_query():
    """
    Main RAG query endpoint.

    Request body:
    {
        "query": "user message",
        "history": [...previous turns...],
        "use_cache": false
    }

    Response:
    {
        "status": "success",
        "response": "assistant response",
        "source": "llm",
        "tool_calls": [...tools called...],
        "session_id": "..."
    }
    """
    data = request.json or {}
    query = data.get("query", "").strip()
    history = data.get("history", [])
    session_id = data.get("session_id") or str(uuid.uuid4())

    if not query:
        return jsonify({"status": "error", "message": "Missing 'query'"}), 400

    # Setup tracing
    trace_id = str(uuid.uuid4())
    set_current_trace_id(trace_id)
    trace = RequestTrace(trace_id=trace_id, session_id=session_id)

    try:
        # Load system prompt
        system_prompt = load_system_prompt()

        # Run pure LLM path with tool calling
        result = run_pure_llm_path(
            query=query,
            history=history,
            system_prompt=system_prompt,
            session_id=session_id,
            trace=trace,
        )

        return jsonify({
            **result,
            "cache_metrics": {"hit": False, "cached_tokens": 0, "savings_ratio": 0.0}
        })

    except Exception as exc:
        logger.exception(f"Query error: {exc}")
        return jsonify({
            "status": "error",
            "message": str(exc),
            "session_id": session_id
        }), 500


@app.route("/api/v1/rag/ingest", methods=["POST"])
def ingest():
    """Ingest document into RAG vector database."""
    data = request.json or {}
    doc_id = data.get("doc_id")
    text = data.get("text")

    if doc_id is None or not text:
        return jsonify({"status": "error", "message": "Missing 'doc_id' or 'text'"}), 400

    try:
        rag_engine.ingest_document(int(doc_id), text)
        return jsonify({"status": "success", "message": f"Document {doc_id} ingested"})
    except Exception as exc:
        return jsonify({"status": "error", "message": str(exc)}), 500


@app.route("/api/v1/rag/retrieve", methods=["POST"])
def retrieve():
    """Retrieve RAG context for a query."""
    data = request.json or {}
    query = data.get("query")
    top_k = data.get("top_k", 5)

    if not query:
        return jsonify({"status": "error", "message": "Missing 'query'"}), 400

    try:
        context = rag_engine.retrieve_context(
            rag_engine.normalize_query(query),
            top_k=int(top_k)
        )
        return jsonify({"status": "success", "context": context})
    except Exception as exc:
        return jsonify({"status": "error", "message": str(exc)}), 500


@app.route("/health", methods=["GET"])
def health():
    """Health check endpoint."""
    return jsonify({"status": "ok"}), 200


# ── Error handlers ──────────────────────────────────────────────────────────────

@app.errorhandler(404)
def not_found(e):
    return jsonify({"status": "error", "message": "Not found"}), 404


@app.errorhandler(500)
def internal_error(e):
    return jsonify({"status": "error", "message": "Internal server error"}), 500


# ── Main ────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logger.info(f"Starting RAG server on port {RAG_PORT}")
    app.run(host="127.0.0.1", port=RAG_PORT, debug=False, threaded=True)
