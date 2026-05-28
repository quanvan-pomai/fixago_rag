"""
core/session.py
Session management backed by PomaiCache.
"""
import json
import os

import rag_engine

_mem: dict = {}  # in-memory store for FIXAGO_TEST_MODE


class SessionManager:
    _TTL_MS = 7_200_000  # 2 hours

    @staticmethod
    def get(session_id: str) -> dict:
        if not session_id:
            return {"history": [], "booking_state": {}}
        if os.environ.get("FIXAGO_TEST_MODE") == "1":
            return dict(_mem.get(session_id, {"history": [], "booking_state": {}}))
        try:
            val = rag_engine.cache.get(f"session:{session_id}")
            if val:
                return json.loads(val.decode("utf-8"))
        except Exception as exc:
            print(f"Session load failed: {exc}")
        return {"history": [], "booking_state": {}}

    @staticmethod
    def save(session_id: str, data: dict):
        if not session_id:
            return
        if os.environ.get("FIXAGO_TEST_MODE") == "1":
            _mem[session_id] = data
            return
        try:
            rag_engine.cache.set(
                f"session:{session_id}",
                json.dumps(data).encode("utf-8"),
                ttl_ms=SessionManager._TTL_MS,
            )
        except Exception as exc:
            print(f"Session save failed: {exc}")
