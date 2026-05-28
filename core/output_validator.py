"""
core/output_validator.py
Catches LLM failures: wrong-script output, CALL_TOOL leaks,
prompt content leakage, ignorance phrases when data was injected.
Returns a replacement string or None (response is valid).
"""
import re

_IGNORANCE_PHRASES = [
    "chưa có thông tin", "không có thông tin", "không tìm thấy thông tin",
    "chưa có dữ liệu", "không có dữ liệu", "tôi không biết",
    "mình chưa có thông tin", "chưa tìm thấy",
    "i don't know", "don't have information", "no information available",
    "không thể cung cấp", "không có trong hệ thống",
]
_TOOL_LEAK_RE = re.compile(r'CALL_TOOL\s*:', re.IGNORECASE)
_PROMPT_LEAK_PHRASES = [
    "[DỮ LIỆU HỆ THỐNG", "SESSION_STATE:", "EXAMPLES:\nQ:", "system prompt",
]


def validate_llm_output(response: str, data_block: str | None, query: str = "") -> str | None:
    """
    Returns a replacement string if the response is bad, None if OK.
    """
    r = (response or "").strip()

    # CALL_TOOL leaked into conversational output
    if _TOOL_LEAK_RE.search(r):
        cleaned = _TOOL_LEAK_RE.sub("", r).strip()
        if len(cleaned) > 20:
            return cleaned
        return "Dạ mình gặp sự cố xử lý. Bạn thử hỏi lại nhé ạ."

    # Prompt internals leaked
    if any(p in r for p in _PROMPT_LEAK_PHRASES):
        return "Dạ mình gặp sự cố xử lý. Bạn thử hỏi lại nhé ạ."

    # Wrong script — Cyrillic/Arabic/CJK when query is Vietnamese or no-accent VI
    _has_cyrillic = bool(re.search(r'[Ѐ-ӿ]', r))
    _has_arabic   = bool(re.search(r'[؀-ۿ]', r))
    _has_cjk      = bool(re.search(r'[一-鿿぀-ゟ゠-ヿ]', r))
    if _has_cyrillic or _has_arabic or _has_cjk:
        if not re.search(r'[Ѐ-ӿ]', query):
            return "Dạ mình gặp sự cố xử lý. Bạn thử hỏi lại nhé ạ."

    # Model claims no data when real data was injected
    if data_block:
        has_real_data = (
            "VNĐ" in data_block
            or "tham khảo" in data_block
            or "dịch vụ" in data_block.lower()
            or any(c.isdigit() for c in data_block)
        )
        if has_real_data and any(p in r.lower() for p in _IGNORANCE_PHRASES):
            return (
                "Dạ đây là thông tin Fixago có:\n\n"
                + data_block.strip()
                + "\n\nBạn cần hỗ trợ thêm không ạ?"
            )

    return None
