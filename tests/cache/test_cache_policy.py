"""tests/cache/test_cache_policy.py — Cache policy and cache key tests."""
import pytest
from core.intent_result import Confidence, IntentResult
from core.policy import PolicyType, ResponsePolicy, policy_for_intent
from core.cache_policy import make_cache_key, should_cache_response


def _policy(policy_type, should_cache):
    return ResponsePolicy(policy_type=policy_type, should_cache=should_cache)


# ── should_cache_response ─────────────────────────────────────────────────────

def test_booking_start_not_cached():
    p = _policy(PolicyType.BOOKING_START, should_cache=False)
    assert should_cache_response(p, backend_ok=True) is False


def test_booking_collect_not_cached():
    p = _policy(PolicyType.BOOKING_COLLECT_INFO, should_cache=False)
    assert should_cache_response(p, backend_ok=True) is False


def test_booking_confirm_not_cached():
    p = _policy(PolicyType.BOOKING_CONFIRM, should_cache=False)
    assert should_cache_response(p, backend_ok=True) is False


def test_booking_create_not_cached():
    p = _policy(PolicyType.BOOKING_CREATE, should_cache=False)
    assert should_cache_response(p, backend_ok=True) is False


def test_service_price_backend_ok_cached():
    p = _policy(PolicyType.SERVICE_PRICE, should_cache=True)
    assert should_cache_response(p, backend_ok=True) is True


def test_service_price_backend_fail_not_cached():
    p = _policy(PolicyType.SERVICE_PRICE, should_cache=True)
    assert should_cache_response(p, backend_ok=False) is False


# ── make_cache_key ────────────────────────────────────────────────────────────

def test_cache_key_deterministic():
    k1 = make_cache_key("sys", "hist", "data", "rag", "query")
    k2 = make_cache_key("sys", "hist", "data", "rag", "query")
    assert k1 == k2


def test_cache_key_differs_on_data_block():
    k1 = make_cache_key("sys", "hist", "data_v1", "rag", "query")
    k2 = make_cache_key("sys", "hist", "data_v2", "rag", "query")
    assert k1 != k2


def test_cache_key_has_prefix():
    k = make_cache_key("s", "h", "d", "r", "q")
    assert k.startswith("pomai_cache:response:")
