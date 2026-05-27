#!/usr/bin/env python3
import os
from dotenv import load_dotenv
load_dotenv()

import re
import hashlib
import requests
import json
import uuid
from flask import Flask, request, jsonify, send_file

import rag_engine
from tools_schema import FIXAGO_TOOLS

# Feature flag: set ENABLE_NATIVE_TOOL_CALL=1 to use OpenAI-style function calling
# Requires cheese-server started with --jinja flag
ENABLE_NATIVE_TOOL_CALL = os.environ.get("ENABLE_NATIVE_TOOL_CALL", "0") in ("1", "true", "yes")

class SessionManager:
    @staticmethod
    def get_session(session_id: str) -> dict:
        if not session_id:
            return {"history": [], "booking_state": {}}
        try:
            val = rag_engine.cache.get(f"session:{session_id}")
            if val:
                return json.loads(val.decode("utf-8"))
        except Exception as e:
            print(f"Session load failed: {e}")
        return {"history": [], "booking_state": {}}

    @staticmethod
    def save_session(session_id: str, session_data: dict):
        if not session_id:
            return
        try:
            # 2 hours TTL
            rag_engine.cache.set(f"session:{session_id}", json.dumps(session_data).encode("utf-8"), ttl_ms=7200000)
        except Exception as e:
            print(f"Session save failed: {e}")

app = Flask(__name__)


