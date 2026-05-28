"""
core/intent_result.py
Structured intent detection result with confidence scoring.
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


class Confidence(str, Enum):
    HIGH   = "high"
    MEDIUM = "medium"
    LOW    = "low"


@dataclass
class IntentResult:
    """Structured result from classify_intent(), wrapping a CALL_TOOL string."""
    tool_call_str: Optional[str]         # exact CALL_TOOL string or None
    confidence: Confidence = Confidence.HIGH
    matched_signals: List[str] = field(default_factory=list)
    ambiguity_reason: Optional[str] = None
