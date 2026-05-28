"""
core/tracer.py
Per-request trace object and PII masking utilities.

Every /api/v1/rag/query call creates a RequestTrace, populates it as the
request flows through the pipeline, then calls .emit() before returning.

Logged fields: trace_id, session (first 8 chars), path, detected intent,
normalized service, tool count, cache/backend/llm flags, validation result,
latency.

NEVER logged: system prompt text, full phone numbers, full addresses, names.
"""
import logging
import re
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import List

_tl = threading.local()

_trace_logger = logging.getLogger("fixago.trace")
_audit_logger = logging.getLogger("fixago.tool_audit")


# ── PII helpers ───────────────────────────────────────────────────────────────

def mask_phone(text: str) -> str:
    """Mask phone digits: 0912345678 → 091****678"""
    return re.sub(
        r'(\+84|0)(\d{2})\d{4}(\d{2})',
        lambda m: f"{m.group(1)}{m.group(2)}****{m.group(3)}",
        text,
    )


def mask_address(_text: str) -> str:
    return "[address_redacted]"


def mask_name(_text: str) -> str:
    return "[name_redacted]"


# ── Request trace ─────────────────────────────────────────────────────────────

@dataclass
class RequestTrace:
    """Collects observability data for a single /query request."""

    trace_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    session_id: str = ""
    query_preview: str = ""       # first 80 chars, phone-masked
    path: str = ""                # guardrail / static_fallback / cache_hit /
                                  # legacy_tool / native_tool / rag_llm
    detected_intent: str = ""     # CALL_TOOL string or ""
    normalized_service: str = ""  # "điện" / "nước" / … or ""
    tools_called: List[str] = field(default_factory=list)
    cache_hit: bool = False
    backend_ok: bool = True
    llm_called: bool = False
    validation_result: str = "ok"   # ok / fixed / blocked
    latency_ms: float = 0.0
    # Phase 4 additions
    intent_confidence: str = ""     # high / medium / low
    policy_type: str = ""           # PolicyType.value
    retrieve_context: bool = False  # whether RAG retrieval was performed
    tool_data_hash: str = ""        # first 8 hex chars of SHA256(data_block)
    # Phase 5 memory metadata; raw memory content is never logged.
    memory_retrieval_enabled: bool = False
    memory_entries_selected_count: int = 0
    memory_scopes_used: List[str] = field(default_factory=list)
    memory_write_count: int = 0
    memory_write_rejected_reason: str = ""
    memory_token_budget_used: int = 0
    _start: float = field(default_factory=time.time, repr=False, compare=False)

    def finish(self):
        self.latency_ms = round((time.time() - self._start) * 1000, 1)

    def emit(self):
        self.finish()
        _trace_logger.info(
            "trace id=%s sess=%.8s path=%s intent=%s svc=%s tools=%d "
            "cache=%s backend_ok=%s llm=%s valid=%s "
            "confidence=%s policy=%s retrieve=%s mem=%s mem_n=%d "
            "mem_scopes=%s mem_writes=%d mem_reject=%s mem_tokens=%d "
            "lat=%.1fms q=%r",
            self.trace_id,
            self.session_id or "-",
            self.path or "-",
            self.detected_intent or "-",
            self.normalized_service or "-",
            len(self.tools_called),
            self.cache_hit,
            self.backend_ok,
            self.llm_called,
            self.validation_result,
            self.intent_confidence or "-",
            self.policy_type or "-",
            self.retrieve_context,
            self.memory_retrieval_enabled,
            self.memory_entries_selected_count,
            ",".join(self.memory_scopes_used) or "-",
            self.memory_write_count,
            self.memory_write_rejected_reason or "-",
            self.memory_token_budget_used,
            self.latency_ms,
            self.query_preview,
        )
        _tl.trace_id = None


# ── Thread-local trace_id for tool audit ─────────────────────────────────────

def get_current_trace_id() -> str:
    return getattr(_tl, "trace_id", None) or "-"


def set_current_trace_id(trace_id: str):
    _tl.trace_id = trace_id


# ── Tool audit event ──────────────────────────────────────────────────────────

def audit_tool(
    tool_name: str,
    fetch_ok: bool,
    item_count: int,
    cache_hit: bool,
    latency_ms: float,
    error_type: str = "",
):
    """Emit a structured tool-call audit log line."""
    _audit_logger.info(
        "tool_audit trace=%s tool=%s ok=%s items=%d cache=%s lat=%.1fms err=%s",
        get_current_trace_id(),
        tool_name,
        fetch_ok,
        item_count,
        cache_hit,
        latency_ms,
        error_type or "-",
    )
