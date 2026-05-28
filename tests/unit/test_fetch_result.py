"""Unit tests for FetchResult and fetch_raw_* functions."""
import os
os.environ.setdefault("FIXAGO_TEST_MODE", "1")

import json
from unittest.mock import patch, MagicMock

import pytest
import requests

from tools.handlers import (
    FetchResult,
    fetch_raw_groups,
    fetch_raw_services,
    fetch_raw_promotions,
    init_cache,
)
from db.cache_store import FakeCacheStore


# ── FetchResult dataclass ─────────────────────────────────────────────────────

def test_fetch_result_ok():
    r = FetchResult(ok=True, data=[1, 2, 3])
    assert r.ok is True
    assert r.data == [1, 2, 3]
    assert r.error == ""


def test_fetch_result_error():
    r = FetchResult(ok=False, error="timeout")
    assert r.ok is False
    assert r.data == []
    assert r.error == "timeout"


def test_fetch_result_default_data():
    r = FetchResult(ok=True)
    assert r.data == []


# ── Backend timeout → ok=False ────────────────────────────────────────────────

def _timeout_get(*args, **kwargs):
    raise requests.exceptions.Timeout("simulated timeout")


@patch("tools.handlers._cache", None)   # disable cache so HTTP is attempted
@patch("requests.get", side_effect=_timeout_get)
def test_groups_timeout_returns_error(mock_get):
    result = fetch_raw_groups()
    assert result.ok is False
    assert result.data == []
    assert result.error != ""


@patch("tools.handlers._cache", None)
@patch("requests.get", side_effect=_timeout_get)
def test_services_timeout_returns_error(mock_get):
    result = fetch_raw_services("điện")
    assert result.ok is False
    assert result.data == []


@patch("tools.handlers._cache", None)
@patch("requests.get", side_effect=_timeout_get)
def test_promotions_timeout_returns_error(mock_get):
    result = fetch_raw_promotions()
    assert result.ok is False
    assert result.data == []


# ── HTTP 503 → ok=False ───────────────────────────────────────────────────────

def _bad_response(*args, **kwargs):
    m = MagicMock()
    m.status_code = 503
    return m


@patch("tools.handlers._cache", None)
@patch("requests.get", side_effect=_bad_response)
def test_groups_http_error_returns_error(mock_get):
    result = fetch_raw_groups()
    assert result.ok is False


# ── Cache hit → ok=True ───────────────────────────────────────────────────────

def test_cache_hit_groups_returns_ok():
    fake = FakeCacheStore()
    sample = [{"name": "Điện"}, {"name": "Nước"}]
    fake.set("grp_cache", json.dumps(sample, ensure_ascii=False).encode())
    init_cache(fake)

    result = fetch_raw_groups()
    assert result.ok is True
    assert len(result.data) == 2
    assert result.data[0]["name"] == "Điện"

    init_cache(None)  # reset


def test_cache_hit_services_returns_ok():
    fake = FakeCacheStore()
    sample = [{"name": "Sửa điện", "unitPrice": 250000, "estimatedTime": 60}]
    fake.set("svc_cache:điện", json.dumps(sample, ensure_ascii=False).encode())
    init_cache(fake)

    result = fetch_raw_services("điện")
    assert result.ok is True
    assert result.data[0]["name"] == "Sửa điện"

    init_cache(None)
