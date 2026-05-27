"""
booking/extractor.py
--------------------
Stateless helpers for extracting and merging booking information
(name, phone, address, issue) from free-form conversation text.
"""
import re
from typing import Dict, List, Optional


# ── Phone extraction ─────────────────────────────────────────────────────────

def extract_phone(text: str) -> Optional[str]:
    if not text:
        return None
    # First try strict 10-digit match (no separators) for highest precision
    m = re.search(r'(?<!\d)((?:\+84|0)\d{9})(?!\d)', text)
    if m:
        raw = m.group(1)
        if raw.startswith('+84'):
            raw = '0' + raw[3:]
        if re.fullmatch(r'0\d{9}', raw):
            return raw

    # Fallback: allow spaces/dots/dashes between digits (e.g. "090 123 4567")
    m2 = re.search(r'(\+84|0)(?:[\s\.\-]?\d){9}(?![\s\.\-]?\d)', text)
    if not m2:
        return None
    raw = re.sub(r'[\s\.\-]', '', m2.group(0))
    # Normalize +84 → 0
    if raw.startswith('+84'):
        raw = '0' + raw[3:]
    # Validate: must be 10 digits starting with 0
    if re.fullmatch(r'0\d{9}', raw):
        return raw
    return None


# ── Label-based field extraction ─────────────────────────────────────────────

def extract_labeled_value(text: str, labels: List[str]) -> Optional[str]:
    """Extract the value after a label like 'Tên: ...' or 'SĐT - ...'."""
    if not text:
        return None
    pattern = "|".join(re.escape(l) for l in labels)
    m = re.search(rf'(?:{pattern})\s*[:\-]\s*(.+)', text, flags=re.IGNORECASE)
    if not m:
        return None
    value = m.group(1).strip()
    # Stop at the next label boundary
    value = re.split(
        r'\n|,?\s*(?:SĐT|Sđt|Phone|Điện thoại|Địa chỉ|Address|Vấn đề|Issue|Tên|Name)\s*[:\-]',
        value
    )[0].strip()
    return value.rstrip('.,; ') or None


def _extract_natural_name(text: str) -> Optional[str]:
    """
    Extract name from natural patterns:
      - "tôi tên X", "mình tên X", "tên tôi là X", "tên mình là X"
      - "tên là X", "tên X"
    """
    m = re.search(
        r'(?:tôi|mình|em|tui)\s+(?:là\s+)?tên\s+(?:là\s+)?([^\s,\.;]+(?:\s+[^\s,\.;]+)?)|'
        r'tên\s+(?:tôi|mình|em|tui)\s+(?:là\s+)?([^\s,\.;]+(?:\s+[^\s,\.;]+)?)|'
        r'tên\s+(?:là\s+)?([A-ZÀÁÂÃÈÉÊÌÍÒÓÔÕÙÚĂĐĨŨƠƯẠẢẤẦẨẪẬẮẰẲẴẶẸẺẼẾỀỂỄỆỈỊỌỎỐỒỔỖỘỚỜỞỠỢỤỦỨỪỬỮỰỲỴỶỸ][a-zA-ZÀÁÂÃÈÉÊÌÍÒÓÔÕÙÚĂĐĨŨƠƯạảấầẩẫậắằẳẵặẹẻẽếềểễệỉịọỏốồổỗộớờởỡợụủứừửữựỳỵỷỹ]+(?:\s+[A-ZÀÁÂÃÈÉÊÌÍÒÓÔÕÙÚĂĐĨŨƠƯẠẢẤẦẨẪẬẮẰẲẴẶẸẺẼẾỀỂỄỆỈỊỌỎỐỒỔỖỘỚỜỞỠỢỤỦỨỪỬỮỰỲỴỶỸ][a-zA-ZÀÁÂÃÈÉÊÌÍÒÓÔÕÙÚĂĐĨŨƠƯạảấầẩẫậắằẳẵặẹẻẽếềểễệỉịọỏốồổỗộớờởỡợụủứừửữựỳỵỷỹ]+)*)|'
        r'(?:tôi|mình|em|tui)\s+là\s+([A-ZÀÁÂÃÈÉÊÌÍÒÓÔÕÙÚĂĐĨŨƠƯẠẢẤẦẨẪẬẮẰẲẴẶẸẺẼẾỀỂỄỆỈỊỌỎỐỒỔỖỘỚỜỞỠỢỤỦỨỪỬỮỰỲỴỶỸ][a-zA-ZÀÁÂÃÈÉÊÌÍÒÓÔÕÙÚĂĐĨŨƠƯạảấầẩẫậắằẳẵặẹẻẽếềểễệỉịọỏốồổỗộớờởỡợụủứừửữựỳỵỷỹ]+(?:\s+[A-ZÀÁÂÃÈÉÊÌÍÒÓÔÕÙÚĂĐĨŨƠƯẠẢẤẦẨẪẬẮẰẲẴẶẸẺẼẾỀỂỄỆỈỊỌỎỐỒỔỖỘỚỜỞỠỢỤỦỨỪỬỮỰỲỴỶỸ][a-zA-ZÀÁÂÃÈÉÊÌÍÒÓÔÕÙÚĂĐĨŨƠƯạảấầẩẫậắằẳẵặẹẻẽếềểễệỉịọỏốồổỗộớờởỡợụủứừửữựỳỵỷỹ]+)*)',
        text, re.IGNORECASE
    )
    _TRAILING_PARTICLES = re.compile(
        r'\s+(?:chứ|nha|ạ|nhé|đó|thôi|này|là|nè|đây|luôn|rồi|không|phải|đúng không|'
        r'không phải|nghen|nhen|ha|hả|vậy|vậy không|đó nhé)$',
        re.IGNORECASE
    )
    if m:
        val = next((g for g in m.groups() if g), None)
        if val:
            val = _TRAILING_PARTICLES.sub('', val).strip()
        return val or None

    # "Name: X" style (English)
    m2 = re.search(r'\bname\s*[:\-]\s*([^\n,;]+)', text, re.IGNORECASE)
    if m2:
        return m2.group(1).strip().rstrip('.,; ') or None

    # Fallback: first capitalized word(s) before a phone number
    # e.g., "Tuấn 0912000111 7 Bạch Đằng" → "Tuấn"
    # e.g., "Khoa, 0902222333" → already handled above via labeled extraction
    phone_match = re.search(r'(?<!\d)(?:\+84|0)\d{9}(?!\d)', text)
    if phone_match:
        before_phone = text[:phone_match.start()].strip().rstrip(',; ')
        # Take last 1-3 words before the phone as name
        words = before_phone.split()
        if 1 <= len(words) <= 3:
            candidate = " ".join(words)
            # Must look like a name: starts with a letter, not a keyword
            _NOT_NAME = ["tên", "name", "sđt", "số", "phone", "địa", "address", "vấn đề",
                         "đặt", "book", "sửa", "mình", "tôi", "em", "tui", "bạn", "tôi",
                         "ơi", "dạ", "xin", "hello", "hi"]
            if (re.match(r'^[a-zA-ZÀ-ỹ]', candidate)
                    and not any(kw in candidate.lower() for kw in _NOT_NAME)):
                return candidate

    return None


