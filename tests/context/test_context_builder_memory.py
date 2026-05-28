"""ContextBuilder memory injection tests."""
from core.context_builder import ContextBuilder
from core.memory.memory_policy import USER_PREF_TTL_MS, now_ms
from core.memory.memory_types import MemoryEntry, MemoryScope, MemoryType, PIILevel, ScoredMemoryEntry
from core.policy import PolicyType, ResponsePolicy


def _scored(content, score=1.0):
    ts = now_ms()
    entry = MemoryEntry(
        id="m1",
        scope=MemoryScope.USER,
        type=MemoryType.PREFERENCE,
        content=content,
        normalized_content=content.lower(),
        source="test",
        confidence=0.9,
        created_at=ts,
        updated_at=ts,
        expires_at=ts + USER_PREF_TTL_MS,
        ttl_ms=USER_PREF_TTL_MS,
        tags=["style"],
        pii_level=PIILevel.NONE,
        allowed_for_prompt=True,
    )
    return ScoredMemoryEntry(entry=entry, score=score, reason="test")


def test_memory_injected_after_data_before_rag():
    ctx = ContextBuilder().build(
        query="q",
        history=[],
        data_block="tool_data",
        rag_context="rag_data",
        policy=ResponsePolicy(policy_type=PolicyType.GENERAL_FIXAGO_QA),
        memory_entries=[_scored("User prefers concise answers.")],
    )
    content = ctx.messages[-1]["content"]
    assert content.index("tool_data") < content.index("NGỮ CẢNH BỘ NHỚ") < content.index("rag_data")


def test_no_memory_block_when_empty():
    ctx = ContextBuilder().build(
        query="q",
        history=[],
        data_block=None,
        rag_context=None,
        policy=ResponsePolicy(policy_type=PolicyType.GENERAL_FIXAGO_QA),
        memory_entries=[],
    )
    assert "NGỮ CẢNH BỘ NHỚ" not in ctx.messages[-1]["content"]

