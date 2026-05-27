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
    For queries that would fall through to LLM but have predictable answers,
    return a canned response to avoid LLM latency.
    Returns empty string if no static answer fits.
    """
    raw_q = (query or "").lower()
    q = _normalize_noaccent(raw_q)

    # Don't fire any static if the message is pure contact data being provided
    # (name + phone or address = user is mid-booking, not asking a question)
    from booking.extractor import extract_booking_from_text as _ex_check
    _contact = _ex_check(query)
    _is_contact_reply = (
        (_contact.get("phone") or _contact.get("name"))
        and not any(kw in q for kw in ["?", "bao nhiêu", "giá", "gì vậy", "là gì",
                                        "tư vấn", "hỏi", "khuyến mãi", "dịch vụ",
                                        "tên gì", "ở đâu", "như thế nào", "ra sao",
                                        "giới thiệu", "là ai", "làm gì", "công ty"])
    )
    if _is_contact_reply:
        return ""

    # Pre-compute intent flags used across multiple blocks
    _has_price_intent = any(k in q for k in ["bao nhiêu", "giá", "khuyến mãi", "ưu đãi", "how much", "price"])
    _has_promo_intent = any(k in q for k in ["khuyến mãi", "ưu đãi", "giảm giá", "discount", "promotion"])
    _has_booking_intent = any(k in q for k in ["đặt lịch", "gọi thợ", "đặt thợ", "book thợ", "hẹn thợ"])

    # Policy / commitment pressure
    if any(k in q for k in ["cam kết 100%", "đền 10 triệu", "chắc chắn sửa được",
                              "cam kết sửa", "cam kết không", "bảo đảm sửa"]):
        return (
            "Dạ Fixago chưa thể xác nhận kết quả trước khi thợ kiểm tra thực tế. "
            "Thợ sẽ báo rõ phương án và chi phí trước khi tiến hành để bạn quyết định nhé."
        )

    # Why Fixago vs street technician
    if any(k in q for k in ["thợ ngoài đường", "thợ tự tìm", "sao phải đặt fixago", "thay vì gọi"]):
        return (
            "Dạ với Fixago bạn được thợ đã xác minh, báo giá rõ ràng trước khi làm, "
            "và được hỗ trợ nếu có vấn đề phát sinh. Bạn muốn mình tư vấn thêm không ạ?"
        )

    # Trust / credibility question
    if any(k in q for k in ["uy tín không", "thợ vớ vẩn", "có tin được không", "chất lượng thế nào"]):
        return (
            "Dạ thợ của Fixago đều được xác minh kỹ năng và kinh nghiệm. "
            "Chi phí được báo rõ trước khi làm, không phát sinh ngoài ý muốn. "
            "Bạn muốn mình hỗ trợ đặt lịch không ạ?"
        )

    # Safety: dangerous electrical work
    if any(k in q for k in ["tự tháo", "tự sửa điện", "tóe lửa", "chạm điện"]):
        return (
            "Dạ tình trạng này khá nguy hiểm — bạn nên ngắt cầu dao điện trước, "
            "tránh tự tháo nếu chưa có kinh nghiệm. Fixago có thể cử thợ điện đến kiểm tra an toàn. "
            "Bạn muốn mình hỗ trợ đặt lịch không ạ?"
        )

    # Business hours — adaptive: single group OR two-group combos
    _HOURS_TOKENS = ["giờ làm", "thời gian làm", "thoi gian lam", "gio lam viec",
                     "working hour", "schedule", "lam viec may gio",
                     "ban đêm", "ban dem", "buổi tối", "buoi toi",
                     "cuối tuần", "cuoi tuan", "chủ nhật", "chu nhat",
                     "ngày lễ", "ngay le", "24/7", "24h", "suốt ngày", "suot ngay"]
    _hours_q = (
        any(k in raw_q for k in _HOURS_TOKENS)
        or _has_tokens(raw_q,
            ["giờ", "thời gian", "thoi gian", "may gio", "lúc nào", "luc nao", "open"],
            ["làm việc", "lam viec", "hoạt động", "hoat dong", "lam", "phục vụ", "phuc vu"])
    )
    if _hours_q:
        _also_services = _has_tokens(raw_q, ["dịch vụ", "hỗ trợ", "làm gì", "dich vu"])
        if _also_services:
            return (
                "Dạ Fixago hoạt động 24/7, kể cả cuối tuần và ngày lễ. "
                "Dịch vụ gồm sửa điện, nước, máy lạnh, xây dựng và thạch cao. "
                "Bạn cần hỗ trợ hạng mục nào ạ?"
            )
        return (
            "Dạ Fixago hoạt động 24/7, kể cả cuối tuần và ngày lễ — "
            "bạn đặt lịch bất kỳ lúc nào, thợ sẽ liên hệ xác nhận thời gian sớm nhất nhé."
        )

    # Payment method
    if any(k in q for k in ["tiền mặt", "chuyển khoản", "thanh toán", "payment", "pay"]):
        return (
            "Dạ mình chưa có thông tin đầy đủ về phương thức thanh toán. "
            "Bạn có thể hỏi trực tiếp thợ khi họ liên hệ xác nhận lịch nhé."
        )

    # VAT / invoice
    if any(k in q for k in ["hóa đơn", "vat", "invoice", "xuất hóa đơn"]):
        return (
            "Dạ mình chưa có thông tin về việc xuất hóa đơn VAT. "
            "Bạn có thể liên hệ trực tiếp Fixago để được hỗ trợ cụ thể nhé."
        )

    # Service area
    if any(k in q for k in ["cần thơ", "đà nẵng", "da nang", "hà nội", "hải phòng",
                              "khu vực", "tỉnh", "vùng", "area", "support", "region"]):
        return (
            "Dạ mình chưa có thông tin đầy đủ về khu vực hoạt động. "
            "Bạn để lại địa chỉ, Fixago sẽ kiểm tra và xác nhận có hỗ trợ được không nhé."
        )

    # Warranty — skip if query also asks for price (tool will handle that, mention warranty in passing)
    if not _has_price_intent and any(k in q for k in ["bảo hành", "warranty", "guarantee"]):
        return (
            "Dạ thông tin bảo hành phụ thuộc vào từng hạng mục. "
            "Thợ sẽ trao đổi cụ thể với bạn khi đến kiểm tra nhé. "
            "Bạn muốn mình hỗ trợ đặt lịch không ạ?"
        )

    # Delivery time / ETA
    if (any(k in q for k in ["bao lâu thợ tới", "thợ tới lúc nào", "khi nào thợ đến",
                               "how long", "how soon"])
            or re.search(r'\beta\b', q)):
        return (
            "Dạ thời gian thợ đến phụ thuộc vào lịch và khu vực. "
            "Sau khi đặt lịch, hệ thống sẽ xác nhận thời gian cụ thể với bạn nhé."
        )

    # Technician selection
    if any(k in q for k in ["chọn thợ", "thợ cụ thể", "thợ quen", "choose technician"]):
        return (
            "Dạ hiện tại Fixago sẽ điều phối thợ phù hợp nhất với yêu cầu và khu vực của bạn. "
            "Bạn muốn mình hỗ trợ đặt lịch không ạ?"
        )

    # Urgent / 5 minutes
    if any(k in q for k in ["ngay lập tức", "trong 5 phút", "ngay bây giờ", "cấp cứu", "urgent"]):
        return (
            "Dạ Fixago điều phối theo lịch — mình không thể đảm bảo thợ đến ngay trong vài phút. "
            "Bạn đặt lịch để Fixago liên hệ sắp xếp sớm nhất có thể nhé?"
        )

    # Package tiers
    if any(k in q for k in ["gói tiết kiệm", "gói tiêu chuẩn", "gói cao cấp", "package"]):
        return (
            "Dạ hiện Fixago tính giá theo từng hạng mục dịch vụ thực tế, "
            "không có gói cố định. Thợ sẽ báo giá rõ trước khi làm nhé."
        )

    # Company name / location — token-based: (tên/name/gọi là) + (công ty/fixago/bạn)
    _company_name_q = (
        _has_tokens(raw_q, ["tên", "name", "gọi là", "ten", "goi la"],
                            ["công ty", "fixago", "cong ty"])
        or _has_tokens(raw_q, ["công ty", "cong ty", "fixago"], ["ở đâu", "o dau", "where"])
        or any(k in raw_q for k in ["ten cong ty", "tên công ty", "fixago tên gì", "fixago o dau"])
    )
    if _company_name_q:
        return (
            "Dạ công ty mình tên là Fixago — nền tảng đặt thợ sửa chữa điện, nước, "
            "điện lạnh, xây dựng và thạch cao tại nhà. "
            "Bạn cần hỗ trợ hạng mục nào ạ?"
        )

    # Vague price + quality question without a service category.
    _has_service_context = any(k in q for k in [
        "điện", "nước", "máy lạnh", "điện lạnh", "máy giặt", "tủ lạnh",
        "ống", "vòi", "bồn cầu", "chập", "ổ cắm", "aptomat",
        "sơn", "chống thấm", "xây dựng", "thạch cao", "trần", "vách",
        "air conditioner", "air con", "aircon", "plumb", "pipe", "leak",
        "electrical", "electric", "refrigerat", "washing machine",
    ])
    if _has_price_intent and not _has_service_context and any(k in q for k in [
        "giá bên bạn", "giá bên mình", "giá thế nào", "giá sao",
        "tốt không", "ổn không", "uy tín không", "chất lượng không",
    ]):
        return (
            "Dạ giá của Fixago tùy theo hạng mục và tình trạng thực tế, thợ sẽ báo rõ trước khi làm. "
            "Fixago điều phối thợ phù hợp và có hỗ trợ nếu phát sinh vấn đề sau dịch vụ. "
            "Bạn cần sửa điện, nước, máy lạnh hay hạng mục nào ạ?"
        )

    # Identity — who is the bot / what can it do
    _identity_q = (
        _has_tokens(raw_q, ["bạn", "ban", "you", "mày", "mình"],
                            ["là ai", "la ai", "là gì", "la gi", "who are", "what are"])
        or _has_tokens(raw_q, ["bạn", "ban", "you"],
                               ["giúp", "hỗ trợ", "làm", "help", "giup", "ho tro"])
        or any(k in raw_q for k in ["who are you", "what can you", "how can you help"])
    )
    if _identity_q:
        return (
            "Dạ mình là Trợ lý AI của Fixago — nền tảng đặt thợ sửa chữa điện, nước, "
            "điện lạnh, xây dựng và thạch cao tại nhà. Bạn cần hỗ trợ gì không ạ?"
        )

    # Technician quality / training
    # Don't fire if query also has a price/promo intent (will be handled by tool)
    _tech_quality_q = _has_tokens(raw_q,
        ["thợ", "tho", "kỹ thuật viên", "technician", "worker"],
        ["đào tạo", "dao tao", "kinh nghiệm", "kinh nghiem", "chuyên nghiệp", "chuyen nghiep",
         "giỏi", "gioi", "tay nghề", "tay nghe", "kỹ năng", "ky nang", "skilled", "trained",
         "chất lượng", "chat luong", "uy tín", "uy tin"])
    if not _has_price_intent and _tech_quality_q:
        return (
            "Dạ thợ của Fixago đều qua kiểm tra kỹ năng và xác minh kinh nghiệm thực tế trước khi nhận việc. "
            "Không phải thợ tự do ngẫu nhiên — mỗi thợ được đánh giá và theo dõi chất lượng sau từng đơn. "
            "Bạn muốn mình tư vấn thêm hoặc hỗ trợ đặt lịch không ạ?"
        )

    # Complaint / after-service support
    if any(k in q for k in ["khiếu nại", "không hài lòng", "thợ làm sai", "làm không tốt",
                              "làm hỏng", "sửa không được", "complain", "refund", "hoàn tiền",
                              "đền bù", "trách nhiệm", "phản ánh"]):
        return (
            "Dạ nếu bạn chưa hài lòng sau khi thợ làm, bạn có thể phản ánh trực tiếp qua ứng dụng Fixago "
            "hoặc liên hệ bộ phận hỗ trợ. Fixago sẽ xem xét và có phương án xử lý phù hợp với từng trường hợp. "
            "Bạn muốn mình hỗ trợ gì thêm không ạ?"
        )

    # Comparison with competitors / street technicians
    # Don't fire if there's also a promo or price query — let tool handle that part first
    _COMPARE_TOKENS = ["so sánh", "so sanh", "ưu điểm", "uu diem", "điểm mạnh", "diem manh",
                       "lợi thế", "loi the", "advantage", "compare", "better than",
                       "different from", "tốt hơn", "tot hon", "rẻ hơn", "re hon",
                       "hơn gì", "hon gi", "khác gì", "khac gi", "khác với", "khac voi"]
    _comparison_match = (
        any(k in raw_q for k in _COMPARE_TOKENS)
        or _has_tokens(raw_q,
            ["fixago", "bên bạn", "ben ban", "công ty bạn", "cong ty ban", "dịch vụ bạn"],
            ["khác", "khac", "hơn", "hon", "so", "tốt", "tot", "bằng", "bang"])
    )
    if not _has_promo_intent and _comparison_match:
        return (
            "Dạ so với tìm thợ tự do hoặc app khác, Fixago khác biệt ở 3 điểm: "
            "① Thợ được xác minh kỹ năng và lịch sử làm việc trước khi nhận đơn. "
            "② Báo giá rõ ràng trước khi thợ bắt tay vào làm — không phát sinh ngoài ý muốn. "
            "③ Hỗ trợ sau dịch vụ nếu có vấn đề phát sinh. "
            "Bạn muốn mình tư vấn thêm hoặc đặt lịch không ạ?"
        )

    # Introduction / what is Fixago or about the company
    _intro_q = (
        _has_tokens(raw_q, ["giới thiệu", "gioi thieu", "introduce", "tell me about",
                             "về fixago", "ve fixago", "about fixago"])
        or _has_tokens(raw_q, ["fixago", "công ty", "cong ty"],
                               ["là gì", "la gi", "là ai", "la ai", "làm gì", "lam gi",
                                "hoạt động", "hoat dong", "what is", "who is"])
        or _has_tokens(raw_q, ["giới thiệu", "gioi thieu"],
                               ["công ty", "cong ty", "cty", "bạn", "ban"])
    )
    if _intro_q:
        return (
            "Dạ Fixago là nền tảng đặt thợ sửa chữa nhà uy tín — kết nối bạn với thợ điện, nước, "
            "điện lạnh, xây dựng và thạch cao đã được xác minh. "
            "Chỉ cần mô tả sự cố, Fixago điều phối thợ phù hợp, báo giá rõ trước khi làm, "
            "và hỗ trợ sau dịch vụ nếu cần. Bạn đang cần hỗ trợ hạng mục nào ạ?"
        )

    # Off-topic
    if any(k in q for k in ["nấu phở", "tình yêu", "love poem", "thơ tình", "bài thơ",
                              "nấu ăn", "recipe", "cooking", "bóng đá", "football"]):
        return (
            "Dạ mình chỉ hỗ trợ về dịch vụ sửa chữa nhà của Fixago thôi ạ 😊 "
            "Bạn có cần tư vấn sửa chữa điện, nước, máy lạnh hay xây dựng không?"
        )

    # Consultation-only: user explicitly says they just want advice, not booking
    if any(k in q for k in ["chỉ hỏi", "hỏi thôi", "tư vấn thôi", "chỉ muốn hỏi",
                              "không muốn đặt", "chưa muốn đặt"]):
        # Route to price/service info if service keyword present
        return ""  # let normal routing handle; negation guard prevents booking

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

    # Emoji / noisy urgent repair — only fire if no explicit booking intent
    _ELECTRIC_NOISE = ["chập điện", "cháy điện", "tóe lửa", "điện bị", "hở điện"]
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


def _detect_multi_service(query: str, first_tool: str, messages: list, used_tools: list):
    """
    If the query mentions two different service categories, call both APIs and
    return a combined answer string directly (not a CALL_TOOL token).
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
        return first_tool  # single or zero service → normal path

    # Avoid false multi-service on compound phrases like "máy giặt bị rò nước"
    # or contact-info messages like "Tôi tên An, sđt 0909111222, ở 45 Trần Phú. Máy giặt bị rò"
    # Require an explicit price/question connector between service mentions
    _MULTI_SEPARATORS = [" còn ", " và giá ", " với giá ", " or ", " and ",
                         "bao nhiêu,", "bao nhiêu còn", "giá còn"]
    if not any(sep in q for sep in _MULTI_SEPARATORS):
        return first_tool  # single compound phrase, not a real multi-service query

    # Fetch both services and stitch responses
    parts = []
    for svc in matched[:2]:
        result = handle_get_services(svc, messages, used_tools)
        # Extract just the price line(s) to keep it concise
        lines = [l for l in result.split("\n") if l.strip() and "muốn mình" not in l]
        parts.append(f"**{svc.title()}:** " + " ".join(lines[:3]))

    combined = "\n\n".join(parts) + "\n\nChi phí thực tế thợ sẽ báo rõ trước khi làm. Bạn muốn mình hỗ trợ đặt lịch không ạ?"
    return combined  # return final string, not CALL_TOOL token


