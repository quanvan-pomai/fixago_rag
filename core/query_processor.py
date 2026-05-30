"""
core/query_processor.py
Multi-question splitting, multi-service detection, tool data fetching.
"""
import re

# NOTE: This file is legacy and not used in experiment branch.
# Keeping for reference only. All logic moved to orchestrator_simple.py

_Q_SIGNALS = [
    "giá", "bao nhiêu", "gì", "sao", "thế nào", "ra sao", "như thế",
    "không", "có", "dịch vụ", "km", "khuyến mãi", "ưu đãi",
    "sửa", "lắp", "kiểm tra", "hỏng", "bị", "lỗi", "hư",
    "điện", "nước", "máy lạnh", "xây", "thạch cao",
    "giờ", "thời gian", "mấy giờ", "làm việc", "hoạt động", "open",
    "how much", "what", "when", "price", "service", "fix", "repair", "hour",
]

_SERVICE_SIGNALS = [
    "điện", "nước", "máy lạnh", "xây", "thạch cao", "sơn", "ống",
    "electric", "water", "pipe", "air con", "dịch vụ", "services",
    "khuyến mãi", "promotion", "km",
]
_QUESTION_SIGNALS = [
    "giá", "bao nhiêu", "thế nào", "ra sao", "có không", "dịch vụ",
    "how much", "what", "price",
]

_MULTI_SERVICE_MAP = {
    "điện":      ["điện", "chập", "ổ cắm", "bóng đèn", "công tắc", "aptomat", "dây điện"],
    "nước":      ["nước", "ống", "rò", "nghẹt", "vòi", "bồn cầu", "máy bơm", "lavabo"],
    "máy lạnh":  ["máy lạnh", "điều hòa", "tủ lạnh", "không lạnh", "máy giặt", "điện lạnh"],
    "xây dựng":  ["sơn", "chống thấm", "ốp lát", "tường", "ban công", "xây dựng", "dột"],
    "thạch cao": ["thạch cao", "trần", "vách ngăn"],
}


def split_questions(query: str) -> list[str]:
    """Split a multi-question message into individual sub-questions.
    Only split on UNAMBIGUOUS boundaries to avoid over-splitting single issues."""
    raw = (query or "").strip()
    if not raw:
        return [raw]

    # 1. Split on ? or ! followed by next sentence (most reliable)
    parts = re.split(r'(?<=[?!])\s+(?=[A-ZÀ-Ỹa-zà-ỹ0-9])', raw)
    if len(parts) >= 2 and all(p.strip() for p in parts):
        return [p.strip() for p in parts]

    # 2. Only split on explicit transition words (very conservative)
    parts = re.split(
        r'(?:,\s*còn\s+|;\s*ngoài ra\s+)',
        raw, flags=re.IGNORECASE
    )
    if len(parts) >= 2 and all(p.strip() for p in parts):
        return [p.strip() for p in parts]

    # 3. Split on " + " (often separates topics)
    if " + " in raw:
        parts = [p.strip() for p in raw.split(" + ") if p.strip()]
        if len(parts) >= 2:
            return parts

    return [raw]


def fetch_tool_data_block(tool_str: str, used_tools: list) -> str:
    """
    Fetch raw backend data for a CALL_TOOL string and return a compact fact-block.
    Returns "" if no matching tool.
    """
    _ERR = "Dạ hiện mình chưa lấy được thông tin từ hệ thống. Bạn thử lại sau ít phút nhé ạ."

    if "get_groups" in tool_str:
        used_tools.append("Tool [Backend API]: GET /services/groups")
        result = fetch_raw_groups()
        if not result.ok:
            return _ERR
        return format_groups_for_llm(result.data)

    if "get_promotions" in tool_str:
        used_tools.append("Tool [Backend API]: GET /discounts/available")
        result = fetch_raw_promotions()
        if not result.ok:
            return _ERR
        return format_promotions_for_llm(result.data)

    if "get_services" in tool_str:
        m = re.search(r'search="([^"]*)"', tool_str)
        search = normalize_service_search(m.group(1) if m else "")
        used_tools.append(f'Tool [Backend API]: GET /services?search="{search}"')
        result = fetch_raw_services(search)
        if not result.ok:
            return _ERR
        return format_services_for_llm(result.data, search)

    return ""


def resolve_tool_data(sub_query: str, used_tools: list) -> str:
    """For a single sub-question, fetch backend data if needed."""
    tool = detect_tool_intent(sub_query)
    if not tool:
        return ""
    return fetch_tool_data_block(tool, used_tools)


def detect_multi_service(query: str, first_tool: str, messages: list, used_tools: list):
    """
    LEGACY PATH ONLY. If query mentions two+ service categories with UNAMBIGUOUS separators,
    fetch both data blocks. Returns first_tool unchanged if no multi-service detected.

    Native path (ENABLE_NATIVE_TOOL_CALL=1) does NOT use this — LLM handles routing.
    """
    q = normalize_noaccent((query or "").lower())

    _UNAMBIGUOUS_SEPARATORS = [
        " và ", " + ", " tính cả ",
    ]
    if not any(sep in q for sep in _UNAMBIGUOUS_SEPARATORS):
        return first_tool

    matched = []
    for key in ["điện", "nước", "máy lạnh", "xây dựng", "thạch cao"]:
        if key in q:
            matched.append(key)

    if len(matched) < 2:
        return first_tool

    data_blocks = []
    for svc in matched[:2]:
        tool_str = f'CALL_TOOL: get_services(search="{svc}")'
        block = fetch_tool_data_block(tool_str, used_tools)
        if block:
            data_blocks.append(block)

    if not data_blocks:
        return first_tool

    return "\n\n---\n".join(data_blocks)
