"""Unit tests for core/output_validator.py — no external deps."""
import os
os.environ.setdefault("FIXAGO_TEST_MODE", "1")

import pytest
from core.output_validator import validate_llm_output


def test_blocks_call_tool_leak():
    response = "CALL_TOOL: get_services(search=\"điện\") Đây là thông tin điện."
    result = validate_llm_output(response, None, "sửa điện")
    assert result is not None
    assert "CALL_TOOL" not in result


def test_blocks_call_tool_only():
    """Bare CALL_TOOL with no useful content → error message."""
    result = validate_llm_output("CALL_TOOL: get_groups()", None, "dịch vụ gì")
    assert result is not None
    assert "CALL_TOOL" not in result


def test_blocks_data_block_leak():
    response = "[DỮ LIỆU HỆ THỐNG — chỉ dùng thông tin này để trả lời]"
    result = validate_llm_output(response, None, "query")
    assert result is not None
    assert "[DỮ LIỆU HỆ THỐNG" not in result


def test_blocks_system_prompt_leak():
    response = "system prompt: You are Fixago AI assistant."
    result = validate_llm_output(response, None, "query")
    assert result is not None


def test_blocks_cyrillic():
    response = "Добрый день, я не знаю."
    result = validate_llm_output(response, None, "sửa điện")
    assert result is not None
    assert "Добрый" not in result


def test_blocks_arabic():
    response = "مرحبا كيف حالك"
    result = validate_llm_output(response, None, "sửa điện")
    assert result is not None


def test_blocks_ignorance_when_data_present():
    data_block = "Giá tham khảo: 250.000 VNĐ.\n- Sửa chập điện: 250.000 VNĐ."
    response = "Mình chưa có thông tin về dịch vụ này."
    result = validate_llm_output(response, data_block, "sửa điện")
    assert result is not None
    assert "VNĐ" in result or "250" in result


def test_ignorance_without_data_passes():
    """No data injected → 'chưa có thông tin' is valid."""
    result = validate_llm_output("Mình chưa có thông tin về dịch vụ này.", None, "query")
    assert result is None


def test_passes_valid_vietnamese():
    response = "Dạ Fixago có thể hỗ trợ bạn sửa điện, nước, máy lạnh và nhiều hơn nữa ạ."
    result = validate_llm_output(response, None, "dịch vụ gì")
    assert result is None


def test_passes_valid_english():
    response = "Fixago offers electrical, plumbing, and air conditioning repair services."
    result = validate_llm_output(response, None, "what services")
    assert result is None


def test_cyrillic_query_passes_cyrillic_response():
    """If the query itself has Cyrillic, don't block Cyrillic response."""
    query = "Добрый день"
    response = "Мы предлагаем услуги ремонта."
    result = validate_llm_output(response, None, query)
    assert result is None
