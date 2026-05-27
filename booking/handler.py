"""
booking/handler.py
------------------
Booking flow logic:
  - Build the next conversational response when booking intent is detected
  - Resolve a real serviceId from the backend
  - Execute the create_booking API call
"""
import logging
import os
import re
from typing import Dict, List, Optional, Tuple

import requests

from booking.extractor import (
    detect_confirmation,
    detect_booking_intent,
    detect_negation,
    merge_booking_info,
)

logger = logging.getLogger("fixago.booking_handler")

BACKEND_URL = os.environ.get("BACKEND_API_URL", "http://127.0.0.1:3001/api/v1")


# ── Service keyword → search term normalization ───────────────────────────────

def normalize_service_search(raw: str) -> str:
    """Map a free-form description to a canonical backend search keyword."""
    s = (raw or "").strip().lower()
    if any(k in s for k in ["máy lạnh", "điều hòa", "tủ lạnh", "gas", "không lạnh", "lạnh", "điện lạnh"]):
        return "máy lạnh"
    if any(k in s for k in ["điện", "chập", "ổ cắm", "bóng đèn", "công tắc", "tủ điện", "aptomat", "cb", "dây điện"]):
        return "điện"
    if any(k in s for k in ["nước", "ống", "bơm", "van", "bồn", "vòi", "nghẹt", "rò", "lavabo", "thoát nước"]):
        return "nước"
    if any(k in s for k in ["giặt", "máy giặt"]):
        return "máy giặt"
    if any(k in s for k in ["sơn", "chống thấm", "ốp lát", "tường", "ban công", "xây", "trát", "dột", "bê tông"]):
        return "xây dựng"
    if any(k in s for k in ["thạch cao", "trần", "vách ngăn"]):
        return "thạch cao"
    return raw.strip()


# ── Real serviceId resolution ─────────────────────────────────────────────────

def resolve_service_id(description: str) -> Tuple[int, Optional[int]]:
    """
    Fetch a real serviceId from the backend matching the booking description.
    Backend requires at least 1 detail — never returns None.

    Strategy:
      1. Search by normalized keyword
      2. Fallback to first active service in the system

    Raises RuntimeError if the backend is completely unreachable.
    """
    search_key = normalize_service_search(description)

    try:
        resp = requests.get(
            f"{BACKEND_URL}/services",
            params={"search": search_key, "limit": 1, "isActive": True},
            timeout=3,
        )
        if resp.status_code == 200:
            data = resp.json().get("data", [])
            if data:
                return data[0]["id"], data[0].get("serviceGroupId")

        # Fallback: any active service
        resp2 = requests.get(
            f"{BACKEND_URL}/services",
            params={"limit": 1, "isActive": True},
            timeout=3,
        )
        if resp2.status_code == 200:
            data2 = resp2.json().get("data", [])
            if data2:
                logger.warning(
                    "resolve_service_id: no match for '%s', using fallback id=%s",
                    search_key, data2[0].get("id"),
                )
                return data2[0]["id"], data2[0].get("serviceGroupId")

    except Exception as exc:
        logger.error("resolve_service_id failed: %s", exc)

    raise RuntimeError("Không thể lấy thông tin dịch vụ từ hệ thống để tạo đơn.")


# ── Conversational booking response builder ───────────────────────────────────

def build_booking_response(query: str, history: List[Dict]) -> Optional[str]:
    """
    Decide what to say next in the booking flow.

    Returns:
      - None               : query has no booking intent → let LLM handle
      - text string        : ask for missing info / show summary for confirmation
      - CALL_TOOL string   : all info present + confirmed → ready to execute
    """
    # Hard stop: user explicitly said no
    if detect_negation(query):
        return None

    has_intent = detect_booking_intent(query) or detect_confirmation(query)
    if not has_intent:
        # Inherit intent from history if:
        # 1. Recent assistant message asked for contact info (mid-booking), OR
        # 2. A recent user turn had booking intent AND current query has contact-like data
        _ASK_CONTACT_HINTS = ["họ tên", "số điện thoại", "địa chỉ cần sửa",
                               "xin họ tên", "xin thêm"]
        _BOOKING_INVITE_HINTS = ["hỗ trợ đặt lịch", "đặt lịch không", "want to book",
                                  "would you like", "xác nhận đặt lịch"]
        from booking.extractor import extract_booking_from_text as _ex
        _cur = _ex(query)
        _has_contact_data = bool(_cur.get("phone") or _cur.get("name") or _cur.get("address"))

        for turn in reversed(history[-6:]):
            role = turn.get("role", "")
            content = turn.get("content", "")
            # Assistant was asking for contact info → only inherit if user provides contact data
            if role == "assistant" and any(h in content.lower() for h in _ASK_CONTACT_HINTS):
                if _has_contact_data:
                    has_intent = True
                break  # stop looking regardless — either we inherit or the flow was interrupted
            # Assistant invited to book AND current query has contact data
            if role == "assistant" and any(h in content.lower() for h in _BOOKING_INVITE_HINTS):
                if _has_contact_data:
                    has_intent = True
                    break
            # User previously expressed booking intent AND current query looks like contact/confirm
            if role == "user" and detect_booking_intent(content):
                if _has_contact_data or detect_confirmation(query):
                    has_intent = True
                break

    if not has_intent:
        return None

    info = merge_booking_info(query, history)
    missing = []
    if not info.get("name"):    missing.append("họ tên")
    if not info.get("phone"):   missing.append("số điện thoại")
    if not info.get("address"): missing.append("địa chỉ cần sửa")

    if missing:
        if len(missing) == 3:
            return "Dạ mình hỗ trợ bạn đặt lịch được ạ. Bạn cho Fixago xin họ tên, số điện thoại và địa chỉ cần sửa nhé."
        return "Dạ cho mình xin thêm " + ", ".join(missing) + " nhé."

    if detect_confirmation(query):
        issue = info.get("issue") or "Khách hàng yêu cầu thợ đến kiểm tra"
        return (
            f'CALL_TOOL: create_booking(name="{info["name"]}", '
            f'phone="{info["phone"]}", '
            f'address="{info["address"]}", '
            f'description="{issue}")'
        )

    # All info present but not confirmed yet — show summary
    return (
        f"Tên: {info['name']}\n"
        f"SĐT: {info['phone']}\n"
        f"Địa chỉ: {info['address']}\n"
        f"Vấn đề: {info.get('issue', '')}\n"
        "Bạn xác nhận đặt lịch với thông tin này nhé?"
    )


