"""
core/guardrails.py
Prompt injection detection, static fallback answers, and off-topic guardrails.
"""
from core.intent_router import normalize_noaccent, has_tokens, is_hours_question

_FIXIE_GREETING = (
    "Chào mừng Quý khách hàng đã đến với Fixago — nền tảng dịch vụ sửa chữa xây dựng uy tín. "
    "Em là Fixie, trợ lý ảo của Fixago, hân hạnh được hỗ trợ!"
)

_IDENTITY_PATTERNS = [
    "bạn là ai", "ban la ai", "mày là ai", "you are", "who are you",
    "tên bạn", "ten ban", "tên gì", "ten gi", "bạn tên", "ban ten",
    "fixie là ai", "fixie la ai", "fixie là gì", "ai là fixie",
    "em là ai", "em tên gì", "giới thiệu bản thân", "gioi thieu",
    "bạn là gì", "ban la gi",
]

_GREETING_PATTERNS = [
    "xin chào", "xin chao", "chào bạn", "chao ban", "hello", "hi fixie",
    "hi fixago", "chào fixie", "chao fixie", "hey fixie", "hey fixago",
    "good morning", "good afternoon", "good evening",
    "chào buổi", "chao buoi",
]


def is_greeting_or_identity(query: str) -> bool:
    q = (query or "").strip().lower()
    # Pure greeting (short, no service question)
    _has_service = any(k in q for k in [
        "dịch vụ", "dich vu", "giá", "gia", "sửa", "sua", "đặt lịch",
        "dat lich", "bao nhiêu", "bao nhieu", "khuyến mãi", "khuyen mai",
    ])
    if _has_service:
        return False
    return any(p in q for p in _IDENTITY_PATTERNS + _GREETING_PATTERNS)


_AREA_RESPONSE = (
    "Dạ Fixago hiện đang phục vụ tại TP. Hồ Chí Minh, cụ thể là Quận 2, Quận 9 và TP. Thủ Đức ạ. "
    "Anh/chị đang ở khu vực nào để mình xem hỗ trợ được không nhé?"
)

_AREA_PATTERNS = [
    "khu vực nào", "khu vuc nao", "vùng nào", "vung nao",
    "phục vụ ở đâu", "phuc vu o dau", "hoạt động ở đâu", "hoat dong o dau",
    "có ở", "co o", "phủ sóng", "phu song",
    "quận mấy", "quan may", "địa bàn", "dia ban",
    "fixago ở đâu", "fixago o dau", "địa chỉ fixago", "dia chi fixago",
    "có ở quận", "co o quan", "có tới", "co toi",
    "thủ đức", "thu duc", "quận 2", "quan 2", "quận 9", "quan 9",
    "hồ chí minh", "ho chi minh", "tphcm", "hcm",
    "có hỗ trợ", "co ho tro", "có phục vụ", "co phuc vu",
]


def is_area_question(query: str) -> bool:
    q = normalize_noaccent((query or "").lower())
    return any(p in q for p in _AREA_PATTERNS)


# ── Static FAQ fast-paths ─────────────────────────────────────────────────────