def _extract_natural_address(text: str) -> Optional[str]:
    """
    Extract address from natural patterns:
      - "nhà ở X", "địa chỉ X", "ở X", "address X"
      - "tại X", "nhà tại X"
      - fallback: segment starting with digit that looks like a street number
    """
    m = re.search(
        r'(?:nhà\s+ở|nhà\s+tại|địa\s+chỉ|address)\s*[:\s]\s*'
        r'(\S[^\n;\.]{2,80})',
        text, re.IGNORECASE
    )
    if m:
        return m.group(1).strip().rstrip('.,; ') or None

    # "ở X" / "tại X" — require at least a digit or uppercase to avoid false positives
    m2 = re.search(
        r'(?:ở|tại)\s+(\d+\s+[^\n,;\.]{3,60})',
        text, re.IGNORECASE
    )
    if m2:
        return m2.group(1).strip().rstrip('.,; ') or None

    # Fallback: comma/space-separated segment that starts with a number (street number)
    # e.g., "Tên Khoa, 0902222333, 10 Điện Biên Phủ"  →  "10 Điện Biên Phủ"
    # e.g., "Tuấn 0912000111 7 Bạch Đằng"              →  "7 Bạch Đằng"
    phone_in_text = extract_phone(text)
    if phone_in_text:
        # Remove phone so it doesn't confuse address detection
        text_no_phone = text.replace(phone_in_text, " ").replace(
            phone_in_text.replace("0", "+840", 1)[:12], " "
        )
    else:
        text_no_phone = text

    # Look for number-prefixed segment after removing phone
    m3 = re.search(
        r'(?:^|[,\s])\s*(\d{1,3}\s+[^\n,;\.]{3,60})',
        text_no_phone, re.IGNORECASE
    )
    if m3:
        candidate = m3.group(1).strip().rstrip('.,; ')
        # Must contain at least one letter (not just digits = not a phone remnant)
        if re.search(r'[a-zA-ZÀ-ỹ]', candidate):
            return candidate

    return None


