# Experiment Branch Audit: Clean LLM-Driven Architecture

## Summary
The experiment branch has successfully removed hardcoded keyword checks and deterministic business logic. Qwen 2.5 3B now makes decisions purely based on:
1. **system_prompt.txt** (explicit tool-calling instructions)
2. **Cached/fetched data** (raw API responses)
3. **Native LLM reasoning** (no guardrails, no pre-checks)

---

## Files Analyzed

### ✅ CLEAN FILES (No keyword checks)

#### `core/orchestrator_simple.py` (NEW)
- Pure LLM-driven orchestration
- Imports: `llm_chat_with_tools`, tool formatters, `execute_create_booking`
- **NO detection functions, NO keyword checks, NO hardcoded rules**
- Flow: Query → LLM → Tool Call → Data Cache Check → Feed to LLM → Response

#### `llm_client/client.py`
- Simple wrapper around cheese-server
- **NO grammar constraints, NO GBNF rules**
- **NO keyword filtering**
- Only `max_tokens`, `temperature`, and error handling
- Supports native function calling via `--jinja` flag

#### `core/cache_policy.py`
- Pure caching logic, NO keyword checks
- TTL-based cache invalidation
- Data-only (no response caching)

#### `core/session.py`
- Session management only
- NO intent detection

#### `core/tracer.py`
- Logging/tracing only
- NO keyword checks

---

### ⚠️  LEGACY FILES (Not used in experiment path)

#### `core/orchestrator.py` (OLD - UNUSED)
- Still contains keyword checks
- Uses `detect_tool_intent()`, `is_hours_question()`, etc.
- **NOT imported by `server.py` in experiment branch**
- Left for reference/rollback

#### `core/query_processor.py` (OLD - UNUSED)
- Contains multi-question splitting
- Uses `detect_tool_intent()`, `is_hours_question()`
- **NOT imported by experiment's `orchestrator_simple.py`**
- Marked as legacy in code

#### `booking/handler.py` & `booking/extractor.py` (LEGACY)
- Contains `detect_booking_intent()`, `detect_confirmation()`, `detect_negation()`
- **NOT called by `orchestrator_simple.py`**
- Only `execute_create_booking()` is imported
- Would only be triggered if LLM directly calls `create_booking` tool

---

## Architecture Verification

### Data Flow in Experiment Branch

```
User Query
    ↓
server.py::rag_query()
    ↓
orchestrator_simple.py::run_pure_llm_path()
    ├─ Build messages array
    ├─ Call llm_chat_with_tools(messages)
    │  ↓
    │  Qwen 2.5 3B reads:
    │  - system_prompt.txt (IF/THEN tool-calling rules)
    │  - Chat history
    │  - Current query
    │  ↓
    │  Qwen decides: tool_name (or None for text)
    │  ↓
    ├─ Check data cache for tool_name
    ├─ If MISS: fetch from backend API
    ├─ Format data with format_*_for_llm()
    ├─ Second LLM call with tool results
    │  ↓
    │  Qwen generates response based on data
    │  ↓
    └─ Return response to user

NO INTERMEDIATE KEYWORD CHECKS ✓
```

---

## Key Findings

### ✅ WHAT'S WORKING
1. **Pure LLM path**: No keyword detection middleware
2. **Data-only caching**: Raw API responses, no LLM response caching
3. **Tool calling**: Native Qwen function calling via `llm_chat_with_tools()`
4. **System prompt**: Complete control via `system_prompt.txt`
5. **Clean imports**: No dead imports from deleted files

### ⚠️  POTENTIAL ISSUES
1. **Legacy files still exist**: `orchestrator.py`, `query_processor.py` not used but could cause confusion
2. **Booking detection functions unused**: `detect_booking_intent()`, `detect_confirmation()` in booking module but not called by experiment path
3. **No edge case handling**: LLM response parsing is minimal (assumes JSON tool calls work)

### ✅ WHAT QWEN SEES
When Qwen processes a query:
- **NO hardcoded keyword matchers**
- **NO deterministic business rules**
- **NO pre-filtering**
- **Full freedom to decide what tool to call**
- **Only constraint**: system_prompt.txt instructions

---

## Recommendations

1. **Clean up legacy files** (for experiment purity):
   ```bash
   rm core/orchestrator.py
   rm core/query_processor.py
   ```

2. **Add safeguards** (for robustness):
   - Error handling if LLM doesn't return proper tool structure
   - Fallback if tool data fetching fails
   - Retry logic for transient failures

3. **Monitor Qwen behavior**:
   - Does it follow system_prompt IF/THEN rules?
   - Does it call correct tools for each query type?
   - Does it handle multi-question queries correctly?
   - Does it respond appropriately when data is unavailable?

---

## Conclusion

**The experiment branch is CLEAN** for testing Qwen 2.5 3B's ability to:
- Understand natural language without keyword checks
- Follow system prompt instructions for tool calling
- Generate intelligent responses based on provided data
- Handle multi-turn conversations

There are **NO hidden keyword matchers** or **hardcoded business rules** preventing Qwen from thinking freely.
