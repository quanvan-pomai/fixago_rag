"""Unit tests for core/query_processor.split_questions — no external deps."""
import os
os.environ.setdefault("FIXAGO_TEST_MODE", "1")

import pytest
from core.query_processor import split_questions


def test_split_on_question_mark():
    parts = split_questions("Giá điện bao nhiêu? Còn nước thì sao?")
    assert len(parts) == 2
    assert any("điện" in p for p in parts)
    assert any("nước" in p for p in parts)


def test_split_on_va_hours_combo():
    parts = split_questions("Dịch vụ gì và giờ làm việc thế nào?")
    assert len(parts) == 2


def test_split_on_plus():
    parts = split_questions("Giá dịch vụ + có khuyến mãi + giờ làm việc")
    assert len(parts) == 3


def test_no_split_single():
    parts = split_questions("Sửa chập điện bao nhiêu?")
    assert len(parts) == 1


def test_no_split_short():
    parts = split_questions("Sửa điện")
    assert len(parts) == 1


def test_split_on_semicolon_with_signals():
    parts = split_questions("giá điện bao nhiêu; giá nước thế nào")
    assert len(parts) == 2


def test_empty_string():
    parts = split_questions("")
    assert len(parts) == 1


def test_split_on_con():
    parts = split_questions("Fixago có dịch vụ gì, còn giờ làm việc thế nào")
    assert len(parts) == 2
