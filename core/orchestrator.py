"""
core/orchestrator.py
Orchestration paths: fast path, legacy tool path, native tool path, session persistence.
"""
import re
import hashlib
import json
import os
import requests

import rag_engine
from booking.extractor import detect_negation, merge_booking_info
from booking.handler import (
    build_booking_response, handle_create_booking,
    normalize_service_search, repair_booking_tool_call,
)
from core.guardrails import static_fallback
from core.intent_router import detect_tool_intent, is_hours_question, is_price_question
from core.output_validator import validate_llm_output
from core.prompt_builder import compact_history
from core.query_processor import (
    detect_multi_service, fetch_tool_data_block, split_questions,
)
from core.session import SessionManager
from llm_client.client import llm_chat, llm_chat_with_tools
from tools.handlers import (
    fetch_raw_groups, fetch_raw_services, fetch_raw_promotions,
    format_groups_for_llm, format_services_direct,
    handle_get_groups, handle_get_promotions, handle_get_services,
)
from booking.extractor import detect_confirmation
try:
    from fallback_config import (
        synthesis_with_fallback, is_unsupported_service,
        has_hallucination_markers, detect_fallback_reason
    )
except ImportError:
    # Fallback config not available yet - define minimal stubs
    def detect_fallback_reason(query, response, lang="vi"):
        return None
    def synthesis_with_fallback(query, response, lang="vi"):
        return response

_HOURS_FACT = "Fixago hoạt động 24/7, kể cả cuối tuần và ngày lễ."
_DATA_INJECTION_MAX_TOKENS = 120

# Focused system prompts for data-injection LLM calls. The full booking protocol
# causes the 3B model to skip price data and jump straight to collecting contacts,
# so we use a minimal, example-driven prompt for this specific call.
_DATA_INJECTION_SYSTEM = {
    "en": (
        "You are Fixie, Fixago assistant. 2 sentences max. "
        "Example: 'AC repair costs around 250,000 VNĐ. "
        "Could you share your name, phone, and address so I can book a technician?'"
    ),
    "vi": (
        "Bạn là Fixie của Fixago. Tối đa 2 câu, dùng 'Dạ/anh/chị/mình'. "
        "Ví dụ: 'Dạ sửa ổ cắm tham khảo khoảng 150.000đ ạ. "
        "Anh/chị cho mình xin tên, SĐT và địa chỉ để đặt lịch thợ nhé?'"
    ),
}

_SHORT_YES = {"có", "co", "yes", "ok", "ừ", "uh", "đúng", "dung", "muốn", "muon"}
_TOOL_ANSWER_TTL_MS = 30 * 60 * 1000


def _detect_service_overview_question(query: str) -> bool:
    """
    Pre-check for service overview questions.
    Returns True if query is clearly asking "what services do you offer".
    This is a safety net for small LLMs that may not reliably call get_groups().
    """
    from core.intent_router import normalize_noaccent
    q = normalize_noaccent((query or "").strip().lower())

    # Service overview signals
    service_signals = ["dịch vụ", "service", "làm", "do", "offer"]
    overview_signals = [
        "gì", "what", "nào", "which", "những", "có gì", "những gì",
        "offer", "provide", "cung cấp", "làm gì"
    ]

    # Must contain both a service word AND an overview word
    has_service = any(s in q for s in service_signals)
    has_overview = any(o in q for o in overview_signals)

    return has_service and has_overview


def _detect_promotion_question(query: str) -> bool:
    """
    Pre-check for promotion/discount questions.
    Returns True if query asks about discounts, vouchers, or promotions.
    This is a safety net for small LLMs that may confuse promotions with prices.
    """
    from core.intent_router import normalize_noaccent
    q = normalize_noaccent((query or "").strip().lower())

    # Promotion signals
    promo_signals = [
        "khuyến mãi", "khuyen mai", "giảm giá", "giam gia",
        "discount", "voucher", "coupon", "ưu đãi", "uu dai",
        "mã giảm", "ma giam", "code"
    ]

    question_signals = ["có", "co", "nào", "what", "gì", "gi", "code", "mã"]

    # Must have both promotion word and question signal
    has_promo = any(p in q for p in promo_signals)
    has_question = any(s in q for s in question_signals)

    return has_promo and has_question


def _detect_area_question(query: str) -> bool:
    """
    Semantic detection for area/location questions.
    Returns True if query is asking where Fixago is located or if it serves a location.
    Uses semantic understanding: looks for location question patterns.
    """
    from core.intent_router import normalize_noaccent
    q = normalize_noaccent((query or "").strip().lower())

    # Location signals: asking WHERE something is
    location_keywords = ["ở đâu", "o dau", "where", "location", "khu vực", "khu vuc"]

    # Company/service context: asking about Fixago, company, service
    company_keywords = [
        "fixago", "công ty", "cong ty", "company", "service", "dịch vụ", "dich vu",
        "em", "bạn", "ban", "you", "trụ sở", "tru so", "địa chỉ", "dia chi",
        "address", "phục vụ", "phuc vu", "serve", "support"
    ]

    # Must have both location question and company context
    has_location = any(k in q for k in location_keywords)
    has_company = any(k in q for k in company_keywords)

    return has_location and has_company


