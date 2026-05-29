"""
tests/unit/test_retrieval.py
Tests for core/retrieval.py should_retrieve_context().
New signature: should_retrieve_context(query, tool_name, booking_state)
"""
import os
os.environ.setdefault("FIXAGO_TEST_MODE", "1")

import pytest
from core.retrieval import should_retrieve_context


# ── Tool-backed → always False ────────────────────────────────────────────────

def test_get_services_returns_false():
    assert should_retrieve_context("sửa điện bao nhiêu", tool_name="get_services") is False


def test_get_groups_returns_false():
    assert should_retrieve_context("fixago có dịch vụ gì", tool_name="get_groups") is False


def test_get_promotions_returns_false():
    assert should_retrieve_context("có khuyến mãi không", tool_name="get_promotions") is False


def test_create_booking_returns_false():
    assert should_retrieve_context("xác nhận đặt lịch", tool_name="create_booking") is False


# ── Confirmation short replies → False ───────────────────────────────────────

@pytest.mark.parametrize("query", ["ok", "chốt", "xác nhận", "confirm", "đặt đi", "có"])
def test_confirmation_returns_false(query):
    assert should_retrieve_context(query, tool_name=None) is False


# ── Booking awaiting confirmation → False ────────────────────────────────────

def test_awaiting_confirmation_returns_false():
    assert should_retrieve_context(
        "tôi muốn đặt lịch",
        tool_name=None,
        booking_state={"awaiting_confirmation": True},
    ) is False


# ── Normal queries → True ─────────────────────────────────────────────────────

def test_general_qa_returns_true():
    assert should_retrieve_context("fixago có bảo hành không", tool_name=None) is True


def test_no_tool_general_question_returns_true():
    assert should_retrieve_context("Fixago làm gì?", tool_name=None) is True


def test_no_tool_repair_question_returns_true():
    assert should_retrieve_context("tôi cần sửa máy lạnh", tool_name=None) is True
