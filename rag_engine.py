"""
rag_engine.py
-------------
Public facade for the RAG subsystem.

Imports are kept stable so any code that does `import rag_engine` continues
to work without changes. The real implementation lives in:
  db/pomaidb_store.py  — vector store (ingest / retrieve / normalize)
  db/cache_store.py    — key-value + prompt-token cache + tokenizer
"""
import logging
import os
import threading

from db.pomaidb_store import PomaiDBStore, FakePomaiDBStore, normalize_query, strip_vietnamese_accents
from db.cache_store import CacheStore, FakeCacheStore

logging.basicConfig(
    level=os.environ.get("RAG_LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)

# Shared re-entrant lock — both stores use the same lock so no cross-store races
rag_lock = threading.RLock()

# In test mode skip native extensions entirely
if os.environ.get("FIXAGO_TEST_MODE") == "1":
    _store = FakePomaiDBStore()
    _cache = FakeCacheStore()
else:
    _store = PomaiDBStore(lock=rag_lock)
    _cache = CacheStore(lock=rag_lock)
    _store.seed()

# ── Re-export the cache object so server.py can do `rag_engine.cache.get(...)` ──
cache = _cache


# ── Public API ────────────────────────────────────────────────────────────────

def ingest_document(doc_id, text):
    return _store.ingest(doc_id, text)


def retrieve_context(query, top_k=5, max_len=65536):
    return _store.retrieve(query, top_k=top_k, max_len=max_len)


def tokenize_text(text):
    return _cache.tokenize(text)


def healthcheck():
    status = {"ok": True}
    try:
        result = retrieve_context("Fixago", top_k=1)
        status["retrieve_ok"] = isinstance(result, str)
    except Exception as exc:
        status["ok"] = False
        status["retrieve_ok"] = False
        status["error"] = str(exc)
    return status