_FAQ = [
    (
        ["thanh toán", "thanh toan", "trả tiền", "tra tien", "payment", "pay",
         "tiền mặt", "tien mat", "chuyển khoản", "chuyen khoan", "cash", "transfer"],
        "Dạ Fixago nhận thanh toán bằng tiền mặt hoặc chuyển khoản ngân hàng ạ 💳"
    ),
    (
        ["phí di chuyển", "phi di chuyen", "phí đi lại", "phi di lai",
         "tính thêm phí", "tinh them phi", "travel fee", "transport fee",
         "đi lại tính tiền", "di lai tinh tien", "phí xăng", "phi xang",
         "bao gồm di chuyển", "bao gom di chuyen"],
        "Dạ chi phí di chuyển đã bao gồm trong giá dịch vụ rồi ạ — anh/chị không phát sinh thêm phí đi lại 😊"
    ),
    (
        ["bao lâu", "bao lau", "mấy phút", "may phut", "confirm", "xác nhận lịch",
         "xac nhan lich", "how long", "how soon", "khi nào", "khi nao",
         "phản hồi", "phan hoi", "liên hệ lại", "lien he lai", "thời gian xác nhận"],
        "Dạ sau khi đặt lịch, thợ sẽ liên hệ xác nhận trong vòng 15–30 phút ạ ⏱️"
    ),
    (
        ["đúng thợ", "dung tho", "thợ nào đến", "tho nao den", "ai đến",
         "biết thợ nào", "biet tho nao", "thông tin thợ", "thong tin tho",
         "thợ có uy tín", "tho co uy tin", "verify technician", "which technician"],
        "Dạ trước khi đến, thợ sẽ chủ động liên hệ anh/chị để xác nhận ạ. Anh/chị cũng có thể xem thông tin thợ qua hệ thống Fixago 😊"
    ),
    (
        ["thay khóa", "thay khoa", "khóa cửa", "khoa cua", "khóa", "lock",
         "locksmith", "door lock", "sửa khóa", "sua khoa"],
        "Dạ hiện Fixago chưa hỗ trợ dịch vụ thay khóa cửa ạ. Anh/chị cần hỗ trợ dịch vụ khác như điện, nước hay máy lạnh không?"
    ),
    (
        ["đặt lịch như thế nào", "dat lich nhu the nao", "cách đặt", "cach dat",
         "how to book", "how to order", "đặt hẹn", "dat hen", "book như thế nào",
         "đăng ký", "dang ky", "order"],
        "Dạ anh/chị chỉ cần nhắn cho mình tên, số điện thoại, địa chỉ và dịch vụ cần là mình đặt lịch ngay ạ 📋 Thợ sẽ liên hệ xác nhận trong 15–30 phút!"
    ),
]


def _faq_fallback(query: str) -> str:
    """Return a static FAQ answer if query matches, else empty string."""
    q = normalize_noaccent((query or "").lower())
    for keywords, answer in _FAQ:
        if any(k in q for k in keywords):
            return answer
    return ""


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

    # Greeting / identity — always return Fixie's fixed introduction
    if is_greeting_or_identity(query):
        return _FIXIE_GREETING

    # Area / coverage question
    if is_area_question(query):
        return _AREA_RESPONSE

    # Static FAQ (payment, travel fee, confirm time, technician, lock, booking how-to)
    faq_ans = _faq_fallback(query)
    if faq_ans:
        return faq_ans

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

    # Off-topic: product/food/drink sales. This must run before generic
    # service routing so "nuoc mia" is not treated as plumbing "nước".
    _PRODUCT_SALES_Q = [
        "nước mía", "nước mia", "nuoc mia",
        "bán nước", "ban nuoc", "bán đồ uống", "ban do uong",
        "đồ uống", "do uong", "trà sữa", "tra sua",
        "cà phê", "ca phe", "cafe", "coffee",
        "bán thức ăn", "ban thuc an", "đồ ăn", "do an",
    ]
    if any(k in raw_q or k in q for k in _PRODUCT_SALES_Q):
        return (
            "Dạ Fixago không bán nước mía hay đồ uống ạ. "
            "Mình chỉ hỗ trợ dịch vụ sửa chữa điện, nước, máy lạnh, xây dựng và thạch cao tại nhà."
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

    # Short comparison / why Fixago question. Keep deterministic so small models
    # do not generate long marketing lists.
    _COMPARISON_Q = [
        "hơn gì", "hon gi", "khác gì", "khac gi", "khác với", "khac voi",
        "so với", "so voi", "chỗ khác", "cho khac", "bên khác", "ben khac",
        "app khác", "app khac", "nền tảng khác", "nen tang khac",
        "tại sao chọn fixago", "tai sao chon fixago", "sao phải đặt fixago",
        "thay vì", "thay vi", "thợ ngoài", "tho ngoai", "thợ tự do", "tho tu do",
    ]
    if any(k in q for k in _COMPARISON_Q):
        return (
            "Dạ Fixago hơn ở chỗ thợ được xác minh, đặt lịch rõ ràng và chi phí báo trước khi làm. "
            "Nếu có vấn đề sau dịch vụ, Fixago cũng có kênh hỗ trợ để xử lý tiếp cho bạn."
        )

    return ""
