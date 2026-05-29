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
