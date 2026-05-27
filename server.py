#!/usr/bin/env python3
"""
server.py
---------
Flask entry point for the Fixago RAG server.

Responsibilities:
  - HTTP routes (ingest, retrieve, query)
  - Session management (load / save via PomaiCache)
  - Orchestration: decide which path to take (booking / tool / LLM)
  - Prompt building + response caching

All business logic lives in dedicated modules:
  booking/extractor.py   — extract & merge booking fields from text
  booking/handler.py     — booking flow, create_booking execution
  tools/handlers.py      — get_groups, get_services, get_promotions
  llm_client/client.py   — LLM calls (plain, tool-calling, summarize)
  db/                    — vector store + cache (via rag_engine facade)
"""
import hashlib
import json
import os
import re
import uuid

from dotenv import load_dotenv
from flask import Flask, jsonify, request, send_file

import rag_engine
from booking.extractor import detect_confirmation, detect_negation, merge_booking_info
from booking.handler import (
    build_booking_response,
    handle_create_booking,
    normalize_service_search,
    repair_booking_tool_call,
)
from llm_client.client import (
    llm_chat,
    llm_chat_with_tools,
    llm_summarize,
    load_grammar,
)
from tools.handlers import handle_get_groups, handle_get_promotions, handle_get_services

load_dotenv()

# ── Feature flags ─────────────────────────────────────────────────────────────
# Set ENABLE_NATIVE_TOOL_CALL=1 when cheese-server is started with --jinja.
ENABLE_NATIVE_TOOL_CALL = os.environ.get("ENABLE_NATIVE_TOOL_CALL", "0") in ("1", "true", "yes")

app = Flask(__name__)


# ── Session management ────────────────────────────────────────────────────────

class SessionManager:
    _TTL_MS = 7_200_000  # 2 hours

    @staticmethod
    def get(session_id: str) -> dict:
        if not session_id:
            return {"history": [], "booking_state": {}}
        try:
            val = rag_engine.cache.get(f"session:{session_id}")
            if val:
                return json.loads(val.decode("utf-8"))
        except Exception as exc:
            print(f"Session load failed: {exc}")
        return {"history": [], "booking_state": {}}

    @staticmethod
    def save(session_id: str, data: dict):
        if not session_id:
            return
        try:
            rag_engine.cache.set(
                f"session:{session_id}",
                json.dumps(data).encode("utf-8"),
                ttl_ms=SessionManager._TTL_MS,
            )
        except Exception as exc:
            print(f"Session save failed: {exc}")


# ── Prompt helpers ────────────────────────────────────────────────────────────

