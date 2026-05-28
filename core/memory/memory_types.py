"""
core.memory.memory_types
Typed schema for Pomai Memory entries and policy decisions.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class MemoryScope(str, Enum):
    SESSION = "session"
    USER = "user"
    BUSINESS = "business"
    TOOL = "tool"
    SEMANTIC = "semantic"


class MemoryType(str, Enum):
    PREFERENCE = "preference"
    FACT = "fact"
    DECISION = "decision"
    TASK = "task"
    TOOL_RESULT = "tool_result"
    SUMMARY = "summary"
    BOOKING_STATE = "booking_state"


class PIILevel(str, Enum):
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass
class MemoryEntry:
    id: str
    scope: MemoryScope
    type: MemoryType
    content: str
    normalized_content: str
    source: str
    confidence: float
    created_at: int
    updated_at: int
    expires_at: Optional[int]
    ttl_ms: Optional[int]
    tags: List[str] = field(default_factory=list)
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    trace_id: Optional[str] = None
    data_hash: Optional[str] = None
    pii_level: PIILevel = PIILevel.NONE
    allowed_for_prompt: bool = True

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["scope"] = self.scope.value
        data["type"] = self.type.value
        data["pii_level"] = self.pii_level.value
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MemoryEntry":
        return cls(
            id=str(data["id"]),
            scope=MemoryScope(data["scope"]),
            type=MemoryType(data["type"]),
            content=str(data.get("content", "")),
            normalized_content=str(data.get("normalized_content", "")),
            source=str(data.get("source", "")),
            confidence=float(data.get("confidence", 0.0)),
            created_at=int(data.get("created_at", 0)),
            updated_at=int(data.get("updated_at", 0)),
            expires_at=data.get("expires_at"),
            ttl_ms=data.get("ttl_ms"),
            tags=list(data.get("tags", []) or []),
            user_id=data.get("user_id"),
            session_id=data.get("session_id"),
            trace_id=data.get("trace_id"),
            data_hash=data.get("data_hash"),
            pii_level=PIILevel(data.get("pii_level", PIILevel.NONE.value)),
            allowed_for_prompt=bool(data.get("allowed_for_prompt", True)),
        )


@dataclass
class MemoryDecision:
    allowed: bool
    scope: Optional[MemoryScope] = None
    type: Optional[MemoryType] = None
    ttl_ms: Optional[int] = None
    pii_level: PIILevel = PIILevel.NONE
    allowed_for_prompt: bool = True
    confidence: float = 0.0
    reason: str = ""
    tags: List[str] = field(default_factory=list)


@dataclass
class ScoredMemoryEntry:
    entry: MemoryEntry
    score: float
    reason: str


@dataclass
class MemoryRetrievalResult:
    entries: List[ScoredMemoryEntry] = field(default_factory=list)
    enabled: bool = False
    reason: str = ""
    max_injected_tokens: int = 350
    token_budget_used: int = 0