def _infer_service_category(query: str) -> str:
    """
    Infer service category from repair keywords in the query.
    Returns category name or "all" if unclear.
    """
    from core.intent_router import normalize_noaccent
    q = normalize_noaccent((query or "").strip().lower())

    # Category inference
    categories = {
        "điện": ["ổ cắm", "o cam", "chập", "chap", "điện", "dien", "cắt", "cat", "dây", "day", "công tắc", "cong tac", "bóng đèn", "bong den", "tủ điện", "tu dien", "aptomat", "mất điện", "mat dien"],
        "nước": ["nước", "nuoc", "ống", "ong", "rò rỉ", "ro ri", "rò", "ro", "cống", "cong", "thoát", "thoat", "vòi", "voi", "bồn cầu", "bon cau", "vệ sinh", "ve sinh"],
        "máy lạnh": ["máy lạnh", "may lanh", "ac", "điều hòa", "dieu hoa", "lạnh", "lanh", "lạnh không"],
        "xây dựng": ["xây", "xay", "trần", "tran", "vách", "vach", "chống thấm", "chong tham", "thấm", "tham", "sơn", "son"],
        "thạch cao": ["thạch cao", "thach cao", "vách ngăn", "vach ngan", "trần thạch", "tran thach"],
    }

    for category, keywords in categories.items():
        if any(k in q for k in keywords):
            return category

    return "all"


def _detect_price_or_repair_question(query: str) -> bool:
    """
    Pre-check for price/repair questions that small LLMs often skip.
    Returns True if query asks about price OR describes a repair issue with price intent.
    """
    from core.intent_router import is_price_question, normalize_noaccent

    # If it's a price question, return True
    if is_price_question(query):
        return True

    # Also check for repair descriptions that might need tool call
    # (even if not explicitly asking for price, repair issue + repair keywords warrants get_services)
    q = normalize_noaccent((query or "").strip().lower())

    repair_signals = [
        "chập", "chap", "hỏng", "hong", "không lạnh", "khong lanh",
        "rò rỉ", "ro ri", "tắc", "tac", "vỡ", "vo", "bị", "bi",
        "sửa", "sua", "fix", "repair"
    ]

    has_repair = any(r in q for r in repair_signals)
    has_service_mention = any(s in q for s in ["điện", "dien", "nước", "nuoc", "máy lạnh", "may lanh", "xây dựng", "xay dung"])

    return has_repair and has_service_mention


def _is_yes_to_service_list(query: str, history: list) -> bool:
    """Treat short yes/no-accent replies as consent to the previous service-list clarification."""
    q = (query or "").strip().lower().strip(" .,!?;:")
    if q not in _SHORT_YES:
        return False

    for msg in reversed(history or []):
        if msg.get("role") != "assistant":
            continue
        content = (msg.get("content") or "").lower()
        if any(k in content for k in [
            "fixago có dịch vụ gì",
            "fixago co dich vu gi",
            "bạn muốn biết fixago có dịch vụ",
            "ban muon biet fixago co dich vu",
            "dịch vụ gì không",
            "dich vu gi khong",
        ]):
            return True
        return False
    return False


def _extract_clean_query(last_user_content: str) -> str:
    """Strip RAG context prefix from the last user message to get the actual query."""
    text = last_user_content or ""
    if "Câu hỏi của khách:" in text:
        return text.split("Câu hỏi của khách:")[-1].strip()
    if "Ngữ cảnh tham khảo:" in text:
        parts = text.split("\n\n")
        return parts[-1].replace("Câu hỏi của khách:\n", "").strip()
    if "[DỮ LIỆU HỆ THỐNG" in text:
        if "Câu hỏi:" in text:
            return text.split("Câu hỏi:")[-1].split("\n")[0].strip()
        if "Khách hỏi:" in text:
            return text.split("Khách hỏi:")[-1].split("\n")[0].strip()
    return text.strip()


