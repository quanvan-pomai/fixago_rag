"""
core/intent_router.py
Intent detection, service classification, language detection,
and accent-normalization utilities. No external dependencies.
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


# ── Hours / language / price classifiers ─────────────────────────────────────

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
    en_hits = re.findall(
        r'\b(what|how|can|does|price|service|fix|repair|help|install|replace|cost|'
        r'check|please|water|electric|working|hours|schedule|services|available|offer)\b',
        text.lower()
    )
    return "en" if len(set(en_hits)) >= 2 else "vi"


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


# ── Tool intent detection ─────────────────────────────────────────────────────

_BOOKING_TRIGGER_WORDS = [
    "đặt lịch", "đặt thợ", "gọi thợ", "book thợ", "book lịch",
    "hẹn thợ", "cử thợ", "cho thợ", "hỗ trợ đặt",
]

_OFF_DOMAIN_PRODUCT_WORDS = [
    "nước mía", "nước mia", "nuoc mia",
    "bán nước", "ban nuoc", "bán đồ uống", "ban do uong",
    "đồ uống", "do uong", "trà sữa", "tra sua",
    "cà phê", "ca phe", "cafe", "coffee",
    "bán thức ăn", "ban thuc an", "đồ ăn", "do an",
]

_PRIORITY_CHECKS = [
    ("máy lạnh", None, [
        "máy lạnh", "điều hòa", "điều hoà", "tủ lạnh", "tủ đông",
        "air conditioner", "aircon", "air con", "ac unit",
        "refrigerator", "fridge", "freezer",
    ]),
    ("xây dựng", [
        r'tường.{0,10}thấm', r'nhà.{0,10}thấm', r'mái.{0,10}dột',
        r'tường.{0,10}nứt', r'nứt.{0,10}tường',
    ], [
        "thấm dột", "dột nhà", "nhà bị dột",
        "bong sơn", "sơn bị bong", "ẩm mốc",
        "chống dột", "chống thấm", "xử lý thấm",
    ]),
    ("nước", None, [
        "bơm nước", "máy bơm", "bơm không lên",
        "ống nước bị", "vòi nước bị", "bồn cầu bị",
    ]),
]

_SERVICE_MAP = {
    "điện": [
        "điện", "ổ cắm", "bóng đèn", "công tắc", "tủ điện", "aptomat",
        "dây điện", "bảng điện", "trạm sạc", "năng lượng mặt trời", "solar",
        "đèn điện", "quạt điện",
        "chập điện", "cháy điện", "tóe lửa", "hở điện",
        "mất điện", "điện yếu", "nhảy cầu dao", "giật điện", "cúp điện",
        "electrical", "electric", "wire", "circuit", "breaker",
        "socket", "outlet", "switch", "fuse", "wiring",
    ],
    "nước": [
        "nước",
        "ống nước", "ống thoát", "vòi nước", "bồn cầu", "lavabo",
        "bồn tắm", "máy bơm", "van nước", "đường ống", "bể nước",
        "rò rỉ", "rò nước", "nghẹt ống", "tắc ống", "tắc bồn cầu",
        "vỡ ống", "bể ống", "ngập nước", "thoát chậm", "không thoát",
        "nước không chảy", "nước yếu", "bơm không lên",
        "pipe", "plumb", "leak", "drain", "clog", "sewage",
        "toilet", "faucet", "tap", "shower", "sink", "pump",
    ],
    "máy lạnh": [
        "máy lạnh", "điều hòa", "điều hoà", "tủ lạnh", "tủ đông",
        "điện lạnh", "máy giặt",
        "nạp gas", "bơm gas", "hết gas", "không lạnh", "không mát",
        "mát yếu", "lạnh yếu", "vệ sinh máy lạnh", "bảo dưỡng máy lạnh",
        "máy giặt không quay", "máy giặt kêu",
        "air conditioner", "aircon", "air con", "ac ",
        "refrigerator", "fridge", "freezer", "washing machine",
        "washer", "dryer",
        "not cold", "not cooling", "ac not", "aircon not",
    ],
    "xây dựng": [
        "sơn nhà", "sơn lại", "sơn tường", "sơn trần",
        "chống thấm", "ốp lát", "gạch men", "gạch nền",
        "tường", "ban công", "xây dựng", "cải tạo nhà",
        "trát vữa", "bê tông", "nền nhà",
        "paint", "waterproof", "tile", "cement",
        "renovation", "remodel", "construction", "wall", "crack",
    ],
    "thạch cao": [
        "thạch cao", "trần thạch cao", "vách ngăn", "trần nhà",
        "vách thạch cao", "làm trần",
        "plasterboard", "gypsum", "drywall", "ceiling board",
        "false ceiling", "partition", "ceiling",
    ],
}

_NOACCENT_SERVICE = {
    "dien":        "điện",
    "nuoc":        "nước",
    "may lanh":    "máy lạnh",
    "may giat":    "máy lạnh",
    "xay dung":    "xây dựng",
    "thach cao":   "thạch cao",
    "son tuong":   "xây dựng",
    "chong tham":  "xây dựng",
    "ong nuoc":    "nước",
    "bon cau":     "nước",
}

_GROUP_PATTERNS = [
    "dịch vụ gì", "có dịch vụ", "những dịch vụ", "nhóm dịch vụ",
    "fixago làm gì", "bên bạn làm gì", "có sửa gì", "hỗ trợ gì",
    "cung cấp gì", "bao gồm gì", "loại dịch vụ", "hạng mục gì",
    "cung cấp những", "sửa được gì", "làm được gì", "hỗ trợ những gì",
    "cung cấp dịch vụ", "dịch vụ nào", "hạng mục nào", "sửa gì",
    "bên bạn có gì", "fixago có gì", "có những gì",
    "dich vu gi", "co dich vu", "nhung dich vu", "nhom dich vu",
    "fixago lam gi", "co sua gi", "ho tro gi", "cung cap gi",
    "hang muc gi", "lam duoc gi", "sua duoc gi",
    "what service", "what can you", "what do you offer", "what does fixago",
    "services do you", "services available", "what kind of", "what types",
    "what repairs", "do you fix", "can you fix", "what do you fix",
    "what can fixago",
]

_GROUP_NOACCENT = [
    "co sua gi", "lam gi", "ho tro gi", "dich vu gi", "cung cap gi",
    "hang muc gi", "co the sua gi", "sua duoc gi",
    "fixago co gi", "co gi", "ben ban co gi", "co nhung gi",
    "fixago co dich vu gi", "co dich vu gi",
]

_GENERIC_PRICE = [
    "giá cả", "bảng giá", "giá dịch vụ",
    "chi phí dịch vụ", "giá các dịch vụ", "dịch vụ giá",
    "các loại giá", "giá chung", "mức giá",
    "price list", "service price", "how much for",
]
_GENERIC_PRICE_NOACCENT = [
    "gia ca", "bang gia", "gia dich vu", "chi phi dich vu",
    "gia cac dich vu", "muc gia", "bao gia",
]

_INTENT_SIGNALS = [
    "giá", "bao nhiêu", "chi phí", "phí", "báo giá",
    "how much", "price", "cost", "fee",
    "sửa", "lắp", "thay", "bảo dưỡng", "vệ sinh", "kiểm tra",
    "khắc phục", "xử lý", "làm lại", "cần sửa",
    "repair", "fix", "install", "replace", "service", "clean", "check",
    "bị", "hỏng", "lỗi", "hư", "không", "tắc", "vỡ", "rò",
    "thấm", "dột", "kêu", "nhảy", "hay bị", "thường bị", "đang bị",
    "yếu quá", "yếu lắm", "quá yếu", "chảy yếu", "lạnh yếu",
    "chậm quá", "quá chậm", "không đủ", "không ổn",
    "tư vấn", "nên làm", "phải làm", "cần làm", "làm thế nào",
    "nguy hiểm không", "có sao không",
    "broken", "not working", "damaged", "leaking", "clogged", "weak",
]

_SYMPTOM_CONTEXT = [
    r'(máy lạnh|điều hòa|tủ lạnh)\s+\S',
    r'(ống nước|bồn cầu|vòi nước|lavabo)\s+\S',
    r'(điện|đèn|ổ cắm)\s+(bị|hay|không|yếu)',
    r'(tường|mái|trần)\s+(bị|thấm|dột|nứt)',
    r'(air con|aircon|ac)\s+(not|broken|leak)',
]


def _has_specific_service_signal(q: str, raw_lower: str) -> bool:
    if any(k in raw_lower for k in _NOACCENT_SERVICE):
        return True
    for kws in _SERVICE_MAP.values():
        if any(kw in q for kw in kws):
            return True
    return False


def detect_tool_intent(query: str) -> str | None:
    """
    Detect which backend tool to call for a given query.
    Returns a CALL_TOOL string or None.
    """
    raw = (query or "").strip()
    raw_lower = raw.lower()
    q   = normalize_noaccent(raw.lower())

    if any(k in q or k in raw_lower for k in _OFF_DOMAIN_PRODUCT_WORDS):
        return None

    is_booking_trigger = any(k in q for k in _BOOKING_TRIGGER_WORDS)
    if is_booking_trigger and not any(k in q for k in [
        "giá", "bao nhiêu", "how much", "price", "cost", "chi phí", "phí",
    ]):
        return None

    # Promotions
    if any(k in q for k in [
        "khuyến mãi", "giảm giá", "ưu đãi", "voucher", "mã giảm", "coupon",
        "discount", "promotion", "mã khuyến", "giảm %",
        "khuyen mai", "giam gia", "uu dai",
    ]):
        return "CALL_TOOL: get_promotions()"

    # Generic price (no specific service)
    generic_price = any(k in q for k in _GENERIC_PRICE) or any(k in raw_lower for k in _GENERIC_PRICE_NOACCENT)
    if generic_price and not _has_specific_service_signal(q, raw_lower):
        return 'CALL_TOOL: get_services(search="all")'

    # Service groups — only if no specific service is mentioned in the same query
    if any(k in q for k in _GROUP_PATTERNS) and not _has_specific_service_signal(q, raw_lower):
        return "CALL_TOOL: get_groups()"

    # Priority checks (resolve ambiguous cases first)
    for svc_key, regex_pats, literal_pats in _PRIORITY_CHECKS:
        if literal_pats and any(p in q for p in literal_pats):
            return f'CALL_TOOL: get_services(search="{svc_key}")'
        if regex_pats and any(re.search(p, q) for p in regex_pats):
            return f'CALL_TOOL: get_services(search="{svc_key}")'

    # No-accent service fallbacks
    for noaccent_key, svc in _NOACCENT_SERVICE.items():
        if noaccent_key in raw_lower:
            return f'CALL_TOOL: get_services(search="{svc}")'

    # Group no-accent
    if any(k in raw_lower for k in _GROUP_NOACCENT):
        return "CALL_TOOL: get_groups()"

    # Intent signal + service map
    has_intent = any(s in q for s in _INTENT_SIGNALS)
    if not has_intent:
        for pat in _SYMPTOM_CONTEXT:
            if re.search(pat, q):
                has_intent = True
                break

    if has_intent:
        for key, kws in _SERVICE_MAP.items():
            if any(kw in q for kw in kws):
                return f'CALL_TOOL: get_services(search="{key}")'

    # Short single-service clarification
    if len(q.split()) <= 3:
        for key, kws in _SERVICE_MAP.items():
            if any(kw == q.strip() or q.strip().startswith(kw) for kw in kws):
                return f'CALL_TOOL: get_services(search="{key}")'

    return None


# ── Generic price query helper ────────────────────────────────────────────────

def _is_generic_price_query(q_lower: str) -> bool:
    """Return True when the query asks about price without naming a specific service."""
    return any(k in q_lower for k in _GENERIC_PRICE + _GENERIC_PRICE_NOACCENT)


# ── Structured intent classification ─────────────────────────────────────────

def classify_intent(query: str):
    """
    Return an IntentResult wrapping detect_tool_intent() with confidence scoring.
    Imported here lazily to avoid circular imports at module load time.
    """
    from core.intent_result import Confidence, IntentResult

    tool_call_str = detect_tool_intent(query)
    signals: list = []
    confidence = Confidence.HIGH
    ambiguity = None

    q_lower = (query or "").lower()

    if tool_call_str and "get_services" in tool_call_str:
        if _is_generic_price_query(q_lower) or 'search="all"' in tool_call_str:
            confidence = Confidence.MEDIUM
            ambiguity = "generic price — specific service unclear"
        else:
            signals.append("explicit_service_keyword")
    elif tool_call_str and "get_groups" in tool_call_str:
        signals.append("list_services_keyword")
    elif tool_call_str and "get_promotions" in tool_call_str:
        signals.append("promotions_keyword")
    elif tool_call_str is None:
        if not query.strip():
            confidence = Confidence.LOW
            ambiguity = "empty query"

    return IntentResult(
        tool_call_str=tool_call_str,
        confidence=confidence,
        matched_signals=signals,
        ambiguity_reason=ambiguity,
    )
