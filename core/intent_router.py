"""
core/intent_router.py
Utility functions for text normalization, language detection, and query classifiers.

Phase 7: Service routing keyword lists removed — the LLM handles routing semantically
via native tool calling (ENABLE_NATIVE_TOOL_CALL=1 with cheesebrain --jinja).
detect_tool_intent() is kept as a no-op stub for backward compatibility with imports.
"""
import re

# ── No-accent normalization ───────────────────────────────────────────────────

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
    "sua chua": "sửa chữa", "tran thach cao": "trần thạch cao",
    "chong tham": "chống thấm", "son nha": "sơn nhà", "lap dat": "lắp đặt",
    "dieu hoa": "điều hòa", "may nuoc nong": "máy nước nóng",
    # Payment/Business keywords
    "thanh toan": "thanh toán", "tien mat": "tiền mặt", "chuyen khoan": "chuyển khoản",
    "lam viec": "làm việc", "hoat dong": "hoạt động", "phuc vu": "phục vụ",
    "o dau": "ở đâu", "co ho tro": "có hỗ trợ", "khoa cua": "khóa cửa",
}


def normalize_noaccent(text: str) -> str:
    t = text.lower()
    for k, v in _NOACCENT_MAP.items():
        t = t.replace(k, v)
    return t


# ── Token matcher ─────────────────────────────────────────────────────────────

def has_tokens(text: str, *token_groups) -> bool:
    """
    Returns True if text contains at least one token from EVERY group.
    Each group is a list of synonymous keywords (OR within group, AND across groups).
    Accent-insensitive.
    """
    t = text.lower()
    t2 = normalize_noaccent(t)
    for group in token_groups:
        if not any(k in t or k in t2 for k in group):
            return False
    return True


# ── Classifiers ───────────────────────────────────────────────────────────────

_HOURS_KEYWORDS = [
    "giờ làm", "thời gian", "mấy giờ", "giờ mở", "làm việc",
    "hoạt động", "cuối tuần", "chủ nhật", "ngày lễ", "ban đêm",
    "lúc nào", "24/7", "working hour", "open", "schedule",
    "gio lam", "thoi gian", "may gio", "gio mo", "cuoi tuan",
]


def is_hours_question(text: str) -> bool:
    t = text.lower()
    return any(k in t for k in _HOURS_KEYWORDS)


def detect_user_language(text: str) -> str:
    """Return 'en' if clearly English, else 'vi'. Used only for static strings."""
    if re.search(r'[àáâãèéêìíòóôõùúýăđơưạảấầẩẫậắằẳẵặẹẻẽếềểễệỉịọỏốồổỗộớờởỡợụủứừửữựỳỷỹỵ]', text, re.IGNORECASE):
        return "vi"

    # More generous English detection: check for any common English word
    en_words = re.findall(
        r'\b(you|your|me|my|i|the|a|an|is|are|am|be|been|being|have|has|had|do|does|did|'
        r'can|could|would|will|should|must|write|poem|love|song|day|today|time|'
        r'what|how|when|where|why|price|service|fix|repair|help|install|replace|cost|'
        r'check|please|water|electric|working|hours|schedule|services|available|offer|code|discount|'
        r'and|or|for|from|to|with|about|by|in|on|at|as|if|no|any|some|all|this|that|these|those)\b',
        text.lower()
    )
    # If we find 3+ common English words, it's likely English
    return "en" if len(en_words) >= 3 else "vi"


def is_price_question(query: str) -> bool:
    q = query.lower()
    price_signals = [
        "bao nhiêu", "bao nhieu", "bao tien", "bao tiền",
        "giá", "gia ca", "gia bao", "chi phí", "chi phi",
        "tốn", "ton bao", "ton khoang", "mất bao", "mat bao",
        "phí", "phi", "tiền", "tien",
        "how much", "price", "cost", "fee", "charge",
        "khoảng bao", "khoang bao", "thường tốn", "thuong ton",
        "trung bình", "trung binh", "estimate",
    ]
    return any(s in q for s in price_signals)


# ── Stub for backward compatibility ──────────────────────────────────────────

def detect_tool_intent(query: str):
    """
    Stub — returns None. Service routing is now handled by the LLM via native
    tool calling (ENABLE_NATIVE_TOOL_CALL=1 + cheesebrain --jinja).
    Kept to avoid ImportError in legacy code paths and tests.
    """
    return None


def classify_intent(query: str):
    """
    Stub — returns a LOW-confidence IntentResult with no tool.
    Policy engine defaults to GENERAL_FIXAGO_QA when no early intent is detected.
    """
    from core.intent_result import Confidence, IntentResult
    return IntentResult(
        tool_call_str=None,
        confidence=Confidence.LOW,
        matched_signals=[],
        ambiguity_reason="semantic_routing_by_llm",
    )


# ── Multi-Question Detection & Splitting ────────────────────────────────────────