# ── Booking execution ─────────────────────────────────────────────────────────

def execute_create_booking(
    name: str,
    phone: str,
    address: str,
    description: str,
    used_tools: List[str],
) -> str:
    """Call POST /bookings and return a user-facing confirmation string."""
    used_tools.append(
        f'Thực thi Tool [Backend API]: Tạo đơn đặt lịch cho "{name}", '
        f'sđt "{phone}", địa chỉ "{address}" với lỗi "{description}"...'
    )

    if not phone:
        return "Dạ mình còn thiếu số điện thoại để tạo lịch. Bạn cho mình xin số điện thoại liên hệ nhé."

    try:
        service_id, _ = resolve_service_id(description)
        payload = {
            "guestPhone":   phone,
            "contactName":  name,
            "contactPhone": phone,
            "address":      {"addressLine": address},
            "priority":     0,
            "customerNote": description,
            "details":      [{"serviceId": service_id, "quantity": 1}],
        }
        resp = requests.post(f"{BACKEND_URL}/bookings", json=payload, timeout=5)

        if resp.status_code in (200, 201):
            booking_code = resp.json().get("bookingCode", "N/A")
            return (
                f"Đặt lịch thành công rồi ạ! Mã đơn: {booking_code}. "
                f"Khách hàng: {name} | SĐT: {phone} | Địa chỉ: {address}. "
                f"Vấn đề: {description}. "
                "Thợ Fixago sẽ liên hệ sớm để hỗ trợ bạn nhé."
            )

        return f"Xin lỗi, hiện mình không thể tạo đơn lúc này. Lỗi: {resp.text[:200]}"

    except Exception as exc:
        return f"Xin lỗi, hiện mình không thể tạo đơn lúc này. Lỗi: {exc}"


def handle_create_booking(call_str: str, used_tools: List[str]) -> str:
    """
    Parse a CALL_TOOL create_booking(...) string and execute the booking.
    Accepts both legacy text-mode strings and forwarded native tool results.
    """
    def _parse(pattern, text, default=""):
        m = re.search(pattern, text)
        return m.group(1).strip() if m else default

    name        = _parse(r'name="([^"]*)"',        call_str, "Khách hàng")
    phone       = _parse(r'phone="([^"]*)"',       call_str)
    address     = _parse(r'address="([^"]*)"',     call_str, "Chưa cung cấp")
    description = _parse(r'description="([^"]*)"', call_str, "Khách hàng yêu cầu thợ đến kiểm tra")

    return execute_create_booking(name, phone, address, description, used_tools)


def repair_booking_tool_call(answer: str, query: str, history: List[Dict]) -> str:
    """
    If the model forgot to emit CALL_TOOL but all booking info is present
    and the user confirmed, synthesize the CALL_TOOL string so execution proceeds.
    """
    if "CALL_TOOL" in answer:
        return answer

    from booking.extractor import extract_booking_from_text
    extracted = extract_booking_from_text(answer)
    merged    = (
        extracted if extracted.get("name") and extracted.get("phone") and extracted.get("address")
        else merge_booking_info(query, history)
    )

    if (merged.get("name") and merged.get("phone") and merged.get("address")
            and detect_confirmation(query)):
        issue = merged.get("issue") or query
        return (
            f'CALL_TOOL: create_booking(name="{merged["name"]}", '
            f'phone="{merged["phone"]}", '
            f'address="{merged["address"]}", '
            f'description="{issue}")'
        )

    return answer