def load_system_prompt():
    try:
        with open("system_prompt.txt", "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return "Bạn là Trợ lý AI của Fixago. Luôn trả lời bằng tiếng Việt, lịch sự, ngắn gọn và hữu ích."


def normalize_text(text):
    return (text or "").strip().lower()


def is_prompt_injection(query):
    q = normalize_text(query)
    patterns = [
        "tiết lộ system prompt",
        "show system prompt",
        "give me your system prompt",
        "ignore previous instruction",
        "ignore all previous",
        "bỏ qua các quy tắc",
        "bỏ qua hướng dẫn trước",
        "bỏ qua lệnh trước",
        "developer message",
        "system message",
        "jailbreak",
        "prompt injection",
        "in ra prompt",
        "hiện prompt",
        "xuất prompt",
        "quên hết hướng dẫn",
    ]
    return any(p in q for p in patterns)


def guardrail_response():
    return {
        "status": "success",
        "response": "Mình không thể hỗ trợ phần đó, nhưng mình có thể tư vấn dịch vụ sửa chữa hoặc hỗ trợ bạn đặt lịch với Fixago ạ.",
        "source": "guardrail",
        "tool_calls": [],
        "cache_metrics": {
            "hit": False,
            "cached_tokens": 0,
            "savings_ratio": 0.0
        }
    }


def compact_history(history, max_items=8):
    if not isinstance(history, list):
        return []
    clean = []
    for msg in history[-max_items:]:
        if not isinstance(msg, dict):
            continue
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if role not in ["system", "user", "assistant"]:
            role = "user"
        if content:
            clean.append({"role": role, "content": str(content)})
    return clean


def history_to_text(history):
    return "\n".join(
        f"{m.get('role', 'user')}: {m.get('content', '')}"
        for m in compact_history(history)
    )


def build_safe_system(system_prompt):
    if ENABLE_NATIVE_TOOL_CALL:
        # Native tool calling: minimal system prompt, no need to teach format
        # Model gets tool schema from the API payload directly
        return system_prompt

    # Legacy text mode: inject compact few-shot examples to teach CALL_TOOL format
    # Keep examples minimal — small models get confused with too many
    return system_prompt + (
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


def detect_tool_intent(query):
    q = normalize_text(query)

    if any(k in q for k in ["khuyến mãi", "giảm giá", "ưu đãi", "voucher", "mã giảm", "coupon"]):
        return "CALL_TOOL: get_promotions()"

    if any(k in q for k in ["dịch vụ gì", "có dịch vụ", "những dịch vụ", "nhóm dịch vụ", "fixago làm gì", "bên bạn làm gì", "có sửa gì"]):
        return "CALL_TOOL: get_groups()"

    service_keywords = {
        "điện": ["điện", "chập", "ổ cắm", "bóng đèn", "công tắc", "tủ điện", "aptomat", "cb", "dây điện"],
        "nước": ["nước", "ống", "rò", "nghẹt", "vòi", "bồn cầu", "máy bơm", "van", "lavabo", "thoát nước"],
        "điện lạnh": ["máy lạnh", "điều hòa", "tủ lạnh", "nạp gas", "gas lạnh", "không lạnh", "điện lạnh"],
        "xây dựng": ["sơn", "chống thấm", "ốp lát", "gạch", "tường", "ban công", "xây dựng", "cải tạo"],
        "thạch cao": ["thạch cao", "trần", "vách ngăn", "vách thạch cao"],
    }

    intent_words = ["giá", "bao nhiêu", "sửa", "lắp", "thay", "bảo dưỡng", "kiểm tra", "báo giá", "hỏng", "lỗi", "dịch vụ"]
    if any(w in q for w in intent_words):
        for key, kws in service_keywords.items():
            if any(kw in q for kw in kws):
                return f'CALL_TOOL: get_services(search="{key}")'

    return None


def detect_booking_intent(query):
    q = normalize_text(query)
    return any(k in q for k in [
        "đặt lịch",
        "book",
        "gọi thợ",
        "đặt thợ",
        "cho thợ",
        "cử thợ",
        "hẹn thợ",
        "qua sửa",
        "đến sửa",
        "đến kiểm tra",
        "hỗ trợ đặt",
    ])


def detect_confirmation(query):
    q = normalize_text(query)
    confirm_words = [
        "xác nhận",
        "đồng ý",
        "ok",
        "oke",
        "okay",
        "được",
        "đặt đi",
        "book đi",
        "làm đi",
        "chốt",
        "yes",
        "có",
        "ừ",
        "uh",
    ]
    return any(w in q for w in confirm_words)


def extract_phone(text):
    if not text:
        return None
    match = re.search(r'(\+?84|0)(?:[\s\.-]?\d){8,10}', text)
    if not match:
        return None
    phone = re.sub(r'[\s\.-]', '', match.group(0))
    return phone


def extract_labeled_value(text, labels):
    if not text:
        return None
    label_pattern = "|".join(re.escape(x) for x in labels)
    match = re.search(rf'(?:{label_pattern})\s*[:\-]\s*(.+)', text, flags=re.IGNORECASE)
    if match:
        value = match.group(1).strip()
        value = re.split(r'\n|,?\s*(?:SĐT|Sđt|Phone|Điện thoại|Địa chỉ|Address|Vấn đề|Issue|Tên|Name)\s*[:\-]', value)[0].strip()
        return value.rstrip('.,; ') if value else None
    return None


def extract_booking_from_text(text):
    if not text:
        return {}

    name = extract_labeled_value(text, ["Tên", "Name", "Họ tên", "Khách hàng"])
    phone = extract_labeled_value(text, ["SĐT", "Sđt", "Phone", "Điện thoại", "Số điện thoại"])
    address = extract_labeled_value(text, ["Địa chỉ", "Address"])
    issue = extract_labeled_value(text, ["Vấn đề", "Issue", "Lỗi", "Nội dung", "Mô tả"])

    found_phone = extract_phone(text)
    if not phone and found_phone:
        phone = found_phone

    return {
        "name": name,
        "phone": phone,
        "address": address,
        "issue": issue,
    }


def merge_booking_info(query, history):
    info = {
        "name": None,
        "phone": None,
        "address": None,
        "issue": None,
    }

    for msg in compact_history(history, max_items=12):
        content = msg.get("content", "")
        extracted = extract_booking_from_text(content)
        for k, v in extracted.items():
            if v and not info.get(k):
                info[k] = v

    current = extract_booking_from_text(query)
    for k, v in current.items():
        if v:
            info[k] = v

    if not info.get("issue"):
        for msg in reversed(compact_history(history, max_items=12)):
            if msg.get("role") == "user":
                c = msg.get("content", "")
                if detect_booking_intent(c) or any(k in normalize_text(c) for k in ["sửa", "hỏng", "lỗi", "chập", "rò", "nghẹt", "không lạnh"]):
                    info["issue"] = c
                    break

    if not info.get("issue"):
        info["issue"] = query

    return info


def maybe_build_booking_response(query, history):
    has_intent = detect_booking_intent(query) or detect_confirmation(query)
    if not has_intent:
        for turn in reversed(history[-4:]): # check recent history
            if turn.get("role") == "user" and detect_booking_intent(turn.get("content", "")):
                has_intent = True
                break
    
    if not has_intent:
        return None

    info = merge_booking_info(query, history)
    missing = []

    if not info.get("name"):
        missing.append("họ tên")
    if not info.get("phone"):
        missing.append("số điện thoại")
    if not info.get("address"):
        missing.append("địa chỉ cần sửa")

    if missing:
        if len(missing) == 3:
            return "Dạ mình hỗ trợ bạn đặt lịch được ạ. Bạn cho Fixago xin họ tên, số điện thoại và địa chỉ cần sửa nhé."
        return "Dạ mình hỗ trợ bạn đặt lịch được ạ. Bạn cho mình xin thêm " + ", ".join(missing) + " nhé."

    if detect_confirmation(query):
        name = info.get("name")
        phone = info.get("phone")
        address = info.get("address")
        issue = info.get("issue") or "Khách hàng yêu cầu thợ đến kiểm tra"
        return f'CALL_TOOL: create_booking(name="{name}", phone="{phone}", address="{address}", description="{issue}")'

    return (
        f"Tên: {info.get('name')}\n"
        f"SĐT: {info.get('phone')}\n"
        f"Địa chỉ: {info.get('address')}\n"
        f"Vấn đề: {info.get('issue')}\n"
        "Bạn xác nhận đặt lịch với thông tin này nhé?"
    )

def format_vnd(value):
    try:
        n = int(float(value))
    except Exception:
        n = 0
    return f"{n:,}".replace(",", ".") + " VNĐ"


def build_price_summary(services):
    priced = []
    quote_required = []

    for s in services:
        name = s.get("name", "Dịch vụ")
        price = s.get("unitPrice", 0) or 0
        estimated_time = s.get("estimatedTime", 0) or 0

        try:
            price_num = int(float(price))
        except Exception:
            price_num = 0

        item = {
            "name": name,
            "price": price_num,
            "estimated_time": estimated_time,
        }

        if price_num > 0:
            priced.append(item)
        else:
            quote_required.append(item)

    if not priced and not quote_required:
        return None

    lines = []

    if priced:
        prices = [x["price"] for x in priced]
        min_price = min(prices)
        max_price = max(prices)

        if min_price == max_price:
            lines.append(f"Giá tham khảo: {format_vnd(min_price)}.")
        else:
            lines.append(f"Khoảng giá tham khảo: {format_vnd(min_price)} - {format_vnd(max_price)}.")

        lines.append("Một số dịch vụ phù hợp:")
        for item in priced[:5]:
            time_text = f", thời gian khoảng {item['estimated_time']} phút" if item["estimated_time"] else ""
            lines.append(f"- {item['name']}: {format_vnd(item['price'])}{time_text}.")

    if quote_required:
        names = ", ".join(x["name"] for x in quote_required[:3])
        lines.append(f"Một số hạng mục như {names} cần khảo sát để báo giá chính xác.")

    return "\n".join(lines)


def normalize_service_search(raw_search):
    search_lower = normalize_text(raw_search)

    if any(k in search_lower for k in ["máy lạnh", "điều hòa", "tủ lạnh", "gas", "không lạnh", "lạnh", "điện lạnh"]):
        return "máy lạnh"
    if any(k in search_lower for k in ["điện", "chập", "ổ cắm", "bóng đèn", "công tắc", "tủ điện", "aptomat", "cb", "dây điện"]):
        return "điện"
    if any(k in search_lower for k in ["nước", "ống", "bơm", "van", "bồn", "vòi", "nghẹt", "rò", "lavabo", "thoát nước"]):
        return "nước"
    if any(k in search_lower for k in ["giặt", "máy giặt"]):
        return "máy giặt"
    if any(k in search_lower for k in ["sơn", "chống thấm", "ốp lát", "tường", "ban công", "xây", "trát", "dột", "bê tông"]):
        return "xây dựng"
    if any(k in search_lower for k in ["thạch cao", "trần", "vách ngăn"]):
        return "thạch cao"

    return raw_search.strip()


def llm_chat(messages, temperature=0.0, timeout=300, grammar=None):
    payload = {
        "messages": messages,
        "temperature": temperature,
    }
    if grammar:
        payload["grammar"] = grammar

    response = requests.post(
        "http://127.0.0.1:8080/v1/chat/completions",
        json=payload,
        timeout=timeout
    )

    if response.status_code != 200:
        raise RuntimeError(f"LLM server returned status {response.status_code}: {response.text[:200]}")

    result_json = response.json()
    return result_json["choices"][0]["message"]["content"]


def load_grammar(grammar_file: str) -> str:
    """Load a GBNF grammar file, return empty string on failure."""
    try:
        grammar_path = os.path.join(os.path.dirname(__file__), "grammars", grammar_file)
        with open(grammar_path, "r", encoding="utf-8") as f:
            # Strip comment lines for cleaner payload
            lines = [l for l in f.readlines() if not l.strip().startswith("#")]
            return "".join(lines).strip()
    except Exception:
        return ""


def llm_chat_with_tools(messages, temperature=0.0, timeout=300):
    """
    Native OpenAI-style function calling — requires cheese-server --jinja.
    Returns (tool_name, tool_args_dict) if model called a tool,
    or (None, text_response) if model replied normally.
    """
    payload = {
        "messages": messages,
        "temperature": temperature,
        "tools": FIXAGO_TOOLS,
        "tool_choice": "auto",
    }

    response = requests.post(
        "http://127.0.0.1:8080/v1/chat/completions",
        json=payload,
        timeout=timeout
    )

    if response.status_code != 200:
        raise RuntimeError(f"LLM server returned status {response.status_code}: {response.text[:200]}")

    result_json = response.json()
    choice = result_json["choices"][0]
    message = choice["message"]

    # Model decided to call a tool
    tool_calls = message.get("tool_calls")
    if tool_calls:
        tc = tool_calls[0]  # take first tool call
        func_name = tc["function"]["name"]
        try:
            func_args = json.loads(tc["function"]["arguments"])
        except Exception:
            func_args = {}
        return func_name, func_args, message

    # Model replied with text
    return None, message.get("content", ""), message


def run_second_llm(messages, api_context, instruction, timeout=120):
    next_messages = list(messages)
    next_messages.append({
        "role": "user",
        "content": f"{api_context}\n\n{instruction}"
    })
    return llm_chat(next_messages, temperature=0.2, timeout=timeout)


def handle_get_groups(messages, used_tools):
    used_tools.append("Thực thi Tool [Backend API]: Lấy danh sách các nhóm dịch vụ (GET /services/groups)...")
    api_context = "[KẾT QUẢ TỪ TOOL GET_GROUPS]:\n"

    try:
        backend_url = os.environ.get("BACKEND_API_URL", "http://127.0.0.1:3001/api/v1")
        resp = requests.get(f"{backend_url}/services/groups", timeout=3)

        if resp.status_code == 200:
            groups = resp.json()
            if groups:
                for g in groups:
                    name = g.get("name", "Nhóm dịch vụ")
                    desc = g.get("description", "Không có mô tả")
                    api_context += f"- Nhóm '{name}': {desc}\n"
            else:
                api_context += "Hiện tại chưa có nhóm dịch vụ nào."
        else:
            api_context += "Hiện tại không lấy được danh sách nhóm dịch vụ."
    except Exception as e:
        api_context += f"Lỗi gọi Backend API: {e}"

    instruction = (
        "Hãy tổng hợp kết quả này để trả lời người dùng thật tự nhiên, thân thiện, ngắn gọn và có duyên. "
        "Bạn là nhân viên tư vấn AI của Fixago. Nếu có dịch vụ phù hợp, hãy mời khách nói tình trạng cần sửa để được tư vấn tiếp."
    )
    return run_second_llm(messages, api_context, instruction)


def handle_get_services(answer, messages, used_tools):
    match = re.search(r'search="([^"]*)"', answer)
    raw_search = match.group(1) if match else ""
    search_arg = normalize_service_search(raw_search)

    used_tools.append(f'Thực thi Tool [Backend API]: Tìm kiếm dịch vụ với từ khóa "{search_arg}"...')

    try:
        backend_url = os.environ.get("BACKEND_API_URL", "http://127.0.0.1:3001/api/v1")
        resp = requests.get(
            f"{backend_url}/services",
            params={"search": search_arg, "limit": 10},
            timeout=3
        )

        if resp.status_code != 200:
            return (
                "Dạ hiện mình chưa lấy được bảng giá từ hệ thống. "
                "Fixago vẫn có thể cử thợ đến kiểm tra thực tế và báo chi phí rõ ràng trước khi làm. "
                "Bạn muốn mình hỗ trợ đặt lịch không ạ?"
            )

        services = resp.json().get("data", [])

        if not services and search_arg in ["máy lạnh", "điện lạnh", "máy giặt"]:
            resp = requests.get(
                f"{backend_url}/services",
                params={"search": "điện", "limit": 10},
                timeout=3
            )
            if resp.status_code == 200:
                services = resp.json().get("data", [])

        if not services:
            return (
                f"Dạ hiện mình chưa thấy dịch vụ khớp chính xác với '{search_arg}' trong hệ thống. "
                "Nhưng Fixago có thể cử thợ đến kiểm tra thực tế và báo phương án, chi phí rõ ràng trước khi làm. "
                "Bạn muốn mình hỗ trợ đặt lịch không ạ?"
            )

        price_summary = build_price_summary(services)

        if price_summary:
            return (
                f"Dạ Fixago có các dịch vụ phù hợp với nhu cầu của bạn.\n\n"
                f"{price_summary}\n\n"
                "Chi phí thực tế có thể thay đổi theo tình trạng tại nhà, nhưng thợ sẽ báo rõ trước khi làm. "
                "Bạn muốn mình hỗ trợ đặt lịch không ạ?"
            )

        return (
            "Dạ Fixago có thể hỗ trợ tình trạng này. "
            "Hiện hạng mục này cần thợ kiểm tra thực tế để báo chi phí chính xác trước khi làm. "
            "Bạn muốn mình hỗ trợ đặt lịch không ạ?"
        )

    except Exception as e:
        return (
            f"Dạ hiện mình chưa lấy được bảng giá do lỗi hệ thống: {e}. "
            "Bạn có thể để lại thông tin, Fixago sẽ hỗ trợ kiểm tra và báo giá rõ ràng trước khi làm ạ."
        )


def handle_get_promotions(messages, used_tools):
    used_tools.append("Thực thi Tool [Backend API]: Lấy danh sách ưu đãi (GET /discounts/available)...")
    api_context = "[KẾT QUẢ TỪ TOOL GET_PROMOTIONS]:\n"

    try:
        backend_url = os.environ.get("BACKEND_API_URL", "http://127.0.0.1:3001/api/v1")
        resp = requests.get(f"{backend_url}/discounts/available", timeout=3)

        if resp.status_code == 200:
            # Backend returns a plain array (no { data: [] } wrapper)
            raw = resp.json()
            promos = raw if isinstance(raw, list) else raw.get("data", [])
            if promos:
                for p in promos:
                    name = p.get("name", "Giảm giá")
                    api_context += f"- Khuyến mãi '{name}': "
                    if p.get("code"):
                        api_context += f"Mã {p.get('code')}, "
                    if p.get("discountType") == 1:
                        api_context += f"giảm {p.get('discountValue', 0)}%"
                        if p.get("maxDiscountAmount"):
                            api_context += f" tối đa {p.get('maxDiscountAmount')} VNĐ"
                    else:
                        api_context += f"giảm {p.get('discountValue', 0)} VNĐ"
                    api_context += ".\n"
            else:
                api_context += "Hiện tại chưa có chương trình khuyến mãi nào."
        else:
            api_context += "Hiện tại không lấy được thông tin khuyến mãi."
    except Exception as e:
        api_context += f"Lỗi gọi Backend API: {e}"

    instruction = (
        "Hãy thông báo kết quả này cho người dùng một cách hấp dẫn, tự nhiên và chân thành. "
        "Nếu chưa có khuyến mãi, nói nhẹ nhàng và mời khách mô tả nhu cầu để Fixago tư vấn dịch vụ phù hợp."
    )
    return run_second_llm(messages, api_context, instruction)


def resolve_service_id(description):
    """
    Fetch a real serviceId from the backend that matches the booking description.
    Backend requires at least one detail in POST /bookings — never return None.
    Strategy:
      1. Search by description keyword (normalized group key)
      2. If no match, fall back to first active service in the system
    Returns (serviceId, serviceGroupId).
    Raises RuntimeError if backend is completely unreachable.
    """
    backend_url = os.environ.get("BACKEND_API_URL", "http://127.0.0.1:3001/api/v1")
    search_key = normalize_service_search(description)

    try:
        # Step 1: search by keyword
        resp = requests.get(
            f"{backend_url}/services",
            params={"search": search_key, "limit": 1, "isActive": True},
            timeout=3
        )
        if resp.status_code == 200:
            data = resp.json().get("data", [])
            if data:
                return data[0].get("id"), data[0].get("serviceGroupId")

        # Step 2: fallback — any active service
        resp2 = requests.get(
            f"{backend_url}/services",
            params={"limit": 1, "isActive": True},
            timeout=3
        )
        if resp2.status_code == 200:
            data2 = resp2.json().get("data", [])
            if data2:
                print(f"resolve_service_id: no match for '{search_key}', using fallback service id={data2[0].get('id')}")
                return data2[0].get("id"), data2[0].get("serviceGroupId")

    except Exception as e:
        print(f"resolve_service_id failed: {e}")

    raise RuntimeError("Không thể lấy thông tin dịch vụ từ hệ thống để tạo đơn.")


def handle_create_booking(answer, used_tools):
    desc_match = re.search(r'description="([^"]*)"', answer)
    name_match = re.search(r'name="([^"]*)"', answer)
    phone_match = re.search(r'phone="([^"]*)"', answer)
    addr_match = re.search(r'address="([^"]*)"', answer)

    desc = desc_match.group(1).strip() if desc_match else "Khách hàng yêu cầu thợ đến kiểm tra"
    name = name_match.group(1).strip() if name_match else "Khách hàng"
    phone = phone_match.group(1).strip() if phone_match else ""
    address = addr_match.group(1).strip() if addr_match else "Chưa cung cấp"

    used_tools.append(f'Thực thi Tool [Backend API]: Tạo đơn đặt lịch cho "{name}", sđt "{phone}", địa chỉ "{address}" với lỗi "{desc}"...')

    api_context = "[KẾT QUẢ TỪ TOOL CREATE_BOOKING]:\n"

    if not phone:
        return "Dạ mình còn thiếu số điện thoại để tạo lịch. Bạn cho mình xin số điện thoại liên hệ nhé."

    try:
        backend_url = os.environ.get("BACKEND_API_URL", "http://127.0.0.1:3001/api/v1")

        # Resolve a real serviceId — backend requires at least 1 detail
        service_id, _ = resolve_service_id(desc)
        booking_payload = {
            "guestPhone": phone,
            "contactName": name,
            "contactPhone": phone,
            "address": {
                "addressLine": address
            },
            "priority": 0,
            "customerNote": desc,
            "details": [{"serviceId": service_id, "quantity": 1}]
        }

        resp = requests.post(f"{backend_url}/bookings", json=booking_payload, timeout=5)

        if resp.status_code in [200, 201]:
            bdata = resp.json()
            booking_code = bdata.get("bookingCode", "N/A")
            api_context += f"OK:{booking_code}"
        else:
            api_context += f"ERR:{resp.text[:200]}"
    except Exception as e:
        api_context += f"ERR:{e}"

    if api_context.startswith("[KẾT QUẢ TỪ TOOL CREATE_BOOKING]:\nOK:"):
        booking_code = api_context.split("OK:", 1)[1].strip()
        return (
            f"Đặt lịch thành công rồi ạ! "
            f"Mã đơn: {booking_code}. "
            f"Khách hàng: {name} | SĐT: {phone} | Địa chỉ: {address}. "
            f"Vấn đề: {desc}. "
            f"Thợ Fixago sẽ liên hệ sớm để hỗ trợ bạn nhé."
        )

    err = api_context.split("ERR:", 1)[1].strip() if "ERR:" in api_context else api_context
    return f"Xin lỗi, hiện mình không thể tạo đơn lúc này. Lỗi: {err}"


def repair_booking_tool_call_if_needed(answer, query, history):
    if "CALL_TOOL" in answer:
        return answer

    extracted = extract_booking_from_text(answer)
    if not (extracted.get("name") and extracted.get("phone") and extracted.get("address")):
        merged = merge_booking_info(query, history)
    else:
        merged = extracted

    if merged.get("name") and merged.get("phone") and merged.get("address"):
        if detect_confirmation(query) or detect_booking_intent(query):
            name = merged.get("name")
            phone = merged.get("phone")
            address = merged.get("address")
            issue = merged.get("issue") or query
            return f'CALL_TOOL: create_booking(name="{name}", phone="{phone}", address="{address}", description="{issue}")'

    return answer


@app.route("/", methods=["GET"])
def index():
    return send_file("demo.html")


@app.route("/api/v1/rag/ingest", methods=["POST"])
def ingest():
    data = request.json or {}
    doc_id = data.get("doc_id")
    text = data.get("text")

    if doc_id is None or not text:
        return jsonify({"status": "error", "message": "Missing 'doc_id' or 'text'"}), 400

    try:
        rag_engine.ingest_document(int(doc_id), text)
        return jsonify({
            "status": "success",
            "message": f"Document {doc_id} ingested successfully"
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/v1/rag/retrieve", methods=["POST"])
def retrieve():
    data = request.json or {}
    query = data.get("query")
    top_k = data.get("top_k", 5)

    if not query:
        return jsonify({"status": "error", "message": "Missing 'query'"}), 400

    try:
        norm_query = rag_engine.normalize_query(query)
        context = rag_engine.retrieve_context(norm_query, top_k=int(top_k))
        return jsonify({"status": "success", "context": context})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/v1/rag/query", methods=["POST"])
def query_rag():
    data = request.json or {}
    query = data.get("query")
    use_cache = data.get("use_cache", True)
    session_id = data.get("session_id")

    if not query:
        return jsonify({"status": "error", "message": "Missing 'query'"}), 400

    if is_prompt_injection(query):
        return jsonify(guardrail_response())

    try:
        if not session_id:
            session_id = str(uuid.uuid4())
            
        session_data = SessionManager.get_session(session_id)
        
        client_history = compact_history(data.get("history", []))
        if client_history and not session_data.get("history"):
            session_data["history"] = client_history
            
        history = session_data.get("history", [])

        system_prompt = data.get("system_prompt", load_system_prompt())
        safe_system = build_safe_system(system_prompt)
        
        booking_state = session_data.get("booking_state", {})
        state_text = (
            f"SESSION_STATE:\n"
            f"- Tên: {booking_state.get('name') or 'Chưa có'}\n"
            f"- SĐT: {booking_state.get('phone') or 'Chưa có'}\n"
            f"- Địa chỉ: {booking_state.get('address') or 'Chưa có'}\n"
            f"- Vấn đề: {booking_state.get('issue') or 'Chưa có'}\n\n"
        )
        safe_system = safe_system.replace("EXAMPLES:\n", state_text + "EXAMPLES:\n")

        db_context = ""
        try:
            norm_query = rag_engine.normalize_query(query)
            db_context = rag_engine.retrieve_context(norm_query, top_k=3)
        except Exception as e:
            print(f"RAG retrieval failed: {e}")

        context = db_context.strip()

        history_text = history_to_text(history)
        prompt_for_cache = (
            f"System: {safe_system}\n"
            f"History:\n{history_text}\n"
            f"Context:\n{context}\n"
            f"Question:\n{query}"
        )

        tokens = rag_engine.tokenize_text(prompt_for_cache)
        prompt_hash = hashlib.sha256(prompt_for_cache.encode("utf-8")).hexdigest()
        cache_key = f"pomai_cache:response:{prompt_hash}"

        if use_cache:
            try:
                with rag_engine.rag_lock:
                    cached_val = rag_engine.cache.get(cache_key)
                    p_get_res = rag_engine.cache.prompt_get(tokens) if cached_val else None

                if cached_val:
                    return jsonify({
                        "status": "success",
                        "response": cached_val.decode("utf-8"),
                        "source": "cache",
                        "tool_calls": [],
                        "cache_metrics": p_get_res or {
                            "hit": True,
                            "cached_tokens": len(tokens),
                            "savings_ratio": 1.0
                        }
                    })
            except Exception as e:
                print(f"Cache lookup failed: {e}")

        messages = [{"role": "system", "content": safe_system}]
        messages.extend(history)

        if context:
            user_msg = (
                "Ngữ cảnh tham khảo:\n"
                f"{context}\n\n"
                "Câu hỏi của khách:\n"
                f"{query}"
            )
        else:
            user_msg = query

        messages.append({"role": "user", "content": user_msg})

        used_tools = []

        if ENABLE_NATIVE_TOOL_CALL:
            # ── Native function calling path (cheese-server --jinja) ──────────
            # Rule-based pre-empt for booking confirmation (stateful, needs context)
            booking_response = maybe_build_booking_response(query, history)
            if booking_response and "CALL_TOOL: create_booking" in booking_response:
                # Already have all info + confirmation → bypass LLM, call directly
                answer = handle_create_booking(booking_response, used_tools)
            elif booking_response and "CALL_TOOL" not in booking_response:
                # Collecting info / asking missing fields — use text response directly
                answer = booking_response
            else:
                # Let the model decide which tool to call (or reply normally)
                tool_name, tool_result, raw_message = llm_chat_with_tools(
                    messages, temperature=0.0, timeout=300
                )

                if tool_name == "get_groups":
                    messages.append({"role": "assistant", "content": None, "tool_calls": raw_message.get("tool_calls")})
                    answer = handle_get_groups(messages, used_tools)

                elif tool_name == "get_services":
                    search = tool_result.get("search", "")
                    # Inject the parsed search arg into a fake CALL_TOOL string
                    # so handle_get_services can parse it (reuse existing handler)
                    fake_answer = f'CALL_TOOL: get_services(search="{search}")'
                    messages.append({"role": "assistant", "content": None, "tool_calls": raw_message.get("tool_calls")})
                    answer = handle_get_services(fake_answer, messages, used_tools)

                elif tool_name == "get_promotions":
                    messages.append({"role": "assistant", "content": None, "tool_calls": raw_message.get("tool_calls")})
                    answer = handle_get_promotions(messages, used_tools)

                elif tool_name == "create_booking":
                    # Double-check confirmation before booking
                    if detect_confirmation(query):
                        name = tool_result.get("name", "")
                        phone = tool_result.get("phone", "")
                        address = tool_result.get("address", "")
                        description = tool_result.get("description", "")
                        fake_answer = f'CALL_TOOL: create_booking(name="{name}", phone="{phone}", address="{address}", description="{description}")'
                        answer = handle_create_booking(fake_answer, used_tools)
                    else:
                        # Model wanted to book but no confirmation — show summary
                        info = merge_booking_info(query, history)
                        info.update({k: v for k, v in tool_result.items() if v})
                        answer = (
                            f"Tên: {info.get('name') or tool_result.get('name', '?')}\n"
                            f"SĐT: {info.get('phone') or tool_result.get('phone', '?')}\n"
                            f"Địa chỉ: {info.get('address') or tool_result.get('address', '?')}\n"
                            f"Vấn đề: {info.get('issue') or tool_result.get('description', '?')}\n"
                            "Bạn xác nhận đặt lịch với thông tin này nhé?"
                        )

                else:
                    # Model replied with text (no tool call)
                    answer = tool_result

        else:
            # ── Legacy text-based tool detection path (no --jinja needed) ─────
            booking_response = maybe_build_booking_response(query, history)
            forced_tool = detect_tool_intent(query)

            if booking_response:
                answer = booking_response
            elif forced_tool:
                answer = forced_tool
            else:
                # Use GBNF grammar to constrain output to either tool call or text
                # This prevents model from hallucinating tool call format
                grammar = load_grammar("fixago_tool_call.gbnf") if not ENABLE_NATIVE_TOOL_CALL else ""
                answer = llm_chat(messages, temperature=0.0, timeout=300, grammar=grammar)

            answer = repair_booking_tool_call_if_needed(answer, query, history)

            if "CALL_TOOL: get_groups" in answer:
                messages.append({"role": "assistant", "content": answer})
                answer = handle_get_groups(messages, used_tools)

            elif "CALL_TOOL: get_services" in answer:
                messages.append({"role": "assistant", "content": answer})
                answer = handle_get_services(answer, messages, used_tools)

            elif "CALL_TOOL: get_promotions" in answer:
                messages.append({"role": "assistant", "content": answer})
                answer = handle_get_promotions(messages, used_tools)

            elif "create_booking" in answer.lower():
                answer = handle_create_booking(answer, used_tools)

        session_data["history"].append({"role": "user", "content": query})
        session_data["history"].append({"role": "assistant", "content": answer})
        session_data["history"] = compact_history(session_data["history"], max_items=12)
        session_data["booking_state"] = merge_booking_info(query, session_data["history"])
        SessionManager.save_session(session_id, session_data)

        if use_cache:
            try:
                with rag_engine.rag_lock:
                    rag_engine.cache.set(cache_key, answer.encode("utf-8"), ttl_ms=600000)
                    rag_engine.cache.prompt_put(tokens, answer.encode("utf-8"), ttl_ms=600000)
            except Exception as e:
                print(f"Cache write failed: {e}")

        return jsonify({
            "status": "success",
            "response": answer,
            "source": "llm",
            "tool_calls": used_tools,
            "cache_metrics": {
                "hit": False,
                "cached_tokens": 0,
                "savings_ratio": 0.0
            }
        })

    except Exception as e:
        return jsonify({
            "status": "error",
            "message": f"LLM query failed: {e}"
        }), 500


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