def split_multi_questions(query: str) -> list:
    """
    Split a query with multiple questions into separate sub-queries.

    Examples:
    - "Services + prices?" → ["Services?", "prices?"]
    - "Where are you, hours?" → ["Where are you?", "hours?"]
    - "Price and can you install?" → ["Price?", "Can you install?"]

    Returns list of sub-queries (minimum 1, original if no split detected)
    """
    # Sentence splitters: period, question mark, newline
    sentences = re.split(r'[.!?]\s+', query.strip())
    sentences = [s.strip() for s in sentences if s.strip()]

    if len(sentences) > 1:
        return sentences

    # Check for conjunction-based splitting (English)
    if re.search(r'\b(and|or|plus|also|with|with the)\b', query, re.IGNORECASE):
        # Split on 'and' / 'or' while preserving intent
        parts = re.split(r'\s+(and|or|plus|với|với cái)\s+', query, flags=re.IGNORECASE)
        questions = []
        i = 0
        while i < len(parts):
            if parts[i].lower() in ('and', 'or', 'plus', 'và', 'hoặc', 'với', 'với cái'):
                i += 1
                continue
            segment = parts[i].strip()
            if segment and '?' not in segment:
                segment += '?'
            if segment:
                questions.append(segment)
            i += 1
        if len(questions) > 1:
            return questions

    # Check for Vietnamese conjunction-based splitting
    if re.search(r'(và|với|hoặc|cùng|kèm theo)', query):
        parts = re.split(r'[,;]\s*|(và|với|hoặc|cùng|kèm theo)\s+', query)
        questions = []
        for part in parts:
            if part and part.lower() not in ('và', 'với', 'hoặc', 'cùng', 'kèm theo'):
                segment = part.strip()
                if segment and not segment.endswith('?'):
                    segment += '?'
                if segment:
                    questions.append(segment)
        if len(questions) > 1:
            return questions

    # Comma-separated (Vietnamese style: "giá sao, thợ qua được không?")
    if ',' in query and len(query.split(',')) > 1:
        parts = [p.strip() for p in query.split(',')]
        questions = []
        for part in parts:
            if part and not part.endswith('?'):
                part += '?'
            if part:
                questions.append(part)
        if len(questions) > 1:
            return questions

    return [query]


def detect_multi_intents(query: str) -> list:
    """
    Detect which intents are present in a multi-question query.

    Returns: List of intent types: 'service_overview', 'pricing', 'hours', 'payment',
             'area', 'promotions', 'capability', etc.
    """
    intents = []

    # Check for each intent type
    if any(k in query.lower() for k in ["dịch vụ", "dich vu", "services", "offer", "làm gì", "lam gi"]):
        intents.append('service_overview')

    if is_price_question(query):
        intents.append('pricing')

    if is_hours_question(query):
        intents.append('hours')

    if any(k in query.lower() for k in ["thanh toán", "thanh toan", "payment", "trả tiền", "tra tien"]):
        intents.append('payment')

    if any(k in query.lower() for k in ["ở đâu", "o dau", "phục vụ", "phuc vu", "location", "where"]):
        intents.append('area')

    if any(k in query.lower() for k in ["khuyến mãi", "khuyen mai", "giảm giá", "giam gia", "promotion", "discount", "voucher"]):
        intents.append('promotions')

    if any(k in query.lower() for k in ["sửa được", "sua duoc", "khả năng", "kha nang", "capability", "can you", "fix"]):
        intents.append('capability')

    return intents if intents else ['general']


def is_faq_query(query: str) -> bool:
    """
    Fast-path detector for FAQ (Frequently Asked Questions).
    FAQ queries are operational/business questions, NOT service requests or pricing questions.

    Returns True if query matches FAQ keywords:
    - Response time & booking methods
    - Technician tracking
    - Travel fees
    - Company/business info
    - Payment methods (distinct from price inquiries)

    This gate is checked BEFORE semantic routing to avoid router confusion.
    """
    faq_keywords = [
        # Response time, booking methods (Vietnamese)
        "thời gian", "đáp ứng", "đặt lịch", "lịch hẹn", "bao lâu",
        "khi nào", "mấy giờ", "bao giờ", "lâu không",

        # Response time, booking methods (English)
        "response time", "how long", "book", "schedule", "appointment",
        "confirm", "how to book", "booking method", "time to arrive", "when can you",

        # Technician tracking & identification (Vietnamese)
        "thợ", "biết", "theo dõi", "tracking", "app", "lịch sử",
        "thợ nào", "thợ sẽ", "thợ có", "liên hệ", "lien he", "thông báo",

        # Technician tracking & identification (English)
        "technician", "worker", "contact", "notification", "track", "which technician", "who will",

        # Travel fees & service costs (Vietnamese + English)
        "phí di chuyển", "phi di chuyen", "travel fee", "travel cost",
        "chi phí di chuyển", "tính tiền gì", "tiền vận chuyển", "delivery",

        # Company/business info (Vietnamese)
        "công ty", "cong ty", "giới thiệu", "gioi thieu", "về", "chúng ta", "chung ta", "chúng em", "chung em",

        # Company/business info (English)
        "about", "company", "introduce", "information", "services", "what do you offer",

        # Payment methods (Vietnamese + English, as business fact not pricing)
        "thanh toán", "thanh toan", "trả tiền", "tra tien", "fixago",
        "payment method", "pay", "accept", "nhận", "nhan",
    ]

    query_lower = query.lower()
    return any(kw in query_lower for kw in faq_keywords)
