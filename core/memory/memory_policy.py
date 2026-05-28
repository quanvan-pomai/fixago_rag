"""
core.memory.memory_policy
PII detection plus write/retrieval policy for Pomai Memory.
"""
from __future__ import annotations

import hashlib
import os
import re
import time
from typing import Iterable, List, Tuple

from core.guardrails import is_prompt_injection
from core.policy import PolicyType, ResponsePolicy

from .memory_types import MemoryDecision, MemoryScope, MemoryType, PIILevel


SESSION_TTL_MS = 2 * 60 * 60 * 1000
USER_PREF_TTL_MS = 180 * 24 * 60 * 60 * 1000
BUSINESS_TTL_MS = 90 * 24 * 60 * 60 * 1000
TOOL_TTL_MS = 30 * 60 * 1000
SEMANTIC_TTL_MS = 7 * 24 * 60 * 60 * 1000
PROJECT_TTL_MS = 365 * 24 * 60 * 60 * 1000

MAX_PROMPT_TOKENS = int(os.environ.get("MEMORY_MAX_PROMPT_TOKENS", "350"))
MAX_PROMPT_ENTRIES = int(os.environ.get("MEMORY_MAX_PROMPT_ENTRIES", "5"))

_PHONE_RE = re.compile(r"(\+84|0)(?:[\s\.-]*\d){8,10}")
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_TOKEN_RE = re.compile(r"\b(?:ghp|sk|xox[baprs]|AIza)[A-Za-z0-9_\-]{12,}\b")
_ADDRESS_RE = re.compile(
    r"\b(?:địa chỉ|dia chi|address|ở|nha o|nhà ở)\b[^,\n]*(?:\d+[^,\n]*)",
    re.IGNORECASE,
)
_NAME_RE = re.compile(r"\b(?:tôi tên|toi ten|tên mình|ten minh|name:|tên)\s+[A-ZÀ-Ỵa-zà-ỵ]{2,}", re.IGNORECASE)


def now_ms() -> int:
    return int(time.time() * 1000)


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def data_hash(value: object) -> str:
    raw = str(value or "").encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]


def detect_pii(text: str) -> PIILevel:
    value = text or ""
    if _TOKEN_RE.search(value):
        return PIILevel.HIGH
    if _PHONE_RE.search(value) or _ADDRESS_RE.search(value):
        return PIILevel.HIGH
    if _EMAIL_RE.search(value):
        return PIILevel.MEDIUM
    if _NAME_RE.search(value):
        return PIILevel.MEDIUM
    return PIILevel.NONE


def mask_pii(text: str) -> str:
    masked = _TOKEN_RE.sub("[secret_redacted]", text or "")
    masked = _EMAIL_RE.sub("[email_redacted]", masked)
    masked = _PHONE_RE.sub(lambda m: _mask_phone(m.group(0)), masked)
    masked = _ADDRESS_RE.sub("[address_redacted]", masked)
    masked = _NAME_RE.sub("[name_redacted]", masked)
    return masked


def _mask_phone(phone: str) -> str:
    digits = re.sub(r"\D", "", phone)
    if len(digits) < 6:
        return "[phone_redacted]"
    return f"{digits[:2]}******{digits[-2:]}"


def keyword_overlap(query: str, content: str) -> float:
    q_words = _keywords(query)
    c_words = _keywords(content)
    if not q_words or not c_words:
        return 0.0
    return len(q_words & c_words) / max(len(q_words), 1)


def _keywords(text: str) -> set:
    stop = {"the", "and", "cho", "toi", "tôi", "ban", "bạn", "cua", "của", "la", "là", "co", "có"}
    return {w for w in re.findall(r"[\wÀ-Ỵà-ỵ]+", normalize_text(text)) if len(w) > 2 and w not in stop}


