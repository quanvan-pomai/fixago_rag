"""
core/orchestrator.py
Orchestration paths: fast path, legacy tool path, native tool path, session persistence.
"""
import re

import rag_engine
from booking.extractor import detect_negation, merge_booking_info
from booking.handler import (
    build_booking_response, handle_create_booking,
    normalize_service_search, repair_booking_tool_call,
)
from core.guardrails import static_fallback
from core.intent_router import detect_tool_intent, is_hours_question
from core.output_validator import validate_llm_output
from core.prompt_builder import compact_history
from core.query_processor import (
    detect_multi_service, fetch_tool_data_block, split_questions,
)
from core.session import SessionManager
from llm_client.client import llm_chat, llm_chat_with_tools
from tools.handlers import (
    fetch_raw_groups, fetch_raw_services, fetch_raw_promotions,
    format_groups_for_llm, format_services_for_llm,
    handle_get_groups, handle_get_promotions, handle_get_services,
)
from booking.extractor import detect_confirmation

_HOURS_FACT = "Fixago hoạt động 24/7, kể cả cuối tuần và ngày lễ."


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


def llm_with_injected_data(query: str, data_block: str, messages: list) -> str:
    """Inject backend data as [DỮ LIỆU HỆ THỐNG] block, then call LLM."""
    instruction = (
        f"[DỮ LIỆU HỆ THỐNG — chỉ dùng thông tin này để trả lời, không bịa thêm]\n"
        f"{data_block}\n"
        f"[/DỮ LIỆU]\n\n"
        f"{query}"
    )
    llm_messages = messages[:-1] + [{"role": "user", "content": instruction}]
    raw = llm_chat(llm_messages, temperature=0.15)
    fix = validate_llm_output(raw, data_block, query)
    return fix if fix is not None else raw


def execute_tool(tool_str: str, messages: list, used_tools: list) -> str:
    """Execute a CALL_TOOL string and return a formatted response."""
    last_user = ""
    for msg in reversed(messages):
        if msg.get("role") == "user":
            last_user = msg.get("content", "")
            break
    query = _extract_clean_query(last_user)

    if "get_groups" in tool_str:
        used_tools.append("Tool [Backend API]: GET /services/groups")
        groups = fetch_raw_groups()
        if groups:
            data_block = format_groups_for_llm(groups)
            return llm_with_injected_data(query, data_block, messages)
        return handle_get_groups(messages, used_tools)

    if "get_promotions" in tool_str:
        return handle_get_promotions(messages, used_tools)

    if "get_services" in tool_str:
        m2 = re.search(r'search="([^"]*)"', tool_str)
        search = normalize_service_search(m2.group(1) if m2 else "")
        used_tools.append(f'Tool [Backend API]: GET /services?search="{search}"')
        services = fetch_raw_services(search)
        if services:
            data_block = format_services_for_llm(services, search)
            return llm_with_injected_data(query, data_block, messages)
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


def run_native_tool_path(query: str, history: list, messages: list, used_tools: list) -> str:
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

        info = merge_booking_info(query, history)
        info.update({k: v for k, v in tool_result.items() if v})
        return (
            f"Tên: {info.get('name') or tool_result.get('name', '?')}\n"
            f"SĐT: {info.get('phone') or tool_result.get('phone', '?')}\n"
            f"Địa chỉ: {info.get('address') or tool_result.get('address', '?')}\n"
            f"Vấn đề: {info.get('issue') or tool_result.get('description', '?')}\n"
            "Bạn xác nhận đặt lịch với thông tin này nhé?"
        )

    return tool_result


def persist_session(session_id: str, session: dict, query: str, answer: str):
    session["history"].append({"role": "user",      "content": query})
    session["history"].append({"role": "assistant", "content": answer})
    session["history"]       = compact_history(session["history"], max_items=8)
    session["booking_state"] = merge_booking_info(query, session["history"])
    SessionManager.save(session_id, session)
