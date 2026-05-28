"""Unit tests for core/intent_router.py — no external deps."""
import os
os.environ.setdefault("FIXAGO_TEST_MODE", "1")

import pytest
from core.intent_router import detect_tool_intent, is_hours_question, normalize_noaccent


# ── Service taxonomy ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("query,expected_svc", [
    ("máy lạnh bị hỏng",          "máy lạnh"),
    ("điều hòa không lạnh giá sao", "máy lạnh"),
    ("may lanh khong lanh",         "máy lạnh"),   # no-accent
    ("Ống nước bị rò rỉ giá bao nhiêu", "nước"),
    ("chống thấm tường nhà giá sao",    "xây dựng"),
    ("tường bị thấm nước xử lý sao",    "xây dựng"),  # must NOT be "nước"
    ("sửa ổ cắm điện bao nhiêu",        "điện"),
    ("chập điện giá bao nhiêu",          "điện"),
    ("thạch cao trần nhà bao nhiêu",     "thạch cao"),
    ("vách ngăn thạch cao giá sao",      "thạch cao"),
    ("sửa máy giặt giá bao nhiêu",       "máy lạnh"),  # máy giặt → máy lạnh category
])
def test_service_routing(query, expected_svc):
    result = detect_tool_intent(query)
    assert result is not None, f"Expected tool call for: {query!r}"
    assert f'search="{expected_svc}"' in result, (
        f"Expected search={expected_svc!r} in {result!r} for query {query!r}"
    )


def test_tường_thấm_not_nước():
    """'Tường bị thấm nước' must route to xây dựng, not nước."""
    result = detect_tool_intent("Tường bị thấm nước xử lý sao?")
    assert result is not None
    assert '"nước"' not in result
    assert '"xây dựng"' in result


def test_may_lanh_not_nuoc():
    """'Máy lạnh nhỏ giọt nước' must route to máy lạnh, not nước."""
    result = detect_tool_intent("Máy lạnh nhỏ giọt nước sửa bao nhiêu?")
    assert result is not None
    assert '"nước"' not in result
    assert '"máy lạnh"' in result


@pytest.mark.parametrize("query", [
    "fixago co ban nuoc mia khong?",
    "có bán nước mía không",
    "bên bạn có bán đồ uống không",
])
def test_product_sales_not_routed_to_water_service(query):
    result = detect_tool_intent(query)
    assert result is None


# ── Group pattern ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("query", [
    "Fixago có dịch vụ gì?",
    "bên bạn làm gì",
    "có sửa gì không",
    "What services do you offer?",
    "what can fixago do",
])
def test_group_pattern(query):
    result = detect_tool_intent(query)
    assert result == "CALL_TOOL: get_groups()", f"got {result!r} for {query!r}"


# ── Promotions ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("query", [
    "Có khuyến mãi không?",
    "hôm nay có ưu đãi gì không",
    "cho tôi mã giảm giá",
    "Do you have any discount?",
])
def test_promotion_pattern(query):
    result = detect_tool_intent(query)
    assert result == "CALL_TOOL: get_promotions()", f"got {result!r} for {query!r}"


# ── Hours ─────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("text,expected", [
    ("giờ làm việc bên bạn thế nào", True),
    ("working hours", True),
    ("mấy giờ mở cửa", True),
    ("Fixago hoạt động 24/7 không", True),
    ("sửa điện bao nhiêu", False),
])
def test_is_hours_question(text, expected):
    assert is_hours_question(text) == expected


# ── No tool for booking confirmation ─────────────────────────────────────────

@pytest.mark.parametrize("query", [
    "Xác nhận",
    "ok đặt đi",
    "chốt",
])
def test_no_tool_for_confirmation(query):
    # Confirmation words alone should not trigger a tool call
    result = detect_tool_intent(query)
    # May be None or None — booking flow handles these, not tool intent
    # We just assert it's not a service lookup
    assert result is None or "get_services" not in result


# ── normalize_noaccent ────────────────────────────────────────────────────────

def test_normalize_may_lanh():
    assert "máy lạnh" in normalize_noaccent("may lanh")

def test_normalize_dien():
    assert "điện" in normalize_noaccent("dien")
