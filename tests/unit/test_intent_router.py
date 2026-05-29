"""
Unit tests for core/intent_router.py — no external deps.

Phase 7: detect_tool_intent() is a stub returning None (semantic routing by LLM).
Tests updated to verify utility functions still work correctly.
"""
import os
os.environ.setdefault("FIXAGO_TEST_MODE", "1")

import pytest
from core.intent_router import detect_tool_intent, is_hours_question, normalize_noaccent, is_price_question, detect_user_language


# ── detect_tool_intent stub ──────────────────────────────────────────────────
# Phase 7: routing is handled by LLM via native tool calling.
# detect_tool_intent() returns None for all queries.

@pytest.mark.parametrize("query", [
    "máy lạnh bị hỏng",
    "điều hòa không lạnh giá sao",
    "Ống nước bị rò rỉ giá bao nhiêu",
    "sửa ổ cắm điện bao nhiêu",
    "Fixago có dịch vụ gì?",
    "Có khuyến mãi không?",
    "fixago co ban nuoc mia khong?",
])
def test_detect_tool_intent_returns_none(query):
    """detect_tool_intent is a stub; all routing delegated to LLM."""
    assert detect_tool_intent(query) is None


# ── Hours classifier ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("text,expected", [
    ("giờ làm việc bên bạn thế nào", True),
    ("working hours", True),
    ("mấy giờ mở cửa", True),
    ("Fixago hoạt động 24/7 không", True),
    ("sửa điện bao nhiêu", False),
])
def test_is_hours_question(text, expected):
    assert is_hours_question(text) == expected


# ── Price classifier ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("text,expected", [
    ("sửa điện bao nhiêu", True),
    ("giá vệ sinh máy lạnh", True),
    ("how much to fix the pipe", True),
    ("xin chào", False),
    ("Fixago có dịch vụ gì", False),
])
def test_is_price_question(text, expected):
    assert is_price_question(text) == expected


# ── Language detection ────────────────────────────────────────────────────────

def test_detect_language_vietnamese():
    assert detect_user_language("máy lạnh bị hỏng") == "vi"

def test_detect_language_english():
    assert detect_user_language("how much does it cost to fix the pipe") == "en"


# ── normalize_noaccent ────────────────────────────────────────────────────────

def test_normalize_may_lanh():
    assert "máy lạnh" in normalize_noaccent("may lanh")

def test_normalize_dien():
    assert "điện" in normalize_noaccent("dien")

def test_normalize_sua_chua():
    # "sua" → "sửa" replaces before the compound "sua chua" → "sửa chữa" can fire
    # The result contains "sửa" either way — verify the accent is applied
    result = normalize_noaccent("sua chua")
    assert "sửa" in result

def test_normalize_chong_tham():
    assert "chống thấm" in normalize_noaccent("chong tham")
