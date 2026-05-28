"""
core.memory.memory_store
PomaiCache-backed MemoryEntry store with small index keys.
"""
from __future__ import annotations

import json
from typing import Iterable, List, Optional

import rag_engine

from .memory_policy import now_ms
from .memory_types import MemoryEntry, MemoryScope


class MemoryStore:
    def __init__(self, cache=None):
        self.cache = cache or rag_engine.cache

    def put(self, entry: MemoryEntry) -> MemoryEntry:
        key = self._entry_key(entry.id)
        self.cache.set(key, json.dumps(entry.to_dict(), ensure_ascii=False).encode("utf-8"), ttl_ms=entry.ttl_ms or 0)
        for index in self._indexes(entry):
            ids = set(self._load_index(index))
            ids.add(entry.id)
            self._save_index(index, sorted(ids))
        return entry

    def get(self, entry_id: str) -> Optional[MemoryEntry]:
        raw = self.cache.get(self._entry_key(entry_id))
        if not raw:
            return None
        try:
            entry = MemoryEntry.from_dict(json.loads(raw.decode("utf-8")))
        except Exception:
            return None
        return None if self._expired(entry) else entry

    def list(
        self,
        *,
        scopes: Optional[Iterable[MemoryScope]] = None,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
        tags: Optional[Iterable[str]] = None,
    ) -> List[MemoryEntry]:
        scope_ids = set()
        for scope in scopes or list(MemoryScope):
            scope_ids |= set(self._load_index(self._scope_index(scope)))

        filter_indexes: List[str] = []
        if session_id:
            filter_indexes.append(f"memory:index:session_id:{session_id}")
        if user_id:
            filter_indexes.append(f"memory:index:user_id:{user_id}")
        for tag in tags or []:
            filter_indexes.append(f"memory:index:tag:{tag}")

        ids = scope_ids
        for index in filter_indexes:
            current = set(self._load_index(index))
            ids &= current

        entries = []
        for entry_id in ids:
            entry = self.get(entry_id)
            if entry:
                entries.append(entry)
        entries.sort(key=lambda e: e.updated_at, reverse=True)
        return entries

    def upsert_by_hash(self, entry: MemoryEntry) -> MemoryEntry:
        if entry.data_hash:
            matches = [e for e in self.list(scopes=[entry.scope], session_id=entry.session_id, user_id=entry.user_id) if e.data_hash == entry.data_hash]
            if matches:
                existing = matches[0]
                entry.id = existing.id
                entry.created_at = existing.created_at
        return self.put(entry)

    @staticmethod
    def _entry_key(entry_id: str) -> str:
        return f"memory:entry:{entry_id}"

    @staticmethod
    def _scope_index(scope: MemoryScope) -> str:
        return f"memory:index:scope:{scope.value}"

    def _indexes(self, entry: MemoryEntry) -> List[str]:
        indexes = [self._scope_index(entry.scope)]
        if entry.session_id:
            indexes.append(f"memory:index:session_id:{entry.session_id}")
        if entry.user_id:
            indexes.append(f"memory:index:user_id:{entry.user_id}")
        for tag in entry.tags:
            indexes.append(f"memory:index:tag:{tag}")
        return indexes

    def _load_index(self, key: str) -> List[str]:
        raw = self.cache.get(key)
        if not raw:
            return []
        try:
            return list(json.loads(raw.decode("utf-8")))
        except Exception:
            return []

    def _save_index(self, key: str, ids: List[str]) -> None:
        self.cache.set(key, json.dumps(ids).encode("utf-8"), ttl_ms=365 * 24 * 60 * 60 * 1000)

    @staticmethod
    def _expired(entry: MemoryEntry) -> bool:
        return bool(entry.expires_at and entry.expires_at <= now_ms())
