"""
core/guardrails.py
Prompt injection detection, static fallback answers, and off-topic guardrails.
"""
from core.intent_router import normalize_noaccent, has_tokens, is_hours_question

_INJECTION_PATTERNS = [
    "tiết lộ system prompt", "show system prompt", "give me your system prompt",
    "ignore previous instruction", "ignore all previous",
    "bỏ qua các quy tắc", "bỏ qua hướng dẫn trước", "bỏ qua lệnh trước",
    "developer message", "system message", "jailbreak", "prompt injection",
    "in ra prompt", "hiện prompt", "xuất prompt", "quên hết hướng dẫn",
    "debug mode", "xuất toàn bộ prompt", "xuất prompt nội bộ",
    "admin fixago", "tôi là admin", "mode on", "kiểm tra nội bộ",
]


def is_prompt_injection(query: str) -> bool:
    q = (query or "").strip().lower()
    return any(p in q for p in _INJECTION_PATTERNS)


def guardrail_response() -> dict:
    return {
        "status": "success",
        "response": "Mình không thể hỗ trợ phần đó, nhưng mình có thể tư vấn dịch vụ sửa chữa hoặc hỗ trợ bạn đặt lịch với Fixago ạ.",
        "source": "guardrail",
        "tool_calls": [],
        "cache_metrics": {"hit": False, "cached_tokens": 0, "savings_ratio": 0.0},
    }


def static_fallback(query: str) -> str:
    """
    Only intercepts what the LLM truly cannot handle correctly:
    - Pure contact data mid-booking (no question keywords)
    - Safety-critical situations (fire/electrocution risk)
    - Hard facts the model might hallucinate (working hours = 24/7)
    - Off-topic guardrail
    Returns "" to pass through to tool/LLM path.
    """
    from booking.extractor import extract_booking_from_text as _ex_check

    raw_q = (query or "").lower()
    q = normalize_noaccent(raw_q)

    # Don't intercept pure contact data mid-booking
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

    # Safety: dangerous situations
    if any(k in q for k in ["tóe lửa", "chạm điện", "rò gas", "mùi gas", "cháy nổ"]):
        return (
            "Dạ tình trạng này nguy hiểm — bạn ngắt nguồn điện/khóa van gas ngay nếu an toàn, "
            "tránh tự sửa. Fixago có thể cử thợ đến kiểm tra. Bạn muốn đặt lịch không ạ?"
        )

    # Hard fact: working hours
    _HOURS_TOKENS = ["giờ làm", "thời gian làm", "thoi gian lam", "gio lam viec",
                     "working hour", "lam viec may gio", "ban đêm", "ban dem",
                     "cuối tuần", "cuoi tuan", "chủ nhật", "chu nhat",
                     "ngày lễ", "ngay le", "24/7", "suốt ngày",
                     "mấy giờ", "may gio", "giờ mở", "gio mo", "open"]
    _hours_q = (
        any(k in raw_q for k in _HOURS_TOKENS)
        or has_tokens(raw_q,
            ["giờ", "thời gian", "thoi gian", "lúc nào", "luc nao"],
            ["làm việc", "lam viec", "hoạt động", "hoat dong", "phục vụ", "phuc vu"])
    )
    if _hours_q:
        _has_other_topic = any(k in raw_q for k in [
            "dịch vụ", "dich vu", "khuyến mãi", "khuyen mai", "promotion",
            "giá", "gia", "bao nhiêu", "what service", "services",
            "làm gì", "lam gi", "có gì", "co gi", "hỗ trợ gì",
        ])
        if _has_other_topic:
            return ""
        return (
            "Dạ Fixago hoạt động 24/7, kể cả cuối tuần và ngày lễ — "
            "bạn đặt lịch bất kỳ lúc nào, thợ sẽ liên hệ xác nhận thời gian sớm nhất nhé."
        )

    # Off-topic
    if any(k in q for k in ["nấu phở", "tình yêu", "love poem", "thơ tình", "bài thơ",
                              "nấu ăn", "recipe", "cooking", "bóng đá", "football",
                              "thời tiết", "weather", "tin tức", "news"]):
        return (
            "Dạ mình chỉ hỗ trợ dịch vụ sửa chữa nhà của Fixago thôi ạ 😊 "
            "Bạn cần tư vấn điện, nước, máy lạnh hay xây dựng không?"
        )

    # Ambiguous "cái này" / "nhìn giúp"
    if any(k in q for k in ["cái này", "nhìn giúp", "xem giúp", "xem cái này"]):
        return (
            "Dạ mình cần biết tình trạng cụ thể để tư vấn chi phí. "
            "Bạn mô tả lỗi hoặc hạng mục cần sửa để mình tư vấn nhé?"
        )

    # Short ambiguous damage statement
    _DAMAGE_WORDS = ["hỏng rồi", "hỏng hết", "bị hỏng", "hư rồi", "hư hết"]
    _SERVICE_WORDS = ["điện", "nước", "máy lạnh", "máy giặt", "ống", "vòi", "chập",
                      "rò", "nghẹt", "thạch cao", "sơn", "xây"]
    if any(k in q for k in _DAMAGE_WORDS) and not any(s in q for s in _SERVICE_WORDS):
        return (
            "Dạ bạn cho mình biết thiết bị hay hạng mục nào bị hỏng để mình tư vấn phù hợp nhé? "
            "(ví dụ: điện, nước, máy lạnh, máy giặt...)"
        )

    # Electrical emergency
    _ELECTRIC_NOISE = ["chập điện", "cháy điện", "điện bị", "hở điện"]
    _has_booking_intent = any(k in q for k in ["đặt lịch", "gọi thợ", "đặt thợ", "book thợ", "hẹn thợ"])
    if not _has_booking_intent and any(k in q for k in _ELECTRIC_NOISE):
        return (
            "Dạ tình trạng chập điện cần xử lý ngay. Fixago có thể cử thợ điện đến kiểm tra và sửa an toàn. "
            "Bạn muốn mình hỗ trợ đặt lịch không ạ?"
        )

    # Generic price question with no specific service
    _GENERIC_PRICE_Q = [
        "giá bên", "giá cả", "giá ra sao", "giá như thế", "giá thế nào",
        "bảng giá", "giá chung", "giá dịch vụ", "giá của fixago",
        "gia ca", "gia the nao", "gia dich vu",
    ]
    _has_service_word = any(s in q for s in [
        "điện", "nước", "máy lạnh", "xây", "thạch cao", "ống", "vòi", "bồn",
        "dien", "nuoc", "may lanh", "xay dung", "thach cao",
    ])
    if any(k in q for k in _GENERIC_PRICE_Q) and not _has_service_word:
        return (
            "Dạ giá của Fixago tùy theo hạng mục và tình trạng thực tế — "
            "thợ sẽ báo rõ chi phí trước khi làm bạn nhé. "
            "Bạn đang cần tư vấn dịch vụ nào ạ? (điện, nước, máy lạnh, xây dựng...)"
        )

    return ""