def extract_booking_from_text(text: str) -> Dict[str, Optional[str]]:
    """Parse structured booking fields out of a single message."""
    if not text:
        return {}

    # Try labeled extraction first
    name    = extract_labeled_value(text, ["Tên", "Name", "Họ tên", "Khách hàng"])
    phone   = extract_labeled_value(text, ["SĐT", "Sđt", "Phone", "Điện thoại", "Số điện thoại", "số"])
    address = extract_labeled_value(text, ["Địa chỉ", "Address"])
    issue   = extract_labeled_value(text, ["Vấn đề", "Issue", "Lỗi", "Nội dung", "Mô tả"])

    # Phone: labeled extraction may grab non-phone text, fallback to regex
    if not phone or not re.search(r'\d{8,}', phone):
        phone = extract_phone(text)

    # Name: fallback to natural language pattern
    if not name:
        name = _extract_natural_name(text)

    # Address: fallback to natural language pattern
    if not address:
        address = _extract_natural_address(text)

    return {"name": name, "phone": phone, "address": address, "issue": issue}


# ── Intent detection ─────────────────────────────────────────────────────────

# Negation words that cancel booking intent
_NEGATION = [
    "không muốn đặt", "đừng đặt", "chưa muốn", "không đặt", "chỉ hỏi",
    "hỏi thôi", "không cần đặt", "thôi hủy", "hủy", "không cần",
    "chưa đồng ý", "chưa xác nhận", "đặt cái gì",
    "đừng book", "chưa cần đặt", "chỉ tư vấn", "tư vấn thôi",
    "chưa muốn book", "chưa book", "book vội",
]

def detect_negation(query: str) -> bool:
    q = (query or "").lower()
    return any(k in q for k in _NEGATION)


def detect_booking_intent(query: str) -> bool:
    if detect_negation(query):
        return False
    q = (query or "").strip().lower()

    # Exact-phrase patterns — require the keyword to actually mean "I want to book"
    # not just mentions of booking in a comparison/question context
    # e.g. "app đặt thợ khác" → NOT intent; "tôi muốn đặt thợ" → intent
    _CONTEXT_NEGATORS = [
        "app ", "ứng dụng ", "platform ", "dịch vụ khác", "chỗ khác",
        "thợ tự do", "thợ ngoài", "thợ bên ngoài", "thợ khác",
        " khác", "so sánh", "hơn ", "kém ", "bằng ", "giống ",
        "gọi thợ tự", "app đặt", "dịch vụ đặt",
    ]

    for k in ["đặt lịch", "đặt thợ", "gọi thợ", "book thợ", "book lịch",
              "cho thợ đến", "cử thợ", "hẹn thợ", "qua sửa", "đến sửa",
              "đến kiểm tra", "hỗ trợ đặt"]:
        if k in q:
            # Check if this keyword appears inside a negating context
            idx = q.find(k)
            surroundings = q[max(0, idx-20):idx+len(k)+20]
            if any(neg in surroundings for neg in _CONTEXT_NEGATORS):
                continue
            return True

    # "book" alone — only count if it's the main verb, not part of "booking app" etc.
    if re.search(r'\bbook\b', q) and not re.search(r'book\s*(?:ing|ed|er|s\b)', q):
        if not any(neg in q for neg in _CONTEXT_NEGATORS):
            return True

    return False


def detect_confirmation(query: str) -> bool:
    if detect_negation(query):
        return False
    q = (query or "").strip().lower()
    words = ["xác nhận", "đồng ý", "ok", "oke", "okay", "được", "đặt đi",
             "book đi", "làm đi", "chốt", "yes", "ừ", "uh", "confirm",
             "tạo đơn", "chốt đơn"]
    return any(w in q for w in words)


# ── Multi-turn merge ─────────────────────────────────────────────────────────

def merge_booking_info(query: str, history: List[Dict]) -> Dict[str, Optional[str]]:
    """
    Scan conversation history oldest-first, then override with the current query.
    Later messages (including the current query) win for any given field.
    """
    info: Dict[str, Optional[str]] = {"name": None, "phone": None, "address": None, "issue": None}

    for msg in history[-12:]:
        if msg.get("role") != "user":
            continue
        extracted = extract_booking_from_text(msg.get("content", ""))
        for k, v in extracted.items():
            if v:
                info[k] = v  # later messages override earlier ones

    # Current query always overrides
    for k, v in extract_booking_from_text(query).items():
        if v:
            info[k] = v

    # Infer issue from recent user turns if still missing
    if not info.get("issue"):
        issue_hints = ["sửa", "hỏng", "lỗi", "chập", "rò", "nghẹt", "không lạnh",
                       "vỡ", "thấm", "dột", "tắc", "không lên", "không hoạt động"]
        for msg in reversed(history[-12:]):
            if msg.get("role") == "user":
                c = msg.get("content", "")
                if detect_booking_intent(c) or any(h in c.lower() for h in issue_hints):
                    info["issue"] = c
                    break
        if not info.get("issue"):
            info["issue"] = query

    return info