def _stable_data_hash(data) -> str:
    payload = json.dumps(data or [], ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _cache_get_text(key: str) -> str:
    try:
        raw = rag_engine.cache.get(key)
        return raw.decode("utf-8") if raw else ""
    except Exception:
        return ""


def _cache_set_text(key: str, value: str, ttl_ms: int = _TOOL_ANSWER_TTL_MS) -> None:
    try:
        rag_engine.cache.set(key, value.encode("utf-8"), ttl_ms=ttl_ms)
    except Exception:
        pass


def _tool_answer_cache_key(tool_name: str, query: str, data_hash: str, search: str = "") -> str:
    kind = "price" if is_price_question(query) else "info"
    clean_search = (search or "all").strip().lower()
    return f"tool_answer:{tool_name}:{clean_search}:{kind}:{data_hash}"


def llm_with_injected_data(query: str, data_block: str, messages: list, cache_key: str = "") -> str:
    """Inject backend data as [DỮ LIỆU HỆ THỐNG] block, then call LLM."""
    if cache_key:
        cached = _cache_get_text(cache_key)
        if cached:
            return cached

    from core.intent_router import detect_user_language
    lang = detect_user_language(query)

    instruction = (
        f"[DỮ LIỆU HỆ THỐNG — chỉ dùng thông tin này để trả lời, không bịa thêm]\n"
        f"{data_block}\n"
        f"[/DỮ LIỆU]\n\n"
        f"{query}"
    )
    focused_system = _DATA_INJECTION_SYSTEM.get(lang, _DATA_INJECTION_SYSTEM["vi"])
    llm_messages = [{"role": "system", "content": focused_system}, {"role": "user", "content": instruction}]
    raw = llm_chat(llm_messages, temperature=0.15, max_tokens=_DATA_INJECTION_MAX_TOKENS)
    fix = validate_llm_output(raw, data_block, query)
    answer = fix if fix is not None else raw
    if cache_key and answer:
        _cache_set_text(cache_key, answer)
    return answer


def execute_tool(tool_str: str, messages: list, used_tools: list) -> str:
    """Execute a CALL_TOOL string and return a formatted response."""
    last_user = ""
    for msg in reversed(messages):
        if msg.get("role") == "user":
            last_user = msg.get("content", "")
            break
    query = _extract_clean_query(last_user)

    _ERR = "Dạ hiện mình chưa lấy được thông tin từ hệ thống. Bạn thử lại sau ít phút nhé ạ."

    if "get_groups" in tool_str:
        used_tools.append("Tool [Backend API]: GET /services/groups")
        result = fetch_raw_groups()
        if not result.ok:
            return _ERR
        if result.data:
            cache_key = _tool_answer_cache_key("get_groups", query, _stable_data_hash(result.data))
            return llm_with_injected_data(query, format_groups_for_llm(result.data), messages, cache_key=cache_key)
        return handle_get_groups(messages, used_tools)

    if "get_promotions" in tool_str:
        return handle_get_promotions(messages, used_tools)

    if "get_services" in tool_str:
        m2 = re.search(r'search="([^"]*)"', tool_str)
        search = normalize_service_search(m2.group(1) if m2 else "")
        used_tools.append(f'Tool [Backend API]: GET /services?search="{search}"')
        result = fetch_raw_services(search)
        if not result.ok:
            return _ERR
        if result.data:
            from core.intent_router import detect_user_language
            return format_services_direct(result.data, search, lang=detect_user_language(query))
        return handle_get_services(search, messages, used_tools)

    return ""


def run_legacy_fast_path(query: str, history: list, messages: list, used_tools: list):
    """
    Pre-RAG fast path: handle static + booking + multi-service without calling LLM.
    Returns None to signal the main path should continue.
    """
    static_early = static_fallback(query)
    if static_early:
        return static_early

    if _is_yes_to_service_list(query, history):
        return execute_tool("CALL_TOOL: get_groups()", messages, used_tools)

    _hint_tool = detect_tool_intent(query)
    _has_service_hint = _hint_tool and "get_services" in str(_hint_tool)
    if not detect_negation(query) and not _has_service_hint:
        booking_resp = build_booking_response(query, history)
        if booking_resp:
            booking_resp = repair_booking_tool_call(booking_resp, query, history)
            if "create_booking" in booking_resp.lower():
                return handle_create_booking(booking_resp, used_tools)
            return booking_resp

    multi_result = detect_multi_service(query, _hint_tool, messages, used_tools)
    if multi_result and multi_result != _hint_tool:
        return llm_with_injected_data(query, multi_result, messages)

    return None


def run_legacy_tool_path(query: str, history: list, messages: list, used_tools: list) -> str:
    """
    Main orchestration path.
    Flow:
      1. Static guardrails
      2. Booking confirmation / mid-flow
      3. Multi-service
      4. Single tool + optional hours combo
      5. Multi-question split
      6. Pure LLM
    """
    # 1. Static guardrails
    static_early = static_fallback(query)
    if static_early:
        return static_early

    if _is_yes_to_service_list(query, history):
        return execute_tool("CALL_TOOL: get_groups()", messages, used_tools)

    # 2. Booking flow
    _hint_tool = detect_tool_intent(query)
    _has_service_hint = _hint_tool and "get_services" in str(_hint_tool)
    if not detect_negation(query) and not _has_service_hint:
        booking_resp = build_booking_response(query, history)
        if booking_resp:
            booking_resp = repair_booking_tool_call(booking_resp, query, history)
            if "create_booking" in booking_resp.lower():
                return handle_create_booking(booking_resp, used_tools)
            return booking_resp

    # 3. Multi-service shortcut
    multi_result = detect_multi_service(query, _hint_tool, messages, used_tools)
    if multi_result and multi_result != _hint_tool:
        return llm_with_injected_data(query, multi_result, messages)

    # 4. Single tool (with optional hours combo)
    if _hint_tool and _hint_tool.startswith("CALL_TOOL:"):
        if is_hours_question(query):
            tool_data = fetch_tool_data_block(_hint_tool, used_tools)
            combo_blocks = [b for b in [tool_data, _HOURS_FACT] if b]
            if combo_blocks:
                return llm_with_injected_data(query, "\n\n---\n".join(combo_blocks), messages)
        return execute_tool(_hint_tool, messages, used_tools)

    # 5. Multi-question split
    sub_questions = split_questions(query)
    if len(sub_questions) > 1:
        data_blocks: list[str] = []
        hours_fact = False

        for sub_q in sub_questions:
            if is_hours_question(sub_q):
                hours_fact = True
                continue
            tool = detect_tool_intent(sub_q)
            if not tool:
                continue
            block = fetch_tool_data_block(tool, used_tools)
            if block:
                data_blocks.append(block)

        if hours_fact:
            data_blocks.append(_HOURS_FACT)

        if data_blocks:
            combined = "\n\n---\n".join(data_blocks)
            enriched = (
                f"[DỮ LIỆU HỆ THỐNG — chỉ dùng thông tin này để trả lời, không bịa thêm]\n"
                f"{combined}\n"
                f"[/DỮ LIỆU]\n\n"
                f"{query}"
            )
            llm_messages = messages[:-1] + [{"role": "user", "content": enriched}]
            return llm_chat(llm_messages, temperature=0.1)

    # 6. Pure LLM
    raw = llm_chat(messages, temperature=0.2)
    fix = validate_llm_output(raw, None, query)
    return fix if fix is not None else raw


_NATIVE_TOOL_FALLBACK = (
    "Dạ mình có thể hỗ trợ hạng mục này. "
    "Anh/chị cho mình xin tên, SĐT và địa chỉ để đặt lịch thợ kiểm tra nhé?"
)


def _extract_category_from_groups(query: str) -> str:
    """
    Extract best matching service category from user query using backend group descriptions.
    Falls back to hardcoded keywords if backend unavailable.

    Scores keywords in query against each group's description.
    Prioritizes exact keyword matches (e.g., "đèn" > "trần").
    Returns category name (e.g., "điện", "nước") or "unknown" if no match.
    """
    import unicodedata
    backend_url = os.environ.get("BACKEND_API_URL", "http://127.0.0.1:3001/api/v1")
    query_lower = unicodedata.normalize("NFC", query.strip().lower())

    # High-priority keywords for each category (checked first)
    priority_keywords = {
        "Điện": ["điện", "ổ cắm", "công tắc", "đèn", "chiếu sáng", "aptomat"],
        "Nước": ["nước", "ống", "rò rỉ", "tắc", "cống", "bơm"],
        "Máy lạnh": ["máy lạnh", "điều hòa", "ac", "lạnh"],
        "Xây dựng": ["sơn", "xây dựng", "tường", "gạch"],
        "Thạch cao": ["thạch cao", "trần", "drywall"],
    }

    # First pass: check priority keywords (exact match, highest scoring)
    for category, keywords in priority_keywords.items():
        if any(k in query_lower for k in keywords):
            return category.lower()

    try:
        # Fallback to backend description matching if no priority keyword matched
        resp = requests.get(f"{backend_url}/services/groups", timeout=2)
        if resp.status_code != 200:
            return _extract_category_fallback(query_lower)

        groups = resp.json() or []
        if not groups:
            return _extract_category_fallback(query_lower)

        # Score each group based on description keyword matches
        best_score = 0
        best_category = "all"

        for group in groups:
            desc = (group.get("description", "") + " " + group.get("name", "")).lower()

            # Count how many words from query appear in description
            query_words = query_lower.split()
            score = sum(1 for word in query_words if len(word) > 2 and word in desc)

            if score > best_score:
                best_score = score
                best_category = group.get("name", "all").lower()

        if best_score > 0:
            return best_category
        else:
            return _extract_category_fallback(query_lower)

    except Exception:
        # Backend unavailable, use fallback
        return _extract_category_fallback(query_lower)


_NOT_SUPPORTED_VI = (
    "Dạ Fixago hiện chưa hỗ trợ dịch vụ đó. "
    "Các dịch vụ Fixago đang cung cấp gồm: "
    "Điện, Nước, Máy lạnh (điện lạnh), Xây dựng và Thạch cao. "
    "Anh/chị cần hỗ trợ hạng mục nào trong số trên không ạ?"
)
_NOT_SUPPORTED_EN = (
    "Fixago doesn't support that service yet. "
    "Available services: Electrical, Plumbing, Air Conditioning, "
    "Construction, and Drywall. "
    "Would you like help with any of these?"
)


def _extract_category_fallback(query_lower: str) -> str:
    """Hardcoded keyword fallback when backend unavailable.
    Returns 'unknown' if no category can be determined — caller must handle this.
    """
    if any(k in query_lower for k in ["điện", "ổ cắm", "công tắc", "aptomat", "chập", "mất", "dây điện", "bóng đèn", "đèn"]):
        return "điện"
    elif any(k in query_lower for k in ["nước", "ống", "rò", "tắc", "cống", "thoát", "bơm"]):
        return "nước"
    elif any(k in query_lower for k in ["máy lạnh", "điều hòa", "ac", "lạnh", "tủ lạnh"]):
        return "máy lạnh"
    elif any(k in query_lower for k in ["xây dựng", "sơn", "tôn", "làm nhà", "build", "chống thấm", "thấm"]):
        return "xây dựng"
    elif any(k in query_lower for k in ["thạch cao", "trần", "drywall", "trần nhà"]):
        return "thạch cao"
    # No keyword matched — cannot determine category
    return "unknown"


def run_native_tool_path(query: str, history: list, messages: list, used_tools: list) -> str:
    """Native function-calling path (cheese-server --jinja required)."""
    static_early = static_fallback(query)
    if static_early:
        return static_early

    # ─────────────────────────────────────────────────────────────────────────────
    # LAYER 0: FAQ PRIORITY PATH (Bypass semantic router confusion)
    # FAQ questions (operational/business) are handled FIRST to avoid router mixing
    # them with pricing/service questions
    # ─────────────────────────────────────────────────────────────────────────────
    from core.intent_router import is_faq_query
    from tools.handlers import handle_get_faq

    is_faq = is_faq_query(query)

    if is_faq:
        faq_answer = handle_get_faq(query)
        if faq_answer:
            return faq_answer
        # If FAQ handler didn't find answer, continue to normal flow (skip hard-gate)
    else:
        # ── QUERY COMPLEXITY CHECK (HARD-GATE for non-FAQ only) ──────────────────────────────
        # Layer 1: Punctuation-based multi-question detection
        # Layer 2: Lexicon-based Service/Info counting (for queries without punctuation)
        from core.intent_router import split_multi_questions, detect_user_language
        from core.lexicon import is_multi_question_by_lexicon

        sub_questions = split_multi_questions(query)
        question_count = len(sub_questions)

        # Layer 2: Check service/info groups (catches no-punctuation multi-questions)
        is_multi_by_lexicon = is_multi_question_by_lexicon(query)

        # HARD-GATE: BLOCK multi-questions BEFORE they reach LLM
        # This is a CRIT GATE - cannot pass unless single question detected
        # Catches both:
        # - "Services and prices?" (Layer 1: 2 sub-questions) -> handled implicitly if lexicon spots multiple infos/services
        # - "sửa ống nước với thay bóng đèn" (Layer 2: 2 services, no punctuation)

        # MUST BE: NOT is_multi_by_lexicon
        # We removed (question_count > 1) because "Do you repair fridges? How much?" has 2 questions but is 1 service intent.
        is_definitely_multi = is_multi_by_lexicon

        if is_definitely_multi:
            lang = detect_user_language(query)

            if lang == "vi":
                return ("Dạ Fixago đây ạ! Do tin nhắn của mình hơi dài nên hệ thống bên em đọc chưa hiểu hết ý. "
                       "Anh/chị có thể chia nhỏ từng câu hỏi giúp em được không ạ? Em cảm ơn nhiều!")
            else:
                return ("Hi there! Your message is quite long, so I might miss something. "
                       "Could you please break it down into separate questions? Thanks!")

    # Deterministic business facts layer — answer stable questions without LLM
    from core.guardrails import deterministic_business_reply
    biz_reply = deterministic_business_reply(query)
    if biz_reply:
        return biz_reply

    # Off-topic detection — reject non-repair questions AFTER business facts but BEFORE booking
    from core.guardrails import is_offtopic, offtopic_response
    if is_offtopic(query):
        return offtopic_response(query)

    # Skip booking handler for INFO questions (price, promotions, warranty, etc.)
    # These should go to LLM with tool calling, not to booking flow
    info_keywords = [
        # ── Vietnamese / no-accent: price / cost ─────────────────────────────
        "bao nhiêu", "bao nhieu",
        "giá", "gia",
        "báo giá", "bao gia",
        "chi phí", "chi phi",
        "phí", "phi",
        "tiền", "tien",
        "tốn bao nhiêu", "ton bao nhieu",
        "hết bao nhiêu", "het bao nhieu",
        "hết mấy", "het may",
        "bảng giá", "bang gia",
        "giá tham khảo", "gia tham khao",
        "giá dịch vụ", "gia dich vu",
        "tổng bill", "tong bill",
        "ước tính", "uoc tinh",

        # ── English: price / cost ───────────────────────────────────────────
        "how much",
        "price",
        "pricing",
        "cost",
        "fee",
        "fees",
        "charge",
        "charges",
        "quote",
        "quotation",
        "estimate",
        "estimated cost",
        "service fee",
        "repair cost",
        "price list",
        "rate",
        "budget",
        "bill",

        # ── Russian: price / cost ───────────────────────────────────────────
        "цена",
        "стоимость",
        "сколько стоит",
        "сколько будет стоить",
        "прайс",
        "смета",
        "оценка стоимости",
        "стоимость ремонта",
        "цена ремонта",
        "тариф",
        "оплата",
        "счет",

        # ── Hindi / Hinglish: price / cost ──────────────────────────────────
        "kitna",
        "kitna lagega",
        "kitne paise",
        "rate",
        "repair cost",
        "service charge",
        "bill kitna",
        "कीमत",
        "कितना",
        "खर्च",
        "चार्ज",
        "रेट",

        # ── French: price / cost ────────────────────────────────────────────
        "prix",
        "tarif",
        "coût",
        "cout",
        "combien",
        "combien ça coûte",
        "combien ca coute",
        "devis",
        "estimation",
        "frais",
        "frais de service",
        "tarification",
        "facture",

        # ── Promotion / discount ────────────────────────────────────────────
        "khuyến mãi", "khuyen mai",
        "ưu đãi", "uu dai",
        "giảm giá", "giam gia",
        "mã giảm", "ma giam",
        "mã code", "ma code",
        "voucher",
        "coupon",
        "code giảm", "code giam",
        "chiết khấu", "chiet khau",
        "discount",
        "promotion",
        "promo",
        "discount code",
        "promo code",
        "offer",
        "deal",
        "special offer",
        "скидка",
        "акция",
        "промокод",
        "купон",
        "छूट",
        "ऑफर",
        "कूपन",
        "promo",
        "réduction",
        "reduction",
        "code promo",
        "remise",
        "rabais",

        # ── Warranty / guarantee / overcommitment ───────────────────────────
        "bảo hành", "bao hanh",
        "cam kết", "cam ket",
        "đảm bảo", "dam bao",
        "đền bù", "den bu",
        "trách nhiệm", "trach nhiem",
        "hư lại", "hu lai",
        "sửa lại", "sua lai",
        "warranty",
        "guarantee",
        "guaranteed",
        "commitment",
        "compensation",
        "refund",
        "money back",
        "гарантия",
        "компенсация",
        "возврат денег",
        "guarantee",
        "warranty",
        "गारंटी",
        "वारंटी",
        "garantie",
        "remboursement",

        # ── Working hours / timing / technician arrival ─────────────────────
        "mấy giờ", "may gio",
        "giờ làm", "gio lam",
        "làm việc", "lam viec",
        "ban đêm", "ban dem",
        "cuối tuần", "cuoi tuan",
        "ngày lễ", "ngay le",
        "24/7",
        "bao lâu", "bao lau",
        "mất bao lâu", "mat bao lau",
        "khi nào", "khi nao",
        "thời gian", "thoi gian",
        "mấy phút", "may phut",
        "how long",
        "working hours",
        "business hours",
        "open time",
        "opening hours",
        "available at night",
        "weekend",
        "holiday",
        "confirm time",
        "arrival time",
        "when can technician come",
        "сколько времени",
        "часы работы",
        "работаете ночью",
        "когда приедет",
        "подтверждение",
        "kitni der",
        "kab aayega",
        "working time",
        "combien de temps",
        "horaires",
        "heure d'ouverture",
        "confirmation",
        "technicien arrive",

        # ── Payment / invoice ───────────────────────────────────────────────
        "thanh toán", "thanh toan",
        "tiền mặt", "tien mat",
        "chuyển khoản", "chuyen khoan",
        "ngân hàng", "ngan hang",
        "xuất hóa đơn", "xuat hoa don",
        "hóa đơn", "hoa don",
        "vat",
        "payment",
        "pay",
        "cash",
        "bank transfer",
        "invoice",
        "vat invoice",
        "оплата",
        "наличные",
        "перевод",
        "счет",
        "pay karna",
        "cash",
        "bank transfer",
        "भुगतान",
        "paiement",
        "espèces",
        "especes",
        "virement",
        "facture",

        # ── Service area / location / coverage ──────────────────────────────
        "ở đâu", "o dau",
        "địa chỉ công ty", "dia chi cong ty",
        "khu vực", "khu vuc",
        "phục vụ ở đâu", "phuc vu o dau",
        "có tới", "co toi",
        "có hỗ trợ", "co ho tro",
        "ngoài khu vực", "ngoai khu vuc",
        "quận nào", "quan nao",
        "tỉnh nào", "tinh nao",
        "where are you",
        "where is fixago",
        "service area",
        "coverage",
        "do you support",
        "do you serve",
        "available in",
        "location",
        "address",
        "area",
        "где вы",
        "район обслуживания",
        "вы работаете в",
        "поддерживаете",
        "kaha service",
        "area support",
        "service area",
        "où êtes-vous",
        "ou etes-vous",
        "zone de service",
        "vous intervenez",
        "disponible à",
        "disponible a",

        # ── Company / service overview / identity ───────────────────────────
        "dịch vụ gì", "dich vu gi",
        "dịch vụ nào", "dich vu nao",
        "có những dịch vụ", "co nhung dich vu",
        "cung cấp gì", "cung cap gi",
        "công ty làm gì", "cong ty lam gi",
        "công ty tên gì", "cong ty ten gi",
        "bạn là ai", "ban la ai",
        "what services",
        "which services",
        "what do you provide",
        "what does fixago do",
        "who are you",
        "introduce your company",
        "company services",
        "какие услуги",
        "что делает fixago",
        "кто вы",
        "services kya hai",
        "company kya karti hai",
        "कौन सी services",
        "quels services",
        "que propose fixago",
        "qui êtes-vous",
        "qui etes-vous",
        "présentez votre entreprise",
        "presentez votre entreprise",

        # ── Policy / trust / comparison / technician ────────────────────────
        "uy tín", "uy tin",
        "tin được không", "tin duoc khong",
        "thợ có đúng", "tho co dung",
        "chọn thợ", "chon tho",
        "thợ riêng", "tho rieng",
        "thợ ngoài", "tho ngoai",
        "hơn gì", "hon gi",
        "khác gì", "khac gi",
        "vì sao chọn", "vi sao chon",
        "why choose",
        "trusted",
        "reliable",
        "specific technician",
        "choose technician",
        "why fixago",
        "better than",
        "сравнить",
        "надежно",
        "можно доверять",
        "выбрать мастера",
        "trust hai kya",
        "reliable hai",
        "technician choose",
        "pourquoi choisir",
        "fiable",
        "technicien précis",
        "choisir technicien",
    ]
    query_lower = query.lower()
    is_info_question = any(kw in query_lower for kw in info_keywords)
    # Booking state machine: deterministic slot extraction before LLM routing
    # BUT: Skip booking handler if this is an INFO question (ask for price/warranty/promotion info)
    if not is_info_question:
        booking_resp = build_booking_response(query, history)
        if booking_resp:
            booking_resp = repair_booking_tool_call(booking_resp, query, history)
            if "create_booking" in booking_resp.lower():
                return handle_create_booking(booking_resp, used_tools)
            return booking_resp

    # ── FAST PATH FOR PROMOTIONS ────────────────────────────────────────────────
    promo_kws = ["khuyến mãi", "khuyen mai", "ưu đãi", "uu dai", "giảm giá", "giam gia", "voucher", "mã code", "discount", "promo", "mã giảm"]
    if any(kw in query_lower for kw in promo_kws):
        from tools.handlers import handle_get_promotions
        return handle_get_promotions(messages, used_tools)

    # ── SEMANTIC ROUTING: ONLY for deterministic facts, not for information queries ─
    # IMPORTANT: Only use semantic router for DETERMINISTIC responses (hours, payment, area, unsupported)
    # Let LLM handle information queries (services, pricing, promotions) with proper tool calling
    from core.semantic_router import route as semantic_route, handle_intent

    intent, confidence = semantic_route(query)

    # Only return deterministic response if it's a DETERMINISTIC intent
    deterministic_intents = ["payment_question", "unsupported_service"]

    if intent != "unclear" and intent in deterministic_intents and confidence >= 0.75:
        # Semantic router matched a DETERMINISTIC intent with high confidence
        response = handle_intent(intent, query, confidence)
        if response is not None:
            # Deterministic response (location, hours, payment, unsupported service)
            used_tools.append(f"[SemanticRoute] {intent} (confidence: {confidence:.2f})")
            return response

    # For information queries (services, pricing, promotions), let LLM handle with tools
    # Don't return early - fall through to llm_chat_with_tools

    # LET LLM HANDLE REMAINING ROUTING
    # The system prompt guides tool calling for service queries
    # Semantic router handles deterministic business facts and high-confidence intents

    try:
        tool_name, tool_result, raw_msg = llm_chat_with_tools(messages, temperature=0.0)
    except Exception:
        # Timeout or server error — return safe deterministic fallback
        return _NATIVE_TOOL_FALLBACK

    # If LLM didn't call a tool, return its plain text response
    # (The system prompt should guide it to call tools for price/repair questions)

    # Tool call: fetch data + inject [DỮ LIỆU HỆ THỐNG] + re-call LLM with price
    if tool_name in ("get_groups", "get_services", "get_promotions"):
        print(f"[DEBUG] Native tool call: tool_name={tool_name}, tool_result={tool_result}", flush=True)
        messages.append({"role": "assistant", "content": None, "tool_calls": raw_msg.get("tool_calls")})
        if tool_name == "get_services":
            raw_svc = tool_result.get("category") or tool_result.get("search", "")
            print(f"[DEBUG] get_services: raw_svc={raw_svc}", flush=True)

            # ALWAYS re-extract category from the CURRENT query.
            # Do NOT trust LLM-provided category — it can be contaminated by
            # session history (e.g. user asked about "điện" before, now asks "ống nước").
            extracted = _extract_category_from_groups(query)

            # Use extracted category; only fall back to LLM's value if extraction
            # returns "unknown" AND LLM provided something specific (not "all"/empty).
            if extracted != "unknown":
                raw_svc = extracted
            elif raw_svc in ("all", "", None):
                raw_svc = "unknown"
            # else: extracted=="unknown" but LLM gave a specific non-"all" value
            # → trust the LLM this one time (edge case: very short/ambiguous query)

            # If unknown — service not in our catalog
            if raw_svc == "unknown":
                from core.intent_router import detect_user_language
                lang = detect_user_language(query)
                return _NOT_SUPPORTED_EN if lang == "en" else _NOT_SUPPORTED_VI

            search = normalize_service_search(raw_svc)
            tool_str = f'CALL_TOOL: get_services(search="{search}")'
        else:
            tool_str = f"CALL_TOOL: {tool_name}()"
        return execute_tool(tool_str, messages, used_tools)

    # Booking: LLM extracted contact info or user confirmed
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

        info = merge_booking_info(query, history)
        info.update({k: v for k, v in tool_result.items() if v})
        return (
            f"Tên: {info.get('name') or tool_result.get('name', '?')}\n"
            f"SĐT: {info.get('phone') or tool_result.get('phone', '?')}\n"
            f"Địa chỉ: {info.get('address') or tool_result.get('address', '?')}\n"
            f"Vấn đề: {info.get('issue') or tool_result.get('description', '?')}\n"
            "Bạn xác nhận đặt lịch với thông tin này nhé?"
        )

    # No tool called: LLM returned plain text (booking collection, clarification, etc.)
    fix = validate_llm_output(tool_result, None, query)
    llm_response = fix if fix is not None else tool_result

    # ── FALLBACK PROTECTION: Check for hallucination ──────────────────────
    # Apply strict data synthesis validation for info questions
    from core.intent_router import detect_user_language
    lang = detect_user_language(query)

    # Check if this is an info question (price, policy, capability)
    is_info_question = any(kw in query.lower() for kw in [
        "bao nhiêu", "giá", "chi phí", "phí", "tiền",
        "how much", "price", "cost", "fee",
        "khuyến mãi", "giảm giá", "voucher", "discount",
        "bảo hành", "warranty", "có được không", "được không",
        "hỗ trợ", "support", "làm được", "can you"
    ])

    if is_info_question:
        # For info questions: validate against hallucination
        hallucination_reason = detect_fallback_reason(query, llm_response, lang)
        if hallucination_reason:
            # Hallucination detected → trigger fallback
            try:
                from fallback_config import get_fallback_response
                fallback = get_fallback_response(hallucination_reason, lang)
            except ImportError:
                fallback = llm_response
            print(f"[FALLBACK] Detected: {hallucination_reason} | Original: {llm_response[:50]}...", flush=True)
            return fallback

    return llm_response


def persist_session(session_id: str, session: dict, query: str, answer: str):
    session["history"].append({"role": "user",      "content": query})
    session["history"].append({"role": "assistant", "content": answer})
    session["history"]       = compact_history(session["history"], max_items=8)
    session["booking_state"] = merge_booking_info(query, session["history"])
    SessionManager.save(session_id, session)
