"""
core/prompt_builder.py
System prompt loading, dynamic few-shot injection, and history compaction.
"""
import json
import os
import re
from typing import Optional

_UNIVERSAL_SHOTS = (
    "Q: Nhà tôi bị mất điện, sửa bao nhiêu?\n"
    "A: Dạ mất điện thường do cầu dao hoặc hở dây. Giá tham khảo từ 150k. Anh/chị cho xin địa chỉ để đặt thợ nhé?\n\n"
    "Q: Đặt thợ sửa điều hòa\n"
    "A: Dạ Fixago hỗ trợ đặt lịch ngay. Anh/chị cho xin họ tên, SĐT và địa chỉ nhé?"
)


_SYSTEM_PROMPT_CACHE: Optional[str] = None
_FALLBACK_PROMPT = "Bạn là Trợ lý AI của Fixago. Luôn trả lời bằng tiếng Việt, lịch sự, ngắn gọn và hữu ích."


def load_system_prompt() -> str:
    global _SYSTEM_PROMPT_CACHE
    if _SYSTEM_PROMPT_CACHE is None:
        try:
            path = os.path.join(os.path.dirname(__file__), "..", "system_prompt.txt")
            with open(path, "r", encoding="utf-8") as f:
                _SYSTEM_PROMPT_CACHE = f.read().strip()
        except Exception:
            _SYSTEM_PROMPT_CACHE = _FALLBACK_PROMPT
    return _SYSTEM_PROMPT_CACHE


def reload_system_prompt() -> str:
    """Force re-read from disk. Use in tests or after editing system_prompt.txt."""
    global _SYSTEM_PROMPT_CACHE
    _SYSTEM_PROMPT_CACHE = None
    return load_system_prompt()


def select_few_shots(intent=None) -> str:
    """Return universal structural examples. Intent argument kept for API compatibility."""
    return "\n\nEXAMPLES:\n" + _UNIVERSAL_SHOTS + "\n"


def build_system_prompt(
    base: str,
    booking_state: dict,
    enable_native_tool_call: bool,
    detected_intent: str | None = None,
    catalog: str = "",
) -> str:
    """
    In native tool-call mode: return base unchanged.
    In legacy text mode: append few-shot examples + session state + catalog.
    """
    if enable_native_tool_call:
        return base

    examples = select_few_shots(detected_intent)
    catalog_line = f"\nDỊCH VỤ: {catalog}\n" if catalog else ""
    state = (
        f"SESSION_STATE:\n"
        f"- Tên: {booking_state.get('name') or 'Chưa có'}\n"
        f"- SĐT: {booking_state.get('phone') or 'Chưa có'}\n"
        f"- Địa chỉ: {booking_state.get('address') or 'Chưa có'}\n"
        f"- Vấn đề: {booking_state.get('issue') or 'Chưa có'}\n\n"
    )
    return base + catalog_line + examples.replace("EXAMPLES:\n", state + "EXAMPLES:\n")


def compact_history(history, max_items=3):
    if not isinstance(history, list):
        return []
    clean = []
    for msg in history[-max_items:]:
        if not isinstance(msg, dict):
            continue
        role    = msg.get("role", "user")
        content = msg.get("content", "")
        if role not in ("system", "user", "assistant"):
            role = "user"
        if content:
            safe_content = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)
            clean.append({"role": role, "content": safe_content})
    return clean
