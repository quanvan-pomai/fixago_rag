"""
core/query_processor.py
Multi-question splitting, multi-service detection, tool data fetching.
"""
import re

from core.intent_router import normalize_noaccent, detect_tool_intent, is_hours_question
from tools.handlers import (
    fetch_raw_groups, fetch_raw_services, fetch_raw_promotions,
    format_groups_for_llm, format_services_for_llm, format_promotions_for_llm,
)
from booking.handler import normalize_service_search

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
    """Split a multi-question message into individual sub-questions."""
    raw = (query or "").strip()
    if not raw:
        return [raw]

    # 1. Split on ? or ! followed by next sentence
    parts = re.split(r'(?<=[?!])\s+(?=[A-ZÀ-Ỹa-zà-ỹ0-9])', raw)
    if len(parts) >= 2 and all(p.strip() for p in parts):
        return [p.strip() for p in parts]

    # 2. Split on transition words
    parts = re.split(
        r'[,;]\s*(?:còn|ngoài ra|thêm nữa|bên cạnh đó|đồng thời)\s+',
        raw, flags=re.IGNORECASE
    )
    if len(parts) >= 2 and all(p.strip() for p in parts):
        return [p.strip() for p in parts]

    # 3. Split on " + "
    if " + " in raw:
        parts = [p.strip() for p in raw.split(" + ") if p.strip()]
        if len(parts) >= 2:
            return parts

    # 4. Split on ", " or ";" when each part has a signal
    for sep in [",", ";"]:
        sep_parts = [p.strip() for p in raw.split(sep) if p.strip()]
        if len(sep_parts) >= 2 and len(sep_parts) <= 5:
            if all(any(s in p.lower() for s in _Q_SIGNALS) for p in sep_parts):
                return sep_parts

    # 5. Split on " và " for distinct topics
    and_parts = re.split(r'\s+và\s+', raw, flags=re.IGNORECASE)
    if len(and_parts) >= 2:
        parts_lower = [p.lower() for p in and_parts]
        has_hours_side = any(is_hours_question(p) for p in parts_lower)
        has_topic_side = any(any(s in p for s in _SERVICE_SIGNALS + _QUESTION_SIGNALS)
                             for p in parts_lower)
        if has_hours_side and has_topic_side:
            return [p.strip() for p in and_parts]
        a, b = parts_lower[0], parts_lower[-1]
        if ((any(s in a for s in _SERVICE_SIGNALS) and any(s in b for s in _SERVICE_SIGNALS))
                or (any(s in a for s in _QUESTION_SIGNALS) and any(s in b for s in _QUESTION_SIGNALS))):
            return [p.strip() for p in and_parts]

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
    If query mentions two+ service categories with a clear separator,
    fetch both data blocks and return a combined string for LLM injection.
    Returns first_tool unchanged if no multi-service detected.
    """
    q = normalize_noaccent((query or "").lower())

    _MULTI_SEPARATORS = [
        " còn ", " và giá ", " với giá ", " or ", " and price",
        "bao nhiêu,", "bao nhiêu còn", "ngoài ra", "; ",
        " + ", "cùng với",
    ]
    if not any(sep in q for sep in _MULTI_SEPARATORS):
        return first_tool

    matched = []
    for key, kws in _MULTI_SERVICE_MAP.items():
        if any(kw in q for kw in kws):
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

    # Return combined data — caller must pass to _llm_with_injected_data
    return "\n\n---\n".join(data_blocks)