def _load_system_prompt() -> str:
    try:
        with open("system_prompt.txt", "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return "Bạn là Trợ lý AI của Fixago. Luôn trả lời bằng tiếng Việt, lịch sự, ngắn gọn và hữu ích."


def _build_system_prompt(base: str, booking_state: dict) -> str:
    """
    In native tool-call mode: return the base prompt unchanged (model gets
    tool schemas via the API payload).
    In legacy text mode: append few-shot CALL_TOOL examples + session state.
    """
    if ENABLE_NATIVE_TOOL_CALL:
        return base

    examples = (
        "\n\nEXAMPLES:\n"
        "Q: Fixago có dịch vụ gì?\n"
        "A: CALL_TOOL: get_groups()\n\n"
        "Q: Sửa ống nước giá bao nhiêu?\n"
        "A: CALL_TOOL: get_services(search=\"nước\")\n\n"
        "Q: Có khuyến mãi hay giảm giá gì không?\n"
        "A: CALL_TOOL: get_promotions()\n\n"
        "Q: Sửa chập điện bao nhiêu tiền?\n"
        "A: CALL_TOOL: get_services(search=\"điện\")\n\n"
        "Q: Tôi muốn đặt thợ sửa điện\n"
        "A: Dạ mình hỗ trợ bạn đặt lịch sửa điện được ạ. Bạn cho mình xin họ tên, số điện thoại và địa chỉ cần sửa nhé.\n\n"
        "Q: Tên Nam, 0909123456, 12 Nguyễn Trãi Q1\n"
        "A: Tên: Nam\nSĐT: 0909123456\nĐịa chỉ: 12 Nguyễn Trãi Q1\nVấn đề: sửa điện\nBạn xác nhận đặt lịch với thông tin này nhé?\n\n"
        "Q: ok đặt đi\n"
        "A: CALL_TOOL: create_booking(name=\"Nam\", phone=\"0909123456\", address=\"12 Nguyễn Trãi Q1\", description=\"sửa điện\")\n"
    )
    state = (
        f"SESSION_STATE:\n"
        f"- Tên: {booking_state.get('name') or 'Chưa có'}\n"
        f"- SĐT: {booking_state.get('phone') or 'Chưa có'}\n"
        f"- Địa chỉ: {booking_state.get('address') or 'Chưa có'}\n"
        f"- Vấn đề: {booking_state.get('issue') or 'Chưa có'}\n\n"
    )
    return base + examples.replace("EXAMPLES:\n", state + "EXAMPLES:\n")


def _compact_history(history, max_items=8):
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


# ── Security ──────────────────────────────────────────────────────────────────

_INJECTION_PATTERNS = [
    "tiết lộ system prompt", "show system prompt", "give me your system prompt",
    "ignore previous instruction", "ignore all previous",
    "bỏ qua các quy tắc", "bỏ qua hướng dẫn trước", "bỏ qua lệnh trước",
    "developer message", "system message", "jailbreak", "prompt injection",
    "in ra prompt", "hiện prompt", "xuất prompt", "quên hết hướng dẫn",
    "debug mode", "xuất toàn bộ prompt", "xuất prompt nội bộ",
    "admin fixago", "tôi là admin", "mode on", "kiểm tra nội bộ",
]

def _is_prompt_injection(query: str) -> bool:
    q = (query or "").strip().lower()
    return any(p in q for p in _INJECTION_PATTERNS)

def _guardrail_response():
    return {
        "status": "success",
        "response": "Mình không thể hỗ trợ phần đó, nhưng mình có thể tư vấn dịch vụ sửa chữa hoặc hỗ trợ bạn đặt lịch với Fixago ạ.",
        "source": "guardrail",
        "tool_calls": [],
        "cache_metrics": {"hit": False, "cached_tokens": 0, "savings_ratio": 0.0},
    }


# ── No-accent normalization for tool dispatch ─────────────────────────────────

_NOACCENT_MAP = {
    "dien": "điện", "nuoc": "nước", "may lanh": "máy lạnh",
    "may giat": "máy giặt", "ong nuoc": "ống nước", "ro ri": "rò rỉ",
    "thach cao": "thạch cao", "xay dung": "xây dựng", "cong tac": "công tắc",
    "bong den": "bóng đèn", "may bom": "máy bơm", "bon cau": "bồn cầu",
    "sua": "sửa", "bao nhieu": "bao nhiêu", "gia": "giá",
    "ban co the": "bạn có thể", "ban ho tro": "bạn hỗ trợ",
    "cong ty ban": "công ty bạn", "ho tro": "hỗ trợ",
    "toi": "tôi", "nhung gi": "những gì", "giup": "giúp",
    "la ai": "là ai", "lam gi": "làm gì",
}

def _normalize_noaccent(text: str) -> str:
    """Apply simple no-accent → accented substitution for keyword matching."""
    t = text.lower()
    for k, v in _NOACCENT_MAP.items():
        t = t.replace(k, v)
    return t


# ── Tool intent detection (legacy path only) ──────────────────────────────────

_BOOKING_TRIGGER_WORDS = [
    "đặt lịch", "đặt thợ", "gọi thợ", "book thợ", "book lịch",
    "hẹn thợ", "cử thợ", "cho thợ", "hỗ trợ đặt",
]

def _detect_tool_intent(query: str):
    # Normalize no-accent input before matching
    q = _normalize_noaccent((query or "").strip().lower())

    # If explicit booking trigger, don't dispatch as price tool
    # (build_booking_response will handle it)
    is_booking_trigger = any(k in q for k in _BOOKING_TRIGGER_WORDS)
    if is_booking_trigger and not any(k in q for k in ["giá", "bao nhiêu", "how much", "price", "cost"]):
        return None

    # Promotion — highest priority, check before service
    if any(k in q for k in [
        "khuyến mãi", "giảm giá", "ưu đãi", "voucher", "mã giảm", "coupon",
        "discount", "promotion", "mã khuyến", "giảm %", "mã giảm",
    ]):
        return "CALL_TOOL: get_promotions()"

    # EN service-list queries
    if any(k in q for k in [
        "what service", "what can you", "what do you", "what does fixago",
        "services do you", "services does fixago", "services available",
    ]):
        return "CALL_TOOL: get_groups()"

    # VI service-list queries
    if any(k in q for k in [
        "dịch vụ gì", "có dịch vụ", "những dịch vụ", "nhóm dịch vụ",
        "fixago làm gì", "bên bạn làm gì", "có sửa gì", "provide",
    ]):
        return "CALL_TOOL: get_groups()"

    service_map = {
        "điện":      ["điện", "chập", "ổ cắm", "bóng đèn", "công tắc", "tủ điện",
                      "aptomat", "cb", "dây điện", "electrical", "electric", "wire",
                      "circuit", "breaker", "trạm sạc", "năng lượng mặt trời"],
        "nước":      ["nước", "ống", "rò", "nghẹt", "vòi", "bồn cầu", "máy bơm",
                      "van", "lavabo", "thoát nước", "pipe", "plumb", "leak", "water",
                      "drain", "clog", "sewage"],
        "máy lạnh":  ["máy lạnh", "điều hòa", "tủ lạnh", "nạp gas", "gas lạnh",
                      "không lạnh", "điện lạnh", "máy giặt", "refrigerat",
                      "air conditioner", "air con", "aircon", "ac unit", "washing machine",
                      "washer", "dryer", "freezer"],
        "xây dựng":  ["sơn", "chống thấm", "ốp lát", "gạch", "tường", "ban công",
                      "xây dựng", "cải tạo", "thấm", "dột", "renovation", "paint",
                      "waterproof", "tile", "cement"],
        "thạch cao": ["thạch cao", "trần thạch cao", "vách ngăn", "plasterboard",
                      "gypsum", "drywall", "ceiling board"],
    }
    intent_words = [
        "giá", "bao nhiêu", "sửa", "lắp", "thay", "bảo dưỡng", "vệ sinh",
        "kiểm tra", "báo giá", "hỏng", "lỗi", "dịch vụ", "tư vấn",
        "how much", "repair", "fix", "install", "replace", "cost", "price",
        "service", "maintenance", "check",
        "làm gì", "phải làm", "xử lý", "khắc phục", "nguy hiểm không",
        "cần làm", "nên làm", "bị", "không lên", "không hoạt động",
        "không mát", "không lạnh", "rò", "rỉ", "nghẹt", "tắc", "vỡ",
    ]

    if any(w in q for w in intent_words):
        for key, kws in service_map.items():
            if any(kw in q for kw in kws):
                return f'CALL_TOOL: get_services(search="{key}")'

    # Short single-service reply (e.g. "Điện", "Nước", "Máy lạnh") — user clarifying service type
    if len(q.split()) <= 3:
        for key, kws in service_map.items():
            if any(kw == q.strip() or q.strip().startswith(kw) for kw in kws):
                return f'CALL_TOOL: get_services(search="{key}")'

    return None


# ── Intent token matcher (fuzzy, accent-tolerant) ────────────────────────────

def _has_tokens(text: str, *token_groups) -> bool:
    """
    Returns True if the text contains at least one token from EVERY group.
    Each group is a list of synonymous keywords (OR within group, AND across groups).
    Accent-insensitive: checks both raw and normalized text.

    Example:
        _has_tokens(q, ["giờ","thời gian","schedule"], ["làm việc","hoạt động","open"])
        → True if text has (giờ OR thời gian OR schedule) AND (làm việc OR hoạt động OR open)
    """
    t = text.lower()
    # Also check unaccented form for no-accent inputs
    t2 = _normalize_noaccent(t)
    for group in token_groups:
        if not any(k in t or k in t2 for k in group):
            return False
    return True


# ── Static fallback (no LLM needed) ──────────────────────────────────────────

def _static_fallback(query: str) -> str:
    """
    Only intercepts what the LLM truly cannot handle correctly:
    - Pure contact data mid-booking (no question keywords)
    - Safety-critical situations (fire/electrocution risk)
    - Hard facts the model might hallucinate (working hours = 24/7)
    - Off-topic guardrail

    Everything else (intro, comparison, quality, policy...) → LLM with 3B model.
    """
    raw_q = (query or "").lower()
    q = _normalize_noaccent(raw_q)

    # Don't intercept pure contact data mid-booking
    from booking.extractor import extract_booking_from_text as _ex_check
    _contact = _ex_check(query)
    _is_contact_reply = (
        (_contact.get("phone") or _contact.get("name"))
        and not any(kw in raw_q for kw in ["?", "bao nhiêu", "giá", "gì vậy", "là gì",
                                            "tư vấn", "hỏi", "khuyến mãi", "dịch vụ",
                                            "tên gì", "ở đâu", "như thế nào", "ra sao",
                                            "giới thiệu", "là ai", "làm gì", "công ty"])
    )
    if _is_contact_reply:
        return ""

    _has_price_intent = any(k in q for k in ["bao nhiêu", "giá", "khuyến mãi", "ưu đãi", "how much", "price"])
    _has_promo_intent = any(k in q for k in ["khuyến mãi", "ưu đãi", "giảm giá", "discount", "promotion"])

    # ── Safety: dangerous situations — must not let LLM fumble these ─────────
    if any(k in q for k in ["tóe lửa", "chạm điện", "rò gas", "mùi gas", "cháy nổ"]):
        return (
            "Dạ tình trạng này nguy hiểm — bạn ngắt nguồn điện/khóa van gas ngay nếu an toàn, "
            "tránh tự sửa. Fixago có thể cử thợ đến kiểm tra. Bạn muốn đặt lịch không ạ?"
        )

    # ── Hard fact: working hours (model tends to say "tôi là AI không có lịch") ──
    _HOURS_TOKENS = ["giờ làm", "thời gian làm", "thoi gian lam", "gio lam viec",
                     "working hour", "lam viec may gio", "ban đêm", "ban dem",
                     "cuối tuần", "cuoi tuan", "chủ nhật", "chu nhat",
                     "ngày lễ", "ngay le", "24/7", "suốt ngày"]
    _hours_q = (
        any(k in raw_q for k in _HOURS_TOKENS)
        or _has_tokens(raw_q,
            ["giờ", "thời gian", "thoi gian", "lúc nào", "luc nao", "open"],
            ["làm việc", "lam viec", "hoạt động", "hoat dong", "phục vụ", "phuc vu"])
    )
    if _hours_q:
        if _has_tokens(raw_q, ["dịch vụ", "hỗ trợ", "làm gì", "dich vu"]):
            return (
                "Dạ Fixago hoạt động 24/7, kể cả cuối tuần và ngày lễ. "
                "Dịch vụ gồm sửa điện, nước, máy lạnh, xây dựng và thạch cao. "
                "Bạn cần hỗ trợ hạng mục nào ạ?"
            )
        return (
            "Dạ Fixago hoạt động 24/7, kể cả cuối tuần và ngày lễ — "
            "bạn đặt lịch bất kỳ lúc nào, thợ sẽ liên hệ xác nhận thời gian sớm nhất nhé."
        )

    # ── Off-topic guardrail ───────────────────────────────────────────────────
    if any(k in q for k in ["nấu phở", "tình yêu", "love poem", "thơ tình", "bài thơ",
                              "nấu ăn", "recipe", "cooking", "bóng đá", "football",
                              "thời tiết", "weather", "tin tức", "news"]):
        return (
            "Dạ mình chỉ hỗ trợ dịch vụ sửa chữa nhà của Fixago thôi ạ 😊 "
            "Bạn cần tư vấn điện, nước, máy lạnh hay xây dựng không?"
        )

    # Ambiguous "cái này" / "nhìn giúp" — can't price without details
    if any(k in q for k in ["cái này", "nhìn giúp", "xem giúp", "xem cái này"]):
        return (
            "Dạ mình cần biết tình trạng cụ thể để tư vấn chi phí. "
            "Bạn mô tả lỗi hoặc hạng mục cần sửa để mình tư vấn nhé?"
        )

    # Short ambiguous "Hỏng rồi" / general damage statement with no service mentioned
    _DAMAGE_WORDS = ["hỏng rồi", "hỏng hết", "bị hỏng", "hư rồi", "hư hết"]
    _SERVICE_WORDS = ["điện", "nước", "máy lạnh", "máy giặt", "ống", "vòi", "chập",
                      "rò", "nghẹt", "thạch cao", "sơn", "xây"]
    if any(k in q for k in _DAMAGE_WORDS) and not any(s in q for s in _SERVICE_WORDS):
        return (
            "Dạ bạn cho mình biết thiết bị hay hạng mục nào bị hỏng để mình tư vấn phù hợp nhé? "
            "(ví dụ: điện, nước, máy lạnh, máy giặt...)"
        )

    # Single-word "Điện" response during a conversation where service is ambiguous
    # (handled by routing to price tool if standalone in _detect_tool_intent)

    # Electrical emergency — route to booking prompt
    _ELECTRIC_NOISE = ["chập điện", "cháy điện", "điện bị", "hở điện"]
    _has_booking_intent = any(k in q for k in ["đặt lịch", "gọi thợ", "đặt thợ", "book thợ", "hẹn thợ"])
    if not _has_booking_intent and any(k in q for k in _ELECTRIC_NOISE):
        return (
            "Dạ tình trạng chập điện cần xử lý ngay. Fixago có thể cử thợ điện đến kiểm tra và sửa an toàn. "
            "Bạn muốn mình hỗ trợ đặt lịch không ạ?"
        )

    return ""


# ── Orchestration ─────────────────────────────────────────────────────────────

def _run_native_tool_path(query: str, history: list, messages: list, used_tools: list) -> str:
    """Native function-calling path (cheese-server --jinja required)."""
    booking_resp = build_booking_response(query, history)

    if booking_resp and "CALL_TOOL: create_booking" in booking_resp:
        return handle_create_booking(booking_resp, used_tools)

    if booking_resp and "CALL_TOOL" not in booking_resp:
        return booking_resp

    tool_name, tool_result, raw_msg = llm_chat_with_tools(messages, temperature=0.0)

    if tool_name == "get_groups":
        messages.append({"role": "assistant", "content": None, "tool_calls": raw_msg.get("tool_calls")})
        return handle_get_groups(messages, used_tools)

    if tool_name == "get_services":
        search = normalize_service_search(tool_result.get("search", ""))
        messages.append({"role": "assistant", "content": None, "tool_calls": raw_msg.get("tool_calls")})
        return handle_get_services(search, messages, used_tools)

    if tool_name == "get_promotions":
        messages.append({"role": "assistant", "content": None, "tool_calls": raw_msg.get("tool_calls")})
        return handle_get_promotions(messages, used_tools)

    if tool_name == "create_booking":
        if detect_confirmation(query):
            n, p, a, d = (
                tool_result.get("name", ""),
                tool_result.get("phone", ""),
                tool_result.get("address", ""),
                tool_result.get("description", ""),
            )
            fake = f'CALL_TOOL: create_booking(name="{n}", phone="{p}", address="{a}", description="{d}")'
            return handle_create_booking(fake, used_tools)

        # All fields present but not confirmed — show summary
        info = merge_booking_info(query, history)
        info.update({k: v for k, v in tool_result.items() if v})
        return (
            f"Tên: {info.get('name') or tool_result.get('name', '?')}\n"
            f"SĐT: {info.get('phone') or tool_result.get('phone', '?')}\n"
            f"Địa chỉ: {info.get('address') or tool_result.get('address', '?')}\n"
            f"Vấn đề: {info.get('issue') or tool_result.get('description', '?')}\n"
            "Bạn xác nhận đặt lịch với thông tin này nhé?"
        )

    # No tool call — plain text reply
    return tool_result


def _split_questions(query: str) -> list[str]:
    """
    Split a multi-question message into individual sub-questions.
    Returns [query] unchanged if no split is needed.

    Handles patterns like:
      "Giá điện bao nhiêu? Còn nước thì sao? Có KM không?"
      "Fixago làm gì, giá ra sao, có KM không"
      "Sửa máy lạnh bao nhiêu và thời gian làm việc thế nào"
    """
    import re as _re
    raw = (query or "").strip()

    # Split on sentence-ending punctuation followed by a capital/word
    parts = _re.split(r'(?<=[?!])\s+(?=[A-ZÀ-Ỹa-zà-ỹ])', raw)
    if len(parts) >= 2:
        return [p.strip() for p in parts if p.strip()]

    # Split on ", còn ", "; ", comma between distinct question fragments
    parts = _re.split(
        r',\s*(?:còn|ngoài ra|thêm nữa|đồng thời)\s+|;\s+',
        raw, flags=_re.IGNORECASE
    )
    if len(parts) >= 2:
        return [p.strip() for p in parts if p.strip()]

    # Split on plain commas when each segment has its own question signal
    _Q_SIGNALS2 = ["giá", "bao nhiêu", "gì", "sao", "thế nào", "ra sao",
                   "không", "có", "làm gì", "dịch vụ", "km", "khuyến mãi"]
    comma_parts = [p.strip() for p in raw.split(",") if p.strip()]
    if len(comma_parts) >= 2 and all(
        any(s in p.lower() for s in _Q_SIGNALS2) for p in comma_parts
    ):
        return comma_parts

    # Split on " và " only when both sides look like distinct questions
    # (each side has a service keyword or question word)
    _Q_SIGNALS = ["giá", "bao nhiêu", "sửa", "có", "thế nào", "ra sao",
                  "như thế", "mấy giờ", "thời gian", "khuyến mãi", "dịch vụ"]
    and_parts = _re.split(r'\s+và\s+', raw, flags=_re.IGNORECASE)
    if len(and_parts) >= 2:
        if all(any(s in p.lower() for s in _Q_SIGNALS) for p in and_parts):
            return [p.strip() for p in and_parts if p.strip()]

    return [raw]


def _detect_multi_service(query: str, first_tool: str, messages: list, used_tools: list):
    """
    If the query mentions two different service categories with a clear separator,
    call both APIs and return a combined answer string directly.
    Otherwise return first_tool unchanged.
    """
    q = _normalize_noaccent((query or "").lower())
    service_map = {
        "điện":     ["điện", "chập", "ổ cắm", "bóng đèn", "công tắc", "aptomat", "dây điện"],
        "nước":     ["nước", "ống", "rò", "nghẹt", "vòi", "bồn cầu", "máy bơm", "lavabo"],
        "máy lạnh": ["máy lạnh", "điều hòa", "tủ lạnh", "không lạnh", "máy giặt"],
        "xây dựng": ["sơn", "chống thấm", "ốp lát", "tường", "ban công", "xây dựng", "dột"],
        "thạch cao":["thạch cao", "trần", "vách ngăn"],
    }
    matched = []
    for key, kws in service_map.items():
        if any(kw in q for kw in kws):
            matched.append(key)

    if len(matched) < 2:
        return first_tool

    _MULTI_SEPARATORS = [" còn ", " và giá ", " với giá ", " or ", " and ",
                         "bao nhiêu,", "bao nhiêu còn", "giá còn", "ngoài ra", "; "]
    if not any(sep in q for sep in _MULTI_SEPARATORS):
        return first_tool

    parts = []
    for svc in matched[:2]:
        result = handle_get_services(svc, messages, used_tools)
        lines = [l for l in result.split("\n") if l.strip() and "muốn mình" not in l]
        parts.append(f"**{svc.title()}:** " + " ".join(lines[:3]))

    return "\n\n".join(parts) + "\n\nChi phí thực tế thợ sẽ báo rõ trước khi làm. Bạn muốn mình hỗ trợ đặt lịch không ạ?"


def _resolve_tool_data(sub_query: str, messages: list, used_tools: list) -> str:
    """
    For a single sub-question, fetch backend data if needed and return
    a data string to inject into the LLM prompt, or "" if no tool needed.
    """
    tool = _detect_tool_intent(sub_query)
    if not tool:
        return ""

    if "get_groups" in tool:
        return handle_get_groups(messages, used_tools)

    if "get_promotions" in tool:
        return handle_get_promotions(messages, used_tools)

    if "get_services" in tool:
        m = re.search(r'search="([^"]*)"', tool)
        search = normalize_service_search(m.group(1) if m else sub_query)
        return handle_get_services(search, messages, used_tools)

    return ""


def _execute_tool(tool_str: str, messages: list, used_tools: list) -> str:
    """Execute a CALL_TOOL string and return the result."""
    if "get_groups" in tool_str:
        return handle_get_groups(messages, used_tools)
    if "get_promotions" in tool_str:
        return handle_get_promotions(messages, used_tools)
    if "get_services" in tool_str:
        m = re.search(r'search="([^"]*)"', tool_str)
        search = normalize_service_search(m.group(1) if m else "")
        return handle_get_services(search, messages, used_tools)
    return ""


def _run_legacy_tool_path(query: str, history: list, messages: list, used_tools: list) -> str:
    """
    Main orchestration path.

    Flow:
      1. Static guardrails (safety / hours / off-topic) → instant return
      2. Booking confirmation / mid-flow → deterministic booking handler
      3. Multi-service (two APIs needed) → stitch + return
      4. Split multi-question → fetch each tool's data, inject all into one LLM call
      5. Single tool → fetch data, inject as context, LLM summarizes naturally
      6. No tool → pure LLM with RAG context
    """
    # 1. Static guardrails
    static_early = _static_fallback(query)
    if static_early:
        return static_early

    # 2. Booking flow — fully deterministic
    _hint_tool = _detect_tool_intent(query)
    _has_service_hint = _hint_tool and "get_services" in str(_hint_tool)
    if not detect_negation(query) and not _has_service_hint:
        booking_resp = build_booking_response(query, history)
        if booking_resp:
            booking_resp = repair_booking_tool_call(booking_resp, query, history)
            if "create_booking" in booking_resp.lower():
                return handle_create_booking(booking_resp, used_tools)
            return booking_resp  # asking for info or showing summary

    # 3. Multi-service shortcut
    multi_result = _detect_multi_service(query, _hint_tool, messages, used_tools)
    if multi_result and multi_result != _hint_tool:
        return multi_result

    # 4 & 5. Split questions, fetch each tool's data, inject all into LLM
    sub_questions = _split_questions(query)
    tool_blocks: list[str] = []

    for sub_q in sub_questions:
        tool = _detect_tool_intent(sub_q)
        if tool and tool.startswith("CALL_TOOL:"):
            data = _execute_tool(tool, messages, used_tools)
            if data:
                tool_blocks.append(data)

    if tool_blocks:
        # Inject all fetched data so the model answers every part naturally
        tool_context = "\n\n---\n".join(tool_blocks)
        enriched = (
            f"{query}\n\n"
            f"[Dữ liệu hệ thống:]\n{tool_context}"
        )
        llm_messages = messages[:-1] + [{"role": "user", "content": enriched}]
        return llm_chat(llm_messages, temperature=0.2)

    # 6. Pure LLM (conversational, comparison, identity, etc.)
    return llm_chat(messages, temperature=0.2)


def _run_legacy_fast_path(query: str, history: list, messages: list, used_tools: list):
    """
    Pre-RAG fast path: handle static + booking + deterministic tools without
    calling the LLM. Returns None to signal the main path should continue.
    """
    # Static guardrails
    static_early = _static_fallback(query)
    if static_early:
        return static_early

    # Booking — fully deterministic, no LLM needed
    _hint_tool = _detect_tool_intent(query)
    _has_service_hint = _hint_tool and "get_services" in str(_hint_tool)
    if not detect_negation(query) and not _has_service_hint:
        booking_resp = build_booking_response(query, history)
        if booking_resp:
            booking_resp = repair_booking_tool_call(booking_resp, query, history)
            if "create_booking" in booking_resp.lower():
                return handle_create_booking(booking_resp, used_tools)
            return booking_resp

    # Multi-service stitched response
    multi_result = _detect_multi_service(query, _hint_tool, messages, used_tools)
    if multi_result and multi_result != _hint_tool:
        return multi_result

    # Everything else needs the LLM — signal to continue
    return None


def _persist_session(session_id: str, session: dict, query: str, answer: str):
    session["history"].append({"role": "user",      "content": query})
    session["history"].append({"role": "assistant", "content": answer})
    session["history"]       = _compact_history(session["history"], max_items=8)
    session["booking_state"] = merge_booking_info(query, session["history"])
    SessionManager.save(session_id, session)


# ── Flask routes ──────────────────────────────────────────────────────────────

@app.route("/", methods=["GET"])
def index():
    return send_file("demo.html")


@app.route("/api/v1/rag/ingest", methods=["POST"])
def ingest():
    data   = request.json or {}
    doc_id = data.get("doc_id")
    text   = data.get("text")
    if doc_id is None or not text:
        return jsonify({"status": "error", "message": "Missing 'doc_id' or 'text'"}), 400
    try:
        rag_engine.ingest_document(int(doc_id), text)
        return jsonify({"status": "success", "message": f"Document {doc_id} ingested successfully"})
    except Exception as exc:
        return jsonify({"status": "error", "message": str(exc)}), 500


@app.route("/api/v1/rag/retrieve", methods=["POST"])
def retrieve():
    data  = request.json or {}
    query = data.get("query")
    top_k = data.get("top_k", 5)
    if not query:
        return jsonify({"status": "error", "message": "Missing 'query'"}), 400
    try:
        context = rag_engine.retrieve_context(rag_engine.normalize_query(query), top_k=int(top_k))
        return jsonify({"status": "success", "context": context})
    except Exception as exc:
        return jsonify({"status": "error", "message": str(exc)}), 500


@app.route("/api/v1/rag/query", methods=["POST"])
def query_rag():
    data      = request.json or {}
    query     = data.get("query")
    use_cache = data.get("use_cache", False)
    session_id = data.get("session_id")

    if not query:
        return jsonify({"status": "error", "message": "Missing 'query'"}), 400

    if _is_prompt_injection(query):
        return jsonify(_guardrail_response())

    try:
        # ── Session ──────────────────────────────────────────────────────────
        if not session_id:
            session_id = str(uuid.uuid4())

        session   = SessionManager.get(session_id)
        client_h  = _compact_history(data.get("history", []))
        if client_h and not session.get("history"):
            session["history"] = client_h
        history   = session.get("history", [])

        # ── System prompt ─────────────────────────────────────────────────────
        base_prompt = data.get("system_prompt", _load_system_prompt())
        system      = _build_system_prompt(base_prompt, session.get("booking_state", {}))

        # ── Fast path ─────────────────────────────────────────────────────────
        # Most production traffic is static policy, booking state, or backend
        # tools. Handle that before RAG retrieval and before any model call.
        used_tools: list = []
        if not ENABLE_NATIVE_TOOL_CALL and not use_cache:
            fast_messages = [{"role": "system", "content": system}]
            fast_messages.extend(_compact_history(history, max_items=6))
            fast_messages.append({"role": "user", "content": query})
            fast_answer = _run_legacy_fast_path(query, history, fast_messages, used_tools)
            if fast_answer is not None:
                _persist_session(session_id, session, query, fast_answer)
                return jsonify({
                    "status": "success",
                    "response": fast_answer,
                    "source": "llm",
                    "tool_calls": used_tools,
                    "cache_metrics": {"hit": False, "cached_tokens": 0, "savings_ratio": 0.0},
                })

        # ── RAG context ───────────────────────────────────────────────────────
        rag_context = ""
        try:
            rag_context = rag_engine.retrieve_context(rag_engine.normalize_query(query), top_k=3)
        except Exception as exc:
            print(f"RAG retrieval failed: {exc}")

        # ── Cache key ─────────────────────────────────────────────────────────
        history_text = "\n".join(
            f"{m.get('role')}: {m.get('content', '')}"
            for m in _compact_history(history)
        )
        cache_seed = f"System:{system}\nHistory:{history_text}\nContext:{rag_context}\nQ:{query}"
        tokens     = []
        cache_key  = ""

        if use_cache:
            try:
                tokens    = rag_engine.tokenize_text(cache_seed)
                cache_key = f"pomai_cache:response:{hashlib.sha256(cache_seed.encode()).hexdigest()}"
                cached = rag_engine.cache.get(cache_key)
                p_res  = rag_engine.cache.prompt_get(tokens) if cached else None
                if cached:
                    return jsonify({
                        "status": "success",
                        "response": cached.decode("utf-8"),
                        "source": "cache",
                        "tool_calls": [],
                        "cache_metrics": p_res or {
                            "hit": True, "cached_tokens": len(tokens), "savings_ratio": 1.0
                        },
                    })
            except Exception as exc:
                print(f"Cache lookup failed: {exc}")

        # ── Build messages ────────────────────────────────────────────────────
        messages = [{"role": "system", "content": system}]
        messages.extend(_compact_history(history, max_items=6))
        messages.append({
            "role": "user",
            "content": (
                f"Ngữ cảnh tham khảo:\n{rag_context}\n\nCâu hỏi của khách:\n{query}"
                if rag_context else query
            ),
        })

        # ── Orchestrate ───────────────────────────────────────────────────────
        answer = (
            _run_native_tool_path(query, history, messages, used_tools)
            if ENABLE_NATIVE_TOOL_CALL
            else _run_legacy_tool_path(query, history, messages, used_tools)
        )

        # ── Persist session ───────────────────────────────────────────────────
        _persist_session(session_id, session, query, answer)

        # ── Write cache ───────────────────────────────────────────────────────
        if use_cache:
            try:
                if not cache_key:
                    tokens    = rag_engine.tokenize_text(cache_seed)
                    cache_key = f"pomai_cache:response:{hashlib.sha256(cache_seed.encode()).hexdigest()}"
                rag_engine.cache.set(cache_key, answer.encode("utf-8"), ttl_ms=600_000)
                rag_engine.cache.prompt_put(tokens, answer.encode("utf-8"), ttl_ms=600_000)
            except Exception as exc:
                print(f"Cache write failed: {exc}")

        return jsonify({
            "status": "success",
            "response": answer,
            "source": "llm",
            "tool_calls": used_tools,
            "cache_metrics": {"hit": False, "cached_tokens": 0, "savings_ratio": 0.0},
        })

    except Exception as exc:
        return jsonify({"status": "error", "message": f"LLM query failed: {exc}"}), 500


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.environ.get("RAG_PORT", 8081))
    print(f"Starting RAG server on port {port}...")
    try:
        from waitress import serve
        print(f"Serving on http://0.0.0.0:{port} with Waitress (threads=20)")
        serve(app, host="0.0.0.0", port=port, threads=20)
    except ImportError:
        print("WARNING: Waitress not found. Falling back to Flask dev server.")
        app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