def _run_legacy_tool_path(query: str, history: list, messages: list, used_tools: list) -> str:
    """Legacy text-based tool detection path (no --jinja needed)."""

    # Tool intent takes priority over booking when not negated
    forced_tool = _detect_tool_intent(query)

    # Multi-service query: user asks about two different services in one message
    # e.g. "giá máy lạnh bao nhiêu, còn giá sửa ống nước thì sao?"
    forced_tool = _detect_multi_service(query, forced_tool, messages, used_tools)

    # Static fallback short-circuits everything (policy/safety/identity/off-topic)
    static_early = _static_fallback(query)
    if static_early:
        return static_early

    # Booking path — skip if user negated intent or a tool will handle it
    # A price/service query takes precedence over booking flow inheritance
    _has_service_tool = forced_tool and "get_services" in str(forced_tool)
    if not detect_negation(query) and not _has_service_tool:
        booking_resp = build_booking_response(query, history)
    else:
        booking_resp = None

    # Decide priority: booking CALL_TOOL > promo/groups > booking text > price tool > LLM
    # Promotion/groups tool always wins over booking (user asking info, not booking)
    promo_or_groups = forced_tool and any(t in forced_tool for t in ["get_promotions", "get_groups"])

    # If _detect_multi_service already resolved to a final string, use it directly
    if forced_tool and not forced_tool.startswith("CALL_TOOL:"):
        return forced_tool

    if booking_resp and "CALL_TOOL: create_booking" in booking_resp:
        # Confirmed booking execution — highest priority
        answer = booking_resp
    elif promo_or_groups:
        # Promotion/groups query — always dispatch, even mid-booking
        answer = forced_tool
    elif booking_resp:
        # Booking flow in progress (asking for info or showing summary)
        answer = booking_resp
    elif forced_tool:
        answer = forced_tool
    else:
        grammar = load_grammar("fixago_tool_call.gbnf")
        answer  = llm_chat(messages, temperature=0.0, grammar=grammar)

    answer = repair_booking_tool_call(answer, query, history)

    if "CALL_TOOL: get_groups" in answer:
        messages.append({"role": "assistant", "content": answer})
        return handle_get_groups(messages, used_tools)

    if "CALL_TOOL: get_services" in answer:
        m      = re.search(r'search="([^"]*)"', answer)
        search = normalize_service_search(m.group(1) if m else "")
        messages.append({"role": "assistant", "content": answer})
        svc_result = handle_get_services(search, messages, used_tools)
        # Append warranty note if query also asked about it
        q_low = (query or "").lower()
        if any(k in q_low for k in ["bảo hành", "warranty", "guarantee"]):
            svc_result = svc_result.rstrip() + "\n\nVề bảo hành: thông tin cụ thể phụ thuộc từng hạng mục, thợ sẽ trao đổi rõ khi đến kiểm tra."
        # Append comparison note if query compares with competitors
        if any(k in q_low for k in ["rẻ hơn", "so với", "so sánh", "tốt hơn", "thợ tự do", "compare"]):
            svc_result = svc_result.rstrip() + "\nThợ Fixago đã được xác minh kỹ năng, báo giá minh bạch trước khi làm — không lo phát sinh."
        return svc_result

    if "CALL_TOOL: get_promotions" in answer:
        messages.append({"role": "assistant", "content": answer})
        promo_result = handle_get_promotions(messages, used_tools)
        # Append comparison note if query also asks about price vs competitors
        q_low = (query or "").lower()
        if any(k in q_low for k in ["rẻ hơn", "so với", "tốt hơn", "thợ tự do", "compare", "cheaper"]):
            promo_result = promo_result.rstrip() + "\n\nVề chi phí so với thợ tự do: Fixago báo giá minh bạch trước khi làm, thợ đã được xác minh — không lo phát sinh chi phí ngoài ý muốn."
        return promo_result

    if "create_booking" in answer.lower():
        return handle_create_booking(answer, used_tools)

    return answer