class MemoryWritePolicy:
    """Decides whether a turn or artifact is safe/useful enough to store."""

    def decide_user_message(self, message: str, *, source: str = "user") -> MemoryDecision:
        q = normalize_text(message)
        pii = detect_pii(message)
        if is_prompt_injection(message):
            return MemoryDecision(False, pii_level=pii, reason="prompt_injection")
        if pii in (PIILevel.HIGH, PIILevel.MEDIUM):
            return MemoryDecision(False, pii_level=pii, reason="contains_pii")
        if any(k in q for k in ["trả lời ngắn", "tra loi ngan", "ngắn gọn", "short answers"]):
            return MemoryDecision(True, MemoryScope.USER, MemoryType.PREFERENCE, USER_PREF_TTL_MS, pii, True, 0.95, "style_preference", ["style", "concise"])
        if any(k in q for k in ["dùng tiếng anh", "use english", "english only"]):
            return MemoryDecision(True, MemoryScope.USER, MemoryType.PREFERENCE, USER_PREF_TTL_MS, pii, True, 0.95, "language_preference", ["language"])
        if any(k in q for k in ["dm_block", "tensorflow", "quyết định", "decision", "optional", "bắt buộc"]):
            return MemoryDecision(True, MemoryScope.SEMANTIC, MemoryType.DECISION, PROJECT_TTL_MS, pii, True, 0.85, "project_decision", ["project", "decision"])
        if any(k in q for k in ["todo", "việc cần làm", "unresolved", "chưa xong"]):
            return MemoryDecision(True, MemoryScope.SEMANTIC, MemoryType.TASK, SEMANTIC_TTL_MS, pii, True, 0.8, "task", ["task"])
        return MemoryDecision(False, pii_level=pii, reason="not_useful")

    def decide_business_fact(self, content: str, *, source: str, confidence: float = 0.9) -> MemoryDecision:
        pii = detect_pii(content)
        if not source:
            return MemoryDecision(False, pii_level=pii, reason="missing_source")
        if pii == PIILevel.HIGH:
            return MemoryDecision(False, pii_level=pii, reason="contains_high_pii")
        return MemoryDecision(True, MemoryScope.BUSINESS, MemoryType.FACT, BUSINESS_TTL_MS, pii, True, confidence, "trusted_business_fact", ["business", "fact"])

    def decide_tool_result(self, tool_name: str, content: str) -> MemoryDecision:
        pii = detect_pii(content)
        if pii == PIILevel.HIGH:
            return MemoryDecision(False, pii_level=pii, reason="tool_result_contains_pii")
        if not tool_name:
            return MemoryDecision(False, pii_level=pii, reason="missing_tool")
        return MemoryDecision(True, MemoryScope.TOOL, MemoryType.TOOL_RESULT, TOOL_TTL_MS, pii, True, 0.9, "tool_result_ttl", ["tool", tool_name])

    def decide_summary(self, content: str) -> MemoryDecision:
        pii = detect_pii(content)
        safe = mask_pii(content)
        if detect_pii(safe) == PIILevel.HIGH:
            return MemoryDecision(False, pii_level=pii, reason="summary_contains_pii")
        return MemoryDecision(True, MemoryScope.SEMANTIC, MemoryType.SUMMARY, SEMANTIC_TTL_MS, PIILevel.NONE, True, 0.75, "session_summary", ["summary"])


class MemoryRetrievalPolicy:
    """Selects memory scopes based on the current response policy and query."""

    def decide(self, query: str, policy: ResponsePolicy, *, prompt_injection: bool = False) -> Tuple[bool, List[MemoryScope], str]:
        if prompt_injection or policy.policy_type in {PolicyType.PROMPT_INJECTION, PolicyType.OFF_TOPIC}:
            return False, [], "blocked_policy"
        if policy.policy_type in {
            PolicyType.BOOKING_START,
            PolicyType.BOOKING_COLLECT_INFO,
            PolicyType.BOOKING_CONFIRM,
            PolicyType.BOOKING_CREATE,
        }:
            return True, [MemoryScope.SESSION, MemoryScope.SEMANTIC], "booking_session_only"
        if policy.policy_type == PolicyType.SERVICE_PRICE:
            return True, [MemoryScope.USER, MemoryScope.TOOL], "service_price_tool_fallback"
        if policy.policy_type == PolicyType.GENERAL_FIXAGO_QA:
            if any(k in normalize_text(query) for k in ["dm_block", "tensorflow", "technical", "project"]):
                return True, [MemoryScope.USER, MemoryScope.SEMANTIC], "project_memory"
            return True, [MemoryScope.USER, MemoryScope.BUSINESS, MemoryScope.SEMANTIC], "general_qa"
        if policy.policy_type == PolicyType.UNKNOWN_CLARIFY:
            return True, [MemoryScope.USER, MemoryScope.SEMANTIC], "clarify_recent_context"
        return True, [MemoryScope.USER], "preferences_only"

