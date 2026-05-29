"""
tests/policy/test_intent_confidence.py — classify_intent() tests.

Phase 7: classify_intent() is a stub returning LOW confidence + no tool.
Service routing is delegated to the LLM via native tool calling.
Tests updated to reflect the new semantic architecture.
"""
import pytest
from core.intent_result import Confidence, IntentResult
from core.intent_router import classify_intent


def test_classify_intent_returns_intent_result():
    """classify_intent() always returns an IntentResult."""
    r = classify_intent("Sửa chập điện bao nhiêu?")
    assert isinstance(r, IntentResult)


def test_classify_intent_no_tool_stub():
    """Phase 7: stub returns no tool — LLM handles routing semantically."""
    r = classify_intent("Sửa chập điện bao nhiêu?")
    assert r.tool_call_str is None


def test_classify_intent_semantic_routing_reason():
    """ambiguity_reason indicates semantic routing is active."""
    r = classify_intent("Máy lạnh không mát sửa bao nhiêu?")
    assert r.ambiguity_reason == "semantic_routing_by_llm"


def test_classify_intent_confidence_low():
    """Stub confidence is LOW — policy engine defaults to GENERAL_FIXAGO_QA."""
    r = classify_intent("Fixago có dịch vụ gì?")
    assert r.confidence == Confidence.LOW


def test_classify_intent_empty_query():
    r = classify_intent("   ")
    assert r.tool_call_str is None
    assert r.confidence == Confidence.LOW


def test_classify_intent_various_queries_all_stub():
    """Multiple queries — all return None tool (routing by LLM)."""
    queries = [
        "Ống nước bị rò sửa bao nhiêu?",
        "Có khuyến mãi không?",
        "Hỏng rồi",
        "Xác nhận",
        "Fixago có dịch vụ gì?",
    ]
    for q in queries:
        r = classify_intent(q)
        assert r.tool_call_str is None, f"Expected None tool for {q!r}, got {r.tool_call_str!r}"
