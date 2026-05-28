"""
core/policy.py
Response policy engine: maps intent + query signals to a ResponsePolicy
that controls LLM instruction, caching, RAG retrieval, and temperature.
"""
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from core.intent_result import Confidence, IntentResult


class PolicyType(str, Enum):
    SERVICE_OVERVIEW    = "SERVICE_OVERVIEW"
    SERVICE_PRICE       = "SERVICE_PRICE"
    PROMOTION           = "PROMOTION"
    BOOKING_START       = "BOOKING_START"
    BOOKING_COLLECT_INFO = "BOOKING_COLLECT_INFO"
    BOOKING_CONFIRM     = "BOOKING_CONFIRM"
    BOOKING_CREATE      = "BOOKING_CREATE"
    WORKING_HOURS       = "WORKING_HOURS"
    SAFETY_WARNING      = "SAFETY_WARNING"
    OFF_TOPIC           = "OFF_TOPIC"
    PROMPT_INJECTION    = "PROMPT_INJECTION"
    UNKNOWN_CLARIFY     = "UNKNOWN_CLARIFY"
    GENERAL_FIXAGO_QA   = "GENERAL_FIXAGO_QA"


@dataclass
class ResponsePolicy:
    policy_type: PolicyType
    llm_instruction: str = ""    # appended to system prompt; "" = no extra instruction
    should_cache: bool = True
    retrieve_rag: bool = False
    temperature: float = 0.15


# ── Policy rules ──────────────────────────────────────────────────────────────

_HOURS_KEYWORDS = [
    "giờ làm", "thời gian", "mấy giờ", "giờ mở", "làm việc",
    "hoạt động", "cuối tuần", "chủ nhật", "ngày lễ", "ban đêm",
    "24/7", "working hour", "open", "schedule",
    "gio lam", "thoi gian", "may gio", "cuoi tuan",
]

_SAFETY_KEYWORDS = [
    "tóe lửa", "chạm điện", "rò gas", "mùi gas", "cháy nổ",
]

_OFF_TOPIC_KEYWORDS = [
    "nấu phở", "tình yêu", "love poem", "thơ tình", "bài thơ",
    "nấu ăn", "recipe", "cooking", "bóng đá", "football",
    "thời tiết", "weather", "tin tức", "news",
]

_BOOKING_KEYWORDS = [
    "đặt lịch", "đặt thợ", "gọi thợ", "book thợ", "book lịch",
    "hẹn thợ", "cử thợ", "cho thợ", "hỗ trợ đặt",
]

_BOOKING_CONFIRM_KEYWORDS = ["xác nhận", "ok đặt", "đồng ý", "ok book", "đặt đi", "confirm"]

_BOOKING_CREATE_KEYWORDS  = ["create_booking"]


def policy_for_intent(intent_result: IntentResult, query: str) -> ResponsePolicy:
    """
    Derive a ResponsePolicy from the intent result and raw query.
    Rules evaluated in priority order; first match wins.
    """
    q = (query or "").lower()
    tool = intent_result.tool_call_str or ""

    # 1. Safety
    if any(k in q for k in _SAFETY_KEYWORDS):
        return ResponsePolicy(
            policy_type=PolicyType.SAFETY_WARNING,
            llm_instruction="",
            should_cache=False,
            retrieve_rag=False,
            temperature=0.1,
        )

    # 2. Working hours
    if any(k in q for k in _HOURS_KEYWORDS):
        return ResponsePolicy(
            policy_type=PolicyType.WORKING_HOURS,
            llm_instruction="",
            should_cache=True,
            retrieve_rag=False,
            temperature=0.1,
        )

    # 3. Off-topic
    if any(k in q for k in _OFF_TOPIC_KEYWORDS):
        return ResponsePolicy(
            policy_type=PolicyType.OFF_TOPIC,
            llm_instruction="",
            should_cache=True,
            retrieve_rag=False,
            temperature=0.2,
        )

    # 4. Booking sub-policies (create > confirm > collect > start)
    if "create_booking" in tool:
        return ResponsePolicy(
            policy_type=PolicyType.BOOKING_CREATE,
            llm_instruction="Thông báo đặt lịch thành công, nêu thông tin đã ghi nhận.",
            should_cache=False,
            retrieve_rag=False,
            temperature=0.1,
        )
    if any(k in q for k in _BOOKING_CONFIRM_KEYWORDS) and any(k in q for k in _BOOKING_KEYWORDS + ["xác nhận"]):
        return ResponsePolicy(
            policy_type=PolicyType.BOOKING_CONFIRM,
            llm_instruction="Tóm tắt thông tin đặt lịch và hỏi xác nhận.",
            should_cache=False,
            retrieve_rag=False,
            temperature=0.1,
        )
    if any(k in q for k in _BOOKING_KEYWORDS):
        # Has booking trigger with no service price query
        return ResponsePolicy(
            policy_type=PolicyType.BOOKING_START,
            llm_instruction="Hỏi tên, SĐT, địa chỉ để đặt lịch.",
            should_cache=False,
            retrieve_rag=False,
            temperature=0.1,
        )

    # 5. Promotions
    if "get_promotions" in tool:
        return ResponsePolicy(
            policy_type=PolicyType.PROMOTION,
            llm_instruction="Nêu mã và điều kiện ưu đãi. Không bịa thêm.",
            should_cache=True,
            retrieve_rag=False,
            temperature=0.15,
        )

    # 6. Service overview
    if "get_groups" in tool:
        return ResponsePolicy(
            policy_type=PolicyType.SERVICE_OVERVIEW,
            llm_instruction="Liệt kê các nhóm dịch vụ, tối đa 6 mục.",
            should_cache=True,
            retrieve_rag=False,
            temperature=0.15,
        )

    # 7. Service price — HIGH confidence → SERVICE_PRICE; LOW/MEDIUM → UNKNOWN_CLARIFY
    if "get_services" in tool:
        if intent_result.confidence == Confidence.HIGH:
            return ResponsePolicy(
                policy_type=PolicyType.SERVICE_PRICE,
                llm_instruction=(
                    "Nêu giá tham khảo. Tối đa 4 bullet. "
                    "Không cam kết giá cố định — thực tế phụ thuộc tình trạng thực tế."
                ),
                should_cache=True,
                retrieve_rag=False,
                temperature=0.15,
            )
        else:
            return ResponsePolicy(
                policy_type=PolicyType.UNKNOWN_CLARIFY,
                llm_instruction="Hỏi một câu ngắn để xác nhận dịch vụ khách cần.",
                should_cache=False,
                retrieve_rag=False,
                temperature=0.2,
            )

    # 8. No tool matched, low confidence
    if intent_result.confidence == Confidence.LOW:
        return ResponsePolicy(
            policy_type=PolicyType.UNKNOWN_CLARIFY,
            llm_instruction="Hỏi một câu ngắn để làm rõ nhu cầu của khách.",
            should_cache=False,
            retrieve_rag=False,
            temperature=0.2,
        )

    # 9. Fallthrough
    return ResponsePolicy(
        policy_type=PolicyType.GENERAL_FIXAGO_QA,
        llm_instruction="Trả lời ngắn gọn, thân thiện về dịch vụ Fixago.",
        should_cache=True,
        retrieve_rag=True,
        temperature=0.2,
    )
