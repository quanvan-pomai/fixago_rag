"""
core/orchestrator.py
Orchestration paths: fast path, legacy tool path, native tool path, session persistence.
"""
import re
import hashlib
import json

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


def run_native_tool_path(query: str, history: list, messages: list, used_tools: list) -> str:
    """Native function-calling path (cheese-server --jinja required)."""
    static_early = static_fallback(query)
    if static_early:
        return static_early

    # Deterministic business facts layer — answer stable questions without LLM
    from core.guardrails import deterministic_business_reply
    biz_reply = deterministic_business_reply(query)
    if biz_reply:
        return biz_reply

    # Off-topic detection — reject non-repair questions AFTER business facts but BEFORE booking
    from core.guardrails import is_offtopic, offtopic_response
    if is_offtopic(query):
        return offtopic_response(query)

    # Booking state machine: deterministic slot extraction before LLM routing
    booking_resp = build_booking_response(query, history)
    if booking_resp:
        booking_resp = repair_booking_tool_call(booking_resp, query, history)
        if "create_booking" in booking_resp.lower():
            return handle_create_booking(booking_resp, used_tools)
        return booking_resp

    # LET LLM HANDLE SEMANTIC ROUTING
    # Remove hardcoded pre-checks — Qwen2.5 3B is smart enough to understand intent
    # The system prompt has explicit routing rules that the LLM will follow
    # Trusting the model to call the right tools via native function calling

    try:
        tool_name, tool_result, raw_msg = llm_chat_with_tools(messages, temperature=0.0)
    except Exception:
        # Timeout or server error — return safe deterministic fallback
        return _NATIVE_TOOL_FALLBACK

    # If LLM didn't call a tool, return its plain text response
    # (The system prompt should guide it to call tools for price/repair questions)

    # Tool call: fetch data + inject [DỮ LIỆU HỆ THỐNG] + re-call LLM with price
    if tool_name in ("get_groups", "get_services", "get_promotions"):
        messages.append({"role": "assistant", "content": None, "tool_calls": raw_msg.get("tool_calls")})
        if tool_name == "get_services":
            raw_svc = tool_result.get("category") or tool_result.get("search", "")
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
    return fix if fix is not None else tool_result


def persist_session(session_id: str, session: dict, query: str, answer: str):
    session["history"].append({"role": "user",      "content": query})
    session["history"].append({"role": "assistant", "content": answer})
    session["history"]       = compact_history(session["history"], max_items=8)
    session["booking_state"] = merge_booking_info(query, session["history"])
    SessionManager.save(session_id, session)
