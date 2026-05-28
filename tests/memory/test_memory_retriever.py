"""Pomai Memory retrieval ranking tests."""
from core.memory.memory_policy import PROJECT_TTL_MS, now_ms
from core.memory.memory_retriever import MemoryRetriever
from core.memory.memory_store import MemoryStore
from core.memory.memory_types import MemoryEntry, MemoryScope, MemoryType, PIILevel
from core.policy import PolicyType, ResponsePolicy


class TinyCache:
    def __init__(self):
        self.data = {}

    def get(self, key):
        return self.data.get(key)

    def set(self, key, value, ttl_ms=0):
        self.data[key] = value if isinstance(value, bytes) else str(value).encode()
        return True


def _entry(entry_id, content, scope=MemoryScope.SEMANTIC, tags=None):
    ts = now_ms()
    return MemoryEntry(
        id=entry_id,
        scope=scope,
        type=MemoryType.DECISION,
        content=content,
        normalized_content=content.lower(),
        source="test",
        confidence=0.9,
        created_at=ts,
        updated_at=ts,
        expires_at=ts + PROJECT_TTL_MS,
        ttl_ms=PROJECT_TTL_MS,
        tags=tags or ["project", "decision"],
        pii_level=PIILevel.NONE,
        allowed_for_prompt=True,
    )


def test_retrieve_project_decision():
    store = MemoryStore(cache=TinyCache())
    store.put(_entry("m1", "Current project decision: TensorFlow is native core of dm; DM_Block is optional."))
    retriever = MemoryRetriever(store=store)
    result = retriever.retrieve(
        query="DM_Block có bắt buộc không?",
        policy=ResponsePolicy(policy_type=PolicyType.GENERAL_FIXAGO_QA),
    )
    assert result.enabled is True
    assert result.entries
    assert "DM_Block is optional" in result.entries[0].entry.content


def test_context_budget_limits_entries():
    store = MemoryStore(cache=TinyCache())
    for i in range(10):
        store.put(_entry(f"m{i}", f"Decision {i}: DM_Block detail {i}."))
    result = MemoryRetriever(store=store).retrieve(
        query="DM_Block",
        policy=ResponsePolicy(policy_type=PolicyType.GENERAL_FIXAGO_QA),
        max_entries=3,
        max_tokens=100,
    )
    assert len(result.entries) <= 3


def test_high_pii_not_injected():
    store = MemoryStore(cache=TinyCache())
    e = _entry("pii", "Phone 0901234567")
    e.pii_level = PIILevel.HIGH
    store.put(e)
    result = MemoryRetriever(store=store).retrieve(
        query="phone",
        policy=ResponsePolicy(policy_type=PolicyType.GENERAL_FIXAGO_QA),
    )
    assert result.entries == []


def test_booking_retrieval_does_not_pull_global_project_memory():
    store = MemoryStore(cache=TinyCache())
    store.put(_entry("global", "Global project decision: DM_Block is optional."))
    session_summary = _entry("session-summary", "Session summary: user is booking a water repair.")
    session_summary.session_id = "s1"
    session_summary.type = MemoryType.SUMMARY
    store.put(session_summary)

    result = MemoryRetriever(store=store).retrieve(
        query="Đặt thợ sửa nước",
        policy=ResponsePolicy(policy_type=PolicyType.BOOKING_START),
        session_id="s1",
    )
    contents = [item.entry.content for item in result.entries]
    assert any("booking a water repair" in c for c in contents)
    assert all("DM_Block" not in c for c in contents)
