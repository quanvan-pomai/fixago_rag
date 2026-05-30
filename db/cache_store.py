"""
db/cache_store.py
-----------------
PomaiCache wrapper: key-value cache and prompt-token cache.
Handles tokenization via the cheesebrain /tokenize endpoint.
"""
import logging
import os
from pathlib import Path
from typing import Any, List, Optional

import requests

logger = logging.getLogger("fixago.cache_store")

# ── Paths & config ───────────────────────────────────────────────────────────

workspace_dir     = Path(os.environ.get("RAG_WORKSPACE_DIR", Path(__file__).resolve().parent.parent)).resolve()
data_dir          = Path(os.environ.get("RAG_DATA_DIR",      workspace_dir / "data")).resolve()
pomaicache_dir    = Path(os.environ.get("POMAICACHE_DIR",    data_dir / "pomaicache")).resolve()
pomaicache_build_dir = Path(os.environ.get("POMAICACHE_BUILD_DIR", workspace_dir / "pomaicache" / "build")).resolve()

RAG_CACHE_MEMORY_LIMIT_BYTES = int(os.environ.get("RAG_CACHE_MEMORY_LIMIT_BYTES", str(128 * 1024 * 1024)))
RAG_TOKENIZER_URL            = os.environ.get("RAG_TOKENIZER_URL",     "http://127.0.0.1:8080/tokenize")
RAG_TOKENIZER_TIMEOUT        = float(os.environ.get("RAG_TOKENIZER_TIMEOUT", "10"))


class CacheStore:
    """Wraps PomaiCache for key-value and prompt-token caching."""

    def __init__(self, lock):
        import sys
        sys.path.insert(0, str(pomaicache_build_dir))

        try:
            import pomaicache as _pomaicache
        except Exception as exc:
            logger.warning(f"Cannot import pomaicache from {pomaicache_build_dir}: {exc}")
            _pomaicache = None

        pomaicache_dir.mkdir(parents=True, exist_ok=True)

        self._cache = None
        self._kv_fallback: dict[str, tuple[bytes, float | None]] = {}

        self._has_native_kv = False
        if _pomaicache and hasattr(_pomaicache, "Cache"):
            try:
                self._cache = _pomaicache.Cache(
                    data_dir=str(pomaicache_dir),
                    memory_limit_bytes=RAG_CACHE_MEMORY_LIMIT_BYTES,
                )
                self._has_native_kv = hasattr(self._cache, "get") and hasattr(self._cache, "set")
                if not self._has_native_kv:
                    logger.warning(
                        "PomaiCache binding has no key-value get/set API; using process-local KV fallback. "
                        "Rebuild pomaicache to enable native persistent session/memory cache."
                    )
            except Exception as exc:
                logger.warning(f"Failed to initialize PomaiCache: {exc}. Using in-memory fallback.")
                self._cache = None
                self._has_native_kv = False
        else:
            logger.info("PomaiCache not available; using in-memory KV fallback.")
            self._has_native_kv = False

        self._lock = lock
        logger.info("Cache initialized (native=%s) at %s", self._has_native_kv, pomaicache_dir)

    # ── Key-value cache ──────────────────────────────────────────────────────

    def get(self, key: str) -> Optional[bytes]:
        if not key:
            return None
        with self._lock:
            if not self._has_native_kv:
                return self._fallback_get(key)
            return self._cache.get(key)

    def set(self, key: str, value: bytes, ttl_ms: int = 600_000) -> bool:
        if not key:
            return False
        if not isinstance(value, bytes):
            value = str(value).encode("utf-8")
        with self._lock:
            if not self._has_native_kv:
                self._fallback_set(key, value, ttl_ms)
                return True
            self._cache.set(key, value, ttl_ms=ttl_ms)
        return True

    def _fallback_get(self, key: str) -> Optional[bytes]:
        import time

        item = self._kv_fallback.get(key)
        if not item:
            return None
        value, expires_at = item
        if expires_at is not None and expires_at <= time.time():
            self._kv_fallback.pop(key, None)
            return None
        return value

    def _fallback_set(self, key: str, value: bytes, ttl_ms: int = 600_000) -> None:
        import time

        expires_at = None if ttl_ms == 0 else time.time() + (ttl_ms / 1000.0)
        self._kv_fallback[key] = (value, expires_at)

    # ── Prompt-token cache ───────────────────────────────────────────────────

    def prompt_get(self, tokens: List[int]) -> Any:
        if not tokens:
            return None
        with self._lock:
            return self._cache.prompt_get(tokens)

    def prompt_put(self, tokens: List[int], value: bytes, ttl_ms: int = 600_000) -> bool:
        if not tokens:
            return False
        if not isinstance(value, bytes):
            value = str(value).encode("utf-8")
        with self._lock:
            self._cache.prompt_put(tokens, value, ttl_ms=ttl_ms)
        return True

    # ── Tokenization ─────────────────────────────────────────────────────────

    def tokenize(self, text: Any) -> List[int]:
        """Tokenize text via cheesebrain /tokenize; fallback to UTF-8 bytes."""
        safe = str(text or "").strip()
        if not safe:
            return []
        try:
            resp = requests.post(
                RAG_TOKENIZER_URL,
                json={"content": safe},
                timeout=RAG_TOKENIZER_TIMEOUT,
            )
            if resp.status_code == 200:
                tokens = resp.json().get("tokens", [])
                if isinstance(tokens, list):
                    clean = [int(t) for t in tokens if isinstance(t, (int, float))]
                    if clean:
                        return clean
        except Exception as exc:
            logger.warning("Tokenizer request failed: %s", exc)
        return list(safe.encode("utf-8"))


class FakeCacheStore:
    """In-memory drop-in replacement for CacheStore used in FIXAGO_TEST_MODE."""

    def __init__(self):
        self._store: dict = {}

    def get(self, key: str) -> Optional[bytes]:
        return self._store.get(key)

    def set(self, key: str, value: bytes, ttl_ms: int = 0) -> bool:
        self._store[key] = value if isinstance(value, bytes) else str(value).encode()
        return True

    def prompt_get(self, tokens: List[int]) -> Any:
        return None

    def prompt_put(self, tokens: List[int], value: bytes, ttl_ms: int = 0) -> bool:
        return True

    def tokenize(self, text: Any) -> List[int]:
        return []
