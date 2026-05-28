"""tests/policy/test_intent_confidence.py — classify_intent() confidence scoring tests."""
import pytest
from core.intent_result import Confidence
from core.intent_router import classify_intent


def test_specific_service_query_high_confidence():
    r = classify_intent("Sửa chập điện bao nhiêu?")
    assert r.tool_call_str is not None
    assert "get_services" in r.tool_call_str
    assert r.confidence == Confidence.HIGH


def test_generic_price_query_medium_confidence():
    r = classify_intent("Giá dịch vụ bên bạn thế nào?")
    assert r.confidence == Confidence.MEDIUM
    assert r.ambiguity_reason is not None


def test_bao_gia_medium_confidence():
    r = classify_intent("Bảng giá bên bạn như thế nào?")
    assert r.confidence == Confidence.MEDIUM


def test_machine_cold_high_confidence():
    r = classify_intent("Máy lạnh không mát sửa bao nhiêu?")
    assert r.confidence == Confidence.HIGH
    assert r.tool_call_str is not None
    assert '"máy lạnh"' in r.tool_call_str


def test_groups_query_high_confidence():
    r = classify_intent("Fixago có dịch vụ gì?")
    assert r.confidence == Confidence.HIGH
    assert r.tool_call_str is not None
    assert "get_groups" in r.tool_call_str
    assert "list_services_keyword" in r.matched_signals


def test_confirmation_no_tool():
    r = classify_intent("Xác nhận")
    assert r.tool_call_str is None
    assert r.confidence == Confidence.HIGH


def test_promotions_keyword():
    r = classify_intent("Có khuyến mãi không?")
    assert "get_promotions" in (r.tool_call_str or "")
    assert "promotions_keyword" in r.matched_signals


def test_empty_query_low_confidence():
    r = classify_intent("   ")
    assert r.confidence == Confidence.LOW
    assert r.ambiguity_reason is not None


def test_hong_roi_vague():
    r = classify_intent("Hỏng rồi")
    # vague damage statement — no specific service keyword, no tool
    assert r.tool_call_str is None


def test_nuoc_specific_high():
    r = classify_intent("Ống nước bị rò sửa bao nhiêu?")
    assert r.confidence == Confidence.HIGH
    assert '"nước"' in (r.tool_call_str or "")
