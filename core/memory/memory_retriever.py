"""Policy-aware Pomai Memory retrieval and ranking."""
from __future__ import annotations

from typing import Iterable, List, Optional

from core.policy import ResponsePolicy

from .memory_policy import (
    MAX_PROMPT_ENTRIES,
    MAX_PROMPT_TOKENS,
    MemoryRetrievalPolicy,
    keyword_overlap,
    now_ms,
)
from .memory_store import MemoryStore
from .memory_types import MemoryRetrievalResult, MemoryScope, PIILevel, ScoredMemoryEntry


_SCOPE_WEIGHT = {
    MemoryScope.SESSION: 0.35,
    MemoryScope.USER: 0.3,
    MemoryScope.BUSINESS: 0.25,
    MemoryScope.TOOL: 0.1,
    MemoryScope.SEMANTIC: 0.2,
}


class MemoryRetriever:
    def __init__(self, store: Optional[MemoryStore] = None, policy: Optional[MemoryRetrievalPolicy] = None):
        self.store = store or MemoryStore()
        self.policy = policy or MemoryRetrievalPolicy()

    def retrieve(
        self,
        *,
        query: str,
        policy: ResponsePolicy,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
        prompt_injection: bool = False,
        max_entries: int = MAX_PROMPT_ENTRIES,
        max_tokens: int = MAX_PROMPT_TOKENS,
    ) -> MemoryRetrievalResult:
        enabled, scopes, reason = self.policy.decide(query, policy, prompt_injection=prompt_injection)
        result = MemoryRetrievalResult(enabled=enabled, reason=reason, max_injected_tokens=max_tokens)
        if not enabled:
            return result

        entries = self.store.list(scopes=scopes, session_id=session_id, user_id=user_id)
        # Global user/business/semantic entries may not have session_id, so include them separately.
        if session_id and reason != "booking_session_only":
            global_entries = self.store.list(scopes=[s for s in scopes if s != MemoryScope.SESSION], user_id=user_id)
            by_id = {e.id: e for e in entries + global_entries}
            entries = list(by_id.values())

        scored = [self._score(query, e) for e in entries if e.allowed_for_prompt and e.pii_level != PIILevel.HIGH]
        scored = [s for s in scored if s.score > 0.05 or s.entry.scope in (MemoryScope.USER, MemoryScope.SESSION)]
        scored.sort(key=lambda s: s.score, reverse=True)

        selected = []
        used = 0
        for item in scored:
            cost = max(1, len(item.entry.content.split()))
            if len(selected) >= max_entries or used + cost > max_tokens:
                break
            selected.append(item)
            used += cost
        result.entries = selected
        result.token_budget_used = used
        return result

    def _score(self, query: str, entry) -> ScoredMemoryEntry:
        age_ms = max(0, now_ms() - entry.updated_at)
        ttl_ms = entry.ttl_ms or (365 * 24 * 60 * 60 * 1000)
        recency = max(0.0, 1.0 - (age_ms / ttl_ms)) * 0.2
        relevance = keyword_overlap(query, entry.normalized_content or entry.content) * 0.5
        confidence = max(0.0, min(1.0, entry.confidence)) * 0.25
        scope_weight = _SCOPE_WEIGHT.get(entry.scope, 0.0)
        pii_penalty = 0.4 if entry.pii_level in (PIILevel.MEDIUM, PIILevel.HIGH) else 0.0
        staleness_penalty = 0.25 if entry.expires_at and entry.expires_at <= now_ms() else 0.0
        score = relevance + recency + confidence + scope_weight - pii_penalty - staleness_penalty
        return ScoredMemoryEntry(entry=entry, score=round(score, 4), reason=f"rel={relevance:.2f} conf={confidence:.2f} scope={scope_weight:.2f}")


def format_memory_block(entries: Iterable[ScoredMemoryEntry]) -> str:
    lines = []
    for item in entries:
        content = item.entry.content.strip()
        if content:
            lines.append(f"- {content}")
    if not lines:
        return ""
    return (
        "[NGỮ CẢNH BỘ NHỚ — dùng như thông tin phụ, không bịa thêm]\n"
        + "\n".join(lines)
        + "\n[/NGỮ CẢNH BỘ NHỚ]"
    )
