"""Pomai Memory store tests."""
from core.memory.memory_policy import BUSINESS_TTL_MS, now_ms
from core.memory.memory_store import MemoryStore
from core.memory.memory_types import MemoryEntry, MemoryScope, MemoryType, PIILevel


class TinyCache:
    def __init__(self):
        self.data = {}

    def get(self, key):
        return self.data.get(key)

    def set(self, key, value, ttl_ms=0):
        self.data[key] = value if isinstance(value, bytes) else str(value).encode()
        return True


def _entry(entry_id="m1", scope=MemoryScope.BUSINESS, content="Fixago fact"):
    ts = now_ms()
    return MemoryEntry(
        id=entry_id,
        scope=scope,
        type=MemoryType.FACT,
        content=content,
        normalized_content=content.lower(),
        source="test",
        confidence=0.9,
        created_at=ts,
        updated_at=ts,
        expires_at=ts + BUSINESS_TTL_MS,
        ttl_ms=BUSINESS_TTL_MS,
        tags=["business"],
        pii_level=PIILevel.NONE,
        allowed_for_prompt=True,
    )


def test_put_get_and_list_by_scope():
    store = MemoryStore(cache=TinyCache())
    store.put(_entry())
    found = store.get("m1")
    listed = store.list(scopes=[MemoryScope.BUSINESS])
    assert found is not None
    assert found.content == "Fixago fact"
    assert [e.id for e in listed] == ["m1"]


def test_expired_entry_filtered():
    store = MemoryStore(cache=TinyCache())
    e = _entry()
    e.expires_at = now_ms() - 1
    store.put(e)
    assert store.get("m1") is None
    assert store.list(scopes=[MemoryScope.BUSINESS]) == []


def test_upsert_by_hash_updates_existing_id():
    store = MemoryStore(cache=TinyCache())
    e1 = _entry("a")
    e1.data_hash = "same"
    e2 = _entry("b", content="Updated")
    e2.data_hash = "same"
    store.upsert_by_hash(e1)
    saved = store.upsert_by_hash(e2)
    assert saved.id == "a"
    assert store.get("a").content == "Updated"

