"""Unit tests for llm_client/client.py — no real LLM needed."""
import os
os.environ.setdefault("FIXAGO_TEST_MODE", "1")

from unittest.mock import patch, MagicMock

import pytest
import requests

from llm_client.client import llm_chat


_SYSTEM = {"role": "system", "content": "You are Fixago."}
_USER   = {"role": "user",   "content": "Sửa điện bao nhiêu?"}
_MSGS   = [_SYSTEM, _USER]


# ── Timeout → graceful Vietnamese message ────────────────────────────────────

@patch("requests.post", side_effect=requests.exceptions.Timeout("simulated"))
def test_llm_timeout_returns_graceful_msg(mock_post):
    result = llm_chat(_MSGS)
    assert isinstance(result, str)
    assert len(result) > 0
    # Should not be an empty string or raw exception text
    assert "Timeout" not in result
    assert "Exception" not in result


# ── HTTP 500 → RuntimeError ───────────────────────────────────────────────────

def _mock_500(*args, **kwargs):
    m = MagicMock()
    m.status_code = 500
    m.text = "Internal Server Error"
    return m


@patch("requests.post", side_effect=_mock_500)
def test_llm_500_raises_runtime_error(mock_post):
    with pytest.raises(RuntimeError, match="500"):
        llm_chat(_MSGS)


# ── Context size exceeded → trims and retries ─────────────────────────────────

def _mock_400_then_200(*args, **kwargs):
    """First call returns 400 with exceed_context_size; second returns 200."""
    if not hasattr(_mock_400_then_200, "_called"):
        _mock_400_then_200._called = True
        m = MagicMock()
        m.status_code = 400
        m.text = '{"error": "exceed_context_size: 1100 > 1024"}'
        return m
    m = MagicMock()
    m.status_code = 200
    m.json.return_value = {"choices": [{"message": {"content": "Trimmed reply."}}]}
    return m


@patch("requests.post", side_effect=_mock_400_then_200)
def test_context_exceeded_trims_and_retries(mock_post):
    # Reset call counter
    if hasattr(_mock_400_then_200, "_called"):
        del _mock_400_then_200._called
    result = llm_chat(_MSGS)
    assert isinstance(result, str)
    assert len(result) > 0
    # Should have called post twice (original + retry)
    assert mock_post.call_count == 2


# ── Successful response ───────────────────────────────────────────────────────

def _mock_200(*args, **kwargs):
    m = MagicMock()
    m.status_code = 200
    m.json.return_value = {"choices": [{"message": {"content": "Giá từ 120.000 VNĐ."}}]}
    return m


@patch("requests.post", side_effect=_mock_200)
def test_llm_success(mock_post):
    result = llm_chat(_MSGS)
    assert result == "Giá từ 120.000 VNĐ."