def _run_legacy_fast_path(query: str, history: list, messages: list, used_tools: list):
    """
    Handle deterministic static/booking/tool responses before RAG retrieval or
    LLM fallback. Returns None when the request needs the model.
    """
    forced_tool = _detect_tool_intent(query)
    forced_tool = _detect_multi_service(query, forced_tool, messages, used_tools)

    static_early = _static_fallback(query)
    if static_early:
        return static_early

    _has_service_tool = forced_tool and "get_services" in str(forced_tool)
    if not detect_negation(query) and not _has_service_tool:
        booking_resp = build_booking_response(query, history)
    else:
        booking_resp = None

    promo_or_groups = forced_tool and any(t in forced_tool for t in ["get_promotions", "get_groups"])

    if forced_tool and not forced_tool.startswith("CALL_TOOL:"):
        return forced_tool

    if booking_resp and "CALL_TOOL: create_booking" in booking_resp:
        answer = booking_resp
    elif promo_or_groups:
        answer = forced_tool
    elif booking_resp:
        answer = booking_resp
    elif forced_tool:
        answer = forced_tool
    else:
        return None

    answer = repair_booking_tool_call(answer, query, history)

    if "CALL_TOOL: get_groups" in answer:
        messages.append({"role": "assistant", "content": answer})
        return handle_get_groups(messages, used_tools)

    if "CALL_TOOL: get_services" in answer:
        m      = re.search(r'search="([^"]*)"', answer)
        search = normalize_service_search(m.group(1) if m else "")
        messages.append({"role": "assistant", "content": answer})
        svc_result = handle_get_services(search, messages, used_tools)
        q_low = (query or "").lower()
        if any(k in q_low for k in ["bảo hành", "warranty", "guarantee"]):
            svc_result = svc_result.rstrip() + "\n\nVề bảo hành: thông tin cụ thể phụ thuộc từng hạng mục, thợ sẽ trao đổi rõ khi đến kiểm tra."
        if any(k in q_low for k in ["rẻ hơn", "so với", "so sánh", "tốt hơn", "thợ tự do", "compare"]):
            svc_result = svc_result.rstrip() + "\nThợ Fixago đã được xác minh kỹ năng, báo giá minh bạch trước khi làm — không lo phát sinh."
        return svc_result

    if "CALL_TOOL: get_promotions" in answer:
        messages.append({"role": "assistant", "content": answer})
        promo_result = handle_get_promotions(messages, used_tools)
        q_low = (query or "").lower()
        if any(k in q_low for k in ["rẻ hơn", "so với", "tốt hơn", "thợ tự do", "compare", "cheaper"]):
            promo_result = promo_result.rstrip() + "\n\nVề chi phí so với thợ tự do: Fixago báo giá minh bạch trước khi làm, thợ đã được xác minh — không lo phát sinh chi phí ngoài ý muốn."
        return promo_result

    if "create_booking" in answer.lower():
        return handle_create_booking(answer, used_tools)

    return answer


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
