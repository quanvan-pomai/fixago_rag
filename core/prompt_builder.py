"""
core/prompt_builder.py
System prompt loading, dynamic few-shot injection, and history compaction.
"""
import os
import re

_INTENT_SHOTS: dict[str | None, list[str]] = {
    "get_groups": [
        "Q: Fixago có dịch vụ gì?\nA: CALL_TOOL: get_groups()",
        "Q: Bên bạn làm được gì?\nA: CALL_TOOL: get_groups()",
    ],
    "get_promotions": [
        "Q: Có khuyến mãi gì không?\nA: CALL_TOOL: get_promotions()",
        "Q: Có mã giảm giá không?\nA: CALL_TOOL: get_promotions()",
    ],
    "get_services_nước": [
        "Q: Sửa ống nước giá bao nhiêu?\nA: CALL_TOOL: get_services(search=\"nước\")",
        "Q: Nước rỉ dưới bồn rửa sửa bao nhiêu?\nA: CALL_TOOL: get_services(search=\"nước\")",
    ],
    "get_services_điện": [
        "Q: Sửa chập điện bao nhiêu?\nA: CALL_TOOL: get_services(search=\"điện\")",
        "Q: Điện hay nhảy cầu dao, chi phí thế nào?\nA: CALL_TOOL: get_services(search=\"điện\")",
    ],
    "get_services_máy lạnh": [
        "Q: Điều hòa không mát giá bao nhiêu?\nA: CALL_TOOL: get_services(search=\"máy lạnh\")",
        "Q: Máy lạnh nhỏ giọt nước thì sửa bao nhiêu?\nA: CALL_TOOL: get_services(search=\"máy lạnh\")",
    ],
    "get_services_xây dựng": [
        "Q: Chống thấm tường giá bao nhiêu?\nA: CALL_TOOL: get_services(search=\"xây dựng\")",
    ],
    "get_services_thạch cao": [
        "Q: Làm trần thạch cao giá bao nhiêu?\nA: CALL_TOOL: get_services(search=\"thạch cao\")",
    ],
    "booking": [
        "Q: Tôi muốn đặt thợ sửa điện\nA: Dạ mình hỗ trợ bạn đặt lịch được ạ. Bạn cho mình xin họ tên, số điện thoại và địa chỉ cần sửa nhé.",
        "Q: ok đặt đi\nA: CALL_TOOL: create_booking(name=\"...\", phone=\"...\", address=\"...\", description=\"...\")",
    ],
    None: [
        "Q: Fixago có dịch vụ gì?\nA: CALL_TOOL: get_groups()",
        "Q: Tôi muốn đặt thợ\nA: Dạ mình hỗ trợ bạn đặt lịch được ạ. Bạn cho mình xin họ tên, số điện thoại và địa chỉ cần sửa nhé.",
    ],
}


def load_system_prompt() -> str:
    try:
        path = os.path.join(os.path.dirname(__file__), "..", "system_prompt.txt")
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return "Bạn là Trợ lý AI của Fixago. Luôn trả lời bằng tiếng Việt, lịch sự, ngắn gọn và hữu ích."


def select_few_shots(intent: str | None) -> str:
    """Return 2-3 Q&A examples matched to the detected intent."""
    if intent is None:
        key: str | None = None
    elif "get_groups" in intent:
        key = "get_groups"
    elif "get_promotions" in intent:
        key = "get_promotions"
    elif "get_services" in intent:
        m = re.search(r'search="([^"]*)"', intent)
        svc = m.group(1) if m else ""
        candidate = f"get_services_{svc}"
        key = candidate if candidate in _INTENT_SHOTS else "get_services_điện"
    elif "create_booking" in intent:
        key = "booking"
    else:
        key = None
    shots = _INTENT_SHOTS.get(key, _INTENT_SHOTS[None])
    return "\n\nEXAMPLES:\n" + "\n\n".join(shots) + "\n"


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


def compact_history(history, max_items=8):
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
            clean.append({"role": role, "content": str(content)})
    return clean
