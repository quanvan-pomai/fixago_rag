# Phase 4 — Policy Engine, Context Builder, and Hardcoded Rule Reduction

## 1. Policy Type Table

Every request is assigned one `PolicyType` by `policy_for_intent()` in `core/policy.py`.

| PolicyType | Condition | llm_instruction | cache | rag | temp |
|-----------|-----------|----------------|-------|-----|------|
| `SAFETY_WARNING` | "tóe lửa", "rò gas", etc. | — | false | false | 0.1 |
| `WORKING_HOURS` | hours keywords | — | true | false | 0.1 |
| `OFF_TOPIC` | cooking/football/weather | — | true | false | 0.2 |
| `BOOKING_CREATE` | create_booking in tool | confirm booking created | false | false | 0.1 |
| `BOOKING_CONFIRM` | confirmation + booking trigger | summarise + ask confirm | false | false | 0.1 |
| `BOOKING_START` | booking trigger keyword | ask for name/phone/address | false | false | 0.1 |
| `PROMOTION` | get_promotions tool | list code + conditions | true | false | 0.15 |
| `SERVICE_OVERVIEW` | get_groups, HIGH confidence | list ≤6 groups | true | false | 0.15 |
| `SERVICE_PRICE` | get_services, HIGH confidence | price reference, ≤4 bullets | true | false | 0.15 |
| `UNKNOWN_CLARIFY` | get_services, LOW/MEDIUM, or low confidence, no tool | ask one clarifying question | false | false | 0.2 |
| `GENERAL_FIXAGO_QA` | fallthrough | short friendly answer | true | true | 0.2 |

**Priority order:** SAFETY_WARNING → WORKING_HOURS → OFF_TOPIC → BOOKING_CREATE → BOOKING_CONFIRM
→ BOOKING_START → PROMOTION → SERVICE_OVERVIEW → SERVICE_PRICE → UNKNOWN_CLARIFY → GENERAL_FIXAGO_QA

---

## 2. IntentResult Fields and Confidence Rules

**File:** `core/intent_result.py`

```python
@dataclass
class IntentResult:
    tool_call_str: Optional[str]      # CALL_TOOL string or None
    confidence: Confidence            # HIGH / MEDIUM / LOW
    matched_signals: List[str]        # signals that contributed to the match
    ambiguity_reason: Optional[str]   # why confidence is not HIGH
```

**Confidence assignment** (in `classify_intent()`, `core/intent_router.py`):

| Situation | Confidence |
|-----------|-----------|
| Explicit service keyword matched | HIGH |
| get_groups / get_promotions matched | HIGH |
| Generic price query (no service named) | MEDIUM |
| get_services(search="all") | MEDIUM |
| Empty query | LOW |
| No tool, no special signals | HIGH (no reason to downgrade) |

---

## 3. ContextBuilder Usage

**File:** `core/context_builder.py`

```python
from core.context_builder import ContextBuilder
from core.policy import policy_for_intent

policy = policy_for_intent(intent_result, query)
ctx = ContextBuilder().build(
    query=query,
    history=history,
    data_block=data_block,   # None if no tool was called
    rag_context=rag_context, # None if RAG was skipped
    policy=policy,
    booking_state=session.get("booking_state", {}),
    enable_native_tool_call=False,
    detected_intent=intent_str,
    catalog=session.get("catalog_summary", ""),
)
# ctx.system_prompt  — system prompt with policy instruction appended
# ctx.messages       — ready to pass to llm_chat()
# ctx.temperature    — policy-derived temperature
```

The `policy.llm_instruction` is appended under `[HƯỚNG DẪN PHẢN HỒI]:` when non-empty.
The `[DỮ LIỆU HỆ THỐNG]` injection format is preserved unchanged so `output_validator` keeps working.

---

## 4. should_retrieve_context() Decision Tree

**File:** `core/retrieval.py`

```
policy.retrieve_rag == False  →  skip RAG
tool = get_services            →  skip RAG (tool data sufficient)
tool = get_groups              →  skip RAG
tool = get_promotions          →  skip RAG
otherwise                      →  retrieve RAG
```

Only `GENERAL_FIXAGO_QA` policy has `retrieve_rag=True`.
Booking, hours, off-topic, safety, service tool calls all skip retrieval.

---

## 5. Cache Key Composition

**File:** `core/cache_policy.py`

```python
make_cache_key(system_prompt, history_text, data_block, rag_context, query)
# → "pomai_cache:response:<sha256>"
```

Including `data_block` in the key means a price change in the backend creates a new cache entry
rather than returning a stale price. This fixes the Phase 3 stale price risk.

`should_cache_response(policy, backend_ok)` returns False when:
- `policy.should_cache` is False (booking policies, error responses)
- `backend_ok` is False (don't cache error/empty responses)

---

## 6. Adding a New Policy Type

1. Add an entry to `PolicyType` enum in `core/policy.py`
2. Add a rule to `policy_for_intent()` in the correct priority position
3. Add tests in `tests/policy/test_response_policy.py`
4. If the new type should block RAG, confirm `retrieve_rag=False` in the rule
5. If the new type should block caching, confirm `should_cache=False`
6. Add the new type to this table in section 1

---

## 7. Phase 4 Known Limitations

1. **ContextBuilder not yet wired into orchestrator** — `server.py` uses `classify_intent()` and
   `policy_for_intent()` to populate trace fields and control RAG/cache decisions. The
   `ContextBuilder` is available and tested but `core/orchestrator.py` still uses the existing
   inline context construction. Future phase can migrate orchestrator to use `ContextBuilder`.

2. **UNKNOWN_CLARIFY path in legacy tool flow** — when `classify_intent()` returns LOW/MEDIUM
   confidence, `policy_for_intent()` returns `UNKNOWN_CLARIFY`. However the static fallback in
   `guardrails.py` handles vague damage statements ("Hỏng rồi") before the policy engine is
   consulted. The two systems are complementary, not redundant.

3. **Temperature is policy-derived in trace but orchestrator still uses hardcoded values** —
   `trace.policy_type` and `trace.intent_confidence` are logged, but the temperature values
   in `run_legacy_tool_path()` (0.15/0.1/0.2) are not yet driven by `policy.temperature`.
   They happen to match but should be wired explicitly in a future PR.

4. **Native tool call path not covered by policy tests** — `ENABLE_NATIVE_TOOL_CALL=1` path
   is not affected by the Phase 4 policy engine (same as Phase 3).
