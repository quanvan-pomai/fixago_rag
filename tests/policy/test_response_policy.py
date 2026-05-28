"""tests/policy/test_response_policy.py — ResponsePolicy derivation tests."""
import pytest
from core.intent_result import Confidence, IntentResult
from core.policy import PolicyType, ResponsePolicy, policy_for_intent


def _ir(tool_call_str, confidence=Confidence.HIGH, ambiguity=None):
    return IntentResult(
        tool_call_str=tool_call_str,
        confidence=confidence,
        ambiguity_reason=ambiguity,
    )


# ── Service overview ──────────────────────────────────────────────────────────

def test_get_groups_high_gives_service_overview():
    p = policy_for_intent(_ir('CALL_TOOL: get_groups()'), "Fixago có dịch vụ gì?")
    assert p.policy_type == PolicyType.SERVICE_OVERVIEW
    assert p.should_cache is True
    assert p.retrieve_rag is False
    assert p.temperature == 0.15


# ── Service price ─────────────────────────────────────────────────────────────

def test_get_services_high_gives_service_price():
    p = policy_for_intent(_ir('CALL_TOOL: get_services(search="điện")'), "Sửa điện bao nhiêu?")
    assert p.policy_type == PolicyType.SERVICE_PRICE
    assert p.should_cache is True
    assert p.retrieve_rag is False
    assert p.temperature == 0.15


def test_get_services_medium_gives_unknown_clarify():
    p = policy_for_intent(
        _ir('CALL_TOOL: get_services(search="all")', confidence=Confidence.MEDIUM, ambiguity="generic"),
        "Giá sao?",
    )
    assert p.policy_type == PolicyType.UNKNOWN_CLARIFY
    assert p.should_cache is False


def test_get_services_low_gives_unknown_clarify():
    p = policy_for_intent(
        _ir('CALL_TOOL: get_services(search="nước")', confidence=Confidence.LOW),
        "Hỏng rồi",
    )
    assert p.policy_type == PolicyType.UNKNOWN_CLARIFY


# ── Promotions ────────────────────────────────────────────────────────────────

def test_get_promotions_gives_promotion_policy():
    p = policy_for_intent(_ir('CALL_TOOL: get_promotions()'), "Có khuyến mãi không?")
    assert p.policy_type == PolicyType.PROMOTION
    assert p.should_cache is True
    assert p.temperature == 0.15


# ── Working hours ─────────────────────────────────────────────────────────────

def test_working_hours_query():
    p = policy_for_intent(_ir(None), "Giờ làm việc bên bạn thế nào?")
    assert p.policy_type == PolicyType.WORKING_HOURS
    assert p.should_cache is True
    assert p.retrieve_rag is False
    assert p.temperature == 0.1


# ── Off-topic ─────────────────────────────────────────────────────────────────

def test_off_topic_query():
    p = policy_for_intent(_ir(None), "Viết bài thơ tình cho tôi")
    assert p.policy_type == PolicyType.OFF_TOPIC
    assert p.should_cache is True
    assert p.retrieve_rag is False


# ── Safety ────────────────────────────────────────────────────────────────────

def test_safety_warning_query():
    p = policy_for_intent(_ir(None), "Nhà tôi bị tóe lửa điện")
    assert p.policy_type == PolicyType.SAFETY_WARNING
    assert p.should_cache is False
    assert p.temperature == 0.1


# ── Booking policies ──────────────────────────────────────────────────────────

def test_booking_start():
    p = policy_for_intent(_ir(None), "Tôi muốn đặt thợ sửa điện")
    assert p.policy_type == PolicyType.BOOKING_START
    assert p.should_cache is False


def test_booking_create():
    p = policy_for_intent(_ir('CALL_TOOL: create_booking(name="A")'), "ok đặt đi")
    assert p.policy_type == PolicyType.BOOKING_CREATE
    assert p.should_cache is False
    assert p.temperature == 0.1


def test_booking_start_cache_false():
    p = policy_for_intent(_ir(None), "Đặt lịch sửa nước")
    assert p.should_cache is False


# ── Temperature correctness ───────────────────────────────────────────────────

def test_unknown_clarify_temperature():
    p = policy_for_intent(
        _ir('CALL_TOOL: get_services(search="all")', confidence=Confidence.MEDIUM),
        "Giá bao nhiêu?",
    )
    assert p.temperature == 0.2


def test_general_fixago_qa_retrieve_rag():
    p = policy_for_intent(_ir(None), "Fixago có uy tín không?")
    assert p.policy_type == PolicyType.GENERAL_FIXAGO_QA
    assert p.retrieve_rag is True
    assert p.temperature == 0.2
