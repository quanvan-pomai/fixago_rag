"""Post-turn Pomai Memory writer."""
from __future__ import annotations

import uuid
from typing import Iterable, Optional

from .memory_policy import MemoryWritePolicy, data_hash, mask_pii, normalize_text, now_ms
from .memory_store import MemoryStore
from .memory_types import MemoryEntry, MemoryScope, MemoryType


class MemoryWriter:
    def __init__(self, store: Optional[MemoryStore] = None, policy: Optional[MemoryWritePolicy] = None):
        self.store = store or MemoryStore()
        self.policy = policy or MemoryWritePolicy()
        self.last_rejected_reason = ""

    def write_business_fact(self, content: str, *, source: str, confidence: float = 0.9) -> Optional[MemoryEntry]:
        decision = self.policy.decide_business_fact(content, source=source, confidence=confidence)
        return self._write(content, decision, source=source, tags=decision.tags)

    def write_project_decision(self, content: str, *, session_id: Optional[str] = None, source: str = "user") -> Optional[MemoryEntry]:
        decision = self.policy.decide_user_message(content, source=source)
        if not decision.allowed:
            self.last_rejected_reason = decision.reason
            return None
        decision.scope = MemoryScope.SEMANTIC
        decision.type = MemoryType.DECISION
        return self._write(content, decision, source=source, session_id=session_id, tags=["project", "decision"])

    def update_after_turn(
        self,
        *,
        query: str,
        response: str,
        tool_calls: Optional[Iterable[str]] = None,
        session: Optional[dict] = None,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
        trace_id: Optional[str] = None,
    ) -> int:
        self.last_rejected_reason = ""
        count = 0
        decision = self.policy.decide_user_message(query)
        if decision.allowed:
            if self._write(query, decision, source="user", session_id=session_id, user_id=user_id, trace_id=trace_id, tags=decision.tags):
                count += 1
        else:
            self.last_rejected_reason = decision.reason

        for tool in tool_calls or []:
            content = self._summarize_tool(tool, response)
            tool_decision = self.policy.decide_tool_result(self._tool_name(tool), content)
            if tool_decision.allowed and self._write(content, tool_decision, source="backend_tool", session_id=session_id, trace_id=trace_id, tags=tool_decision.tags, data_hash_value=data_hash(content)):
                count += 1

        if session and len(session.get("history", [])) >= 8:
            summary = self._summarize_history(session.get("history", []))
            summary_decision = self.policy.decide_summary(summary)
            if summary_decision.allowed and self._write(summary, summary_decision, source="session_summary", session_id=session_id, trace_id=trace_id, tags=summary_decision.tags, data_hash_value=data_hash(summary)):
                count += 1
        return count

    def _write(self, content: str, decision, *, source: str, session_id: Optional[str] = None, user_id: Optional[str] = None, trace_id: Optional[str] = None, tags=None, data_hash_value: Optional[str] = None) -> Optional[MemoryEntry]:
        if not decision.allowed:
            self.last_rejected_reason = decision.reason
            return None
        if decision.scope is None or decision.type is None:
            self.last_rejected_reason = "missing_scope_or_type"
            return None
        ts = now_ms()
        safe_content = mask_pii(content)
        entry = MemoryEntry(
            id=f"mem_{uuid.uuid4().hex[:16]}",
            scope=decision.scope,
            type=decision.type,
            content=safe_content,
            normalized_content=normalize_text(safe_content),
            source=source,
            confidence=decision.confidence,
            created_at=ts,
            updated_at=ts,
            expires_at=(ts + decision.ttl_ms) if decision.ttl_ms else None,
            ttl_ms=decision.ttl_ms,
            tags=tags or decision.tags,
            user_id=user_id,
            session_id=session_id,
            trace_id=trace_id,
            data_hash=data_hash_value or data_hash(safe_content),
            pii_level=decision.pii_level,
            allowed_for_prompt=decision.allowed_for_prompt,
        )
        return self.store.upsert_by_hash(entry)

    @staticmethod
    def _tool_name(tool_call: str) -> str:
        text = str(tool_call or "").lower()
        if "services" in text or "get_services" in text:
            return "get_services"
        if "groups" in text or "get_groups" in text:
            return "get_groups"
        if "promotion" in text or "discount" in text or "get_promotions" in text:
            return "get_promotions"
        return "tool"

    def _summarize_tool(self, tool_call: str, response: str) -> str:
        return f"{self._tool_name(tool_call)} result summary: {mask_pii(response)[:500]}"

    @staticmethod
    def _summarize_history(history: list) -> str:
        useful = []
        for msg in history[-8:]:
            role = msg.get("role", "")
            content = mask_pii(str(msg.get("content", "")))
            if content and len(content) > 8:
                useful.append(f"{role}: {content[:160]}")
        return "Session summary: " + " | ".join(useful)


_default_writer: Optional[MemoryWriter] = None


def get_default_writer() -> MemoryWriter:
    global _default_writer
    if _default_writer is None:
        _default_writer = MemoryWriter()
    return _default_writer


def update_after_turn(**kwargs) -> int:
    return get_default_writer().update_after_turn(**kwargs)
