# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Fixago RAG** is an agentic customer service chatbot for home repair booking. It runs a local LLM (Qwen 2.5 3B) with native tool calling, RAG for knowledge retrieval, and integrates with a NestJS backend API for real service data.

**Key capabilities:**
- Multi-turn conversation with booking state tracking
- Native tool calling (get_groups, get_services, get_promotions, create_booking)
- Deterministic business facts (hours, payment, area) answered in <1ms
- RAG-powered knowledge retrieval
- Prompt injection protection
- Language-aware (Vietnamese + English)

---

## System Architecture

### Three-Service Architecture
The system requires **3 independent services** running simultaneously:

1. **Cheesebrain (cheese-server)** `:8080` — Local LLM inference engine (Qwen 2.5 3B)
   - OpenAI-compatible `/v1/chat/completions` API
   - **CRITICAL flags required:**
     - `ENABLE_NATIVE_TOOL_CALL=1` — enables `/v1/chat/completions` to accept `tools` parameter
     - `--chat-template qwen` — uses Qwen's native function calling format (NOT Hermes 2 Pro)
     - `--n-predict 300+` — allows 2-3 tool calls per query

2. **Fix-Go Backend API** `:3001` — Real service data (separate repo)
   - Endpoints: `/api/v1/groups`, `/api/v1/services`, `/api/v1/promotions`, `/api/v1/bookings`
   - Provides live pricing, availability, booking confirmation

3. **RAG Server (Python Flask)** `:8081` — Orchestrator & retrieval engine
   - Routing: deterministic business layer → LLM with tools → booking state machine
   - Caches API responses (NOT LLM outputs)
   - Manages multi-turn conversation history

### Request Flow
```
Client → RAG Server :8081/api/v1/rag/query
       → Deterministic business layer (hours, payment, unsupported services)
       → LLM :8080/v1/chat/completions with function schemas
       → Backend API :3001 (if tool calls needed)
       → Response
```

### Core Modules

| Module | Purpose |
|--------|---------|
| `core/orchestrator.py` | Main routing logic: fast path, legacy paths, native tool path, session persistence |
| `core/guardrails.py` | Injection filtering, off-topic detection, deterministic business facts, safety warnings |
| `core/intent_router.py` | Language detection, keyword normalization, multi-question splitting |
| `core/policy.py` | ResponsePolicy engine: maps intent to caching/RAG/temperature decisions |
| `core/prompt_builder.py` | System prompt assembly, history compaction |
| `booking/handler.py` | Booking state machine: issue → contact extraction → confirmation |
| `booking/extractor.py` | Name/phone/address extraction from user input |
| `tools/handlers.py` | API wrappers for get_groups, get_services, get_promotions, create_booking |
| `core/memory/` | Multi-turn conversation memory (retriever, writer, policy, store) |
| `core/cache_policy.py` | Deterministic cache key generation, TTL rules |
| `server.py` | Flask entry point, route handlers, request orchestration |

---

## Building & Running

### Initial Setup
```bash
# Clone and build all submodules (CMake + Go)
./build.sh

# Verify builds
ls cheesebrain/build/bin/cheese-server
ls pomaidb/build/lib/libpomai_core.so
python3 -c "import venv; print('venv ready')"
```

### Running the System (3 terminals required)

**Terminal 1: LLM Server (Cheesebrain)**
```bash
cd ~/fixago_rag

# For 4GB RAM VPS (CRITICAL: both ENABLE_NATIVE_TOOL_CALL and --chat-template required)
nohup env ENABLE_NATIVE_TOOL_CALL=1 \
./cheesebrain/build/bin/cheese-server \
  --model ./models/qwen2.5-3b-instruct-q4_k_m.gguf \
  --host 0.0.0.0 \
  --port 8080 \
  --ctx-size 4096 \
  --flash-attn on \
  --threads 2 \
  --n-predict 300 \
  --parallel 1 \
  --chat-template qwen \
  > cheese.log 2>&1 &

# Verify startup
tail -f cheese.log | grep -E "model loaded|server is listening"
```

**Terminal 2: Backend API** (separate repo: Fix-Go-BackEnd-API)
```bash
cd ~/Fix-Go-BackEnd-API
npm run start:prod
# Expect: "Application is running on: http://localhost:3001/api/v1"
```

**Terminal 3: RAG Server**
```bash
cd ~/fixago_rag
source venv/bin/activate
python server.py
# Expect: "Starting RAG server on port 8081..."
```

### Verify All Services Running
```bash
curl http://localhost:8080/health
curl http://localhost:3001/api/v1/health
curl -X POST http://localhost:8081/api/v1/rag/query \
  -H "Content-Type: application/json" \
  -d '{"query": "Fixago làm việc mấy giờ?", "history": []}'
```

---

## Testing

### Unit Tests (Fast)
```bash
source venv/bin/activate

# Intent routing, guardrails, extraction
pytest tests/unit/

# Policy engine (caching, memory decisions)
pytest tests/policy/ -v

# Memory retrieval/writing
pytest tests/memory/ -v
```

### Integration Tests (Requires Services Running)

**Information queries (36 scenarios)**
```bash
source venv/bin/activate
python tests/run_info_tests.py
# Expected: 36/36 PASS (service overview, pricing, hours, promotions, unsupported)
```

**Full booking flow**
```bash
python tests/test_full_scenarios.py
# Tests: multi-turn booking, service queries, tool calling, injection blocking
```

**Audit scenarios**
```bash
pytest tests/test_audit_scenarios.py -v
# Tests: language switching, multi-question, edge cases
```

### Running a Single Test
```bash
# Single test function
pytest tests/unit/test_guardrails.py::test_injection_block -v

# All tests in a file
pytest tests/policy/test_response_policy.py -v

# Tests matching a pattern
pytest tests/ -k "memory" -v
```

---

## Key Architecture Decisions

### 1. Native Tool Calling (No Hardcoded Keyword Router)
- LLM decides which tool to invoke based on semantic understanding
- Tool schemas in `tools_schema.py` with explicit "MUST call when..." language
- System prompt in `system_prompt.txt` has booking_protocol_CRITICAL rules
- **Why:** Keyword routers fail on synonyms/variations; LLMs are more maintainable

### 2. Deterministic Business Layer (O(1) for Stable Facts)
- `guardrails.py:deterministic_business_reply()` handles hours, payment, unsupported services
- No LLM call → instant response, no hallucination
- Defers to LLM for dynamic data (services, prices, promotions)
- **Why:** Consistency (24/7 always returns 24/7) + Performance + Token efficiency

### 3. Cache Data, Not LLM Responses
- `core/cache_policy.py` caches raw API data (service list, prices, promotions)
- Never cache system prompt facts or LLM outputs
- API responses cached with 30min TTL
- **Why:** Prevents stale LLM facts; API data is stable; reduces token usage

### 4. Prompt Injection Protection
- `guardrails.py:is_prompt_injection()` detects injection patterns
- Blocks attempts to override system instructions
- Off-topic detection prevents repair questions masked as chatter
- **Why:** Home repair domain requires safety; malicious queries could override booking intent

### 5. Multi-Turn Memory & Conversation Compaction
- `core/session.py` tracks conversation state across turns
- `core/memory/` system stores user facts (name, phone, address) separately
- `core/prompt_builder.py:compact_history()` truncates history to stay within context window
- **Why:** Enables multi-turn booking without token explosion; remembers user details

### 6. Two-Stage Booking: Extraction → Confirmation
- `booking/extractor.py` parses contact info from any message
- `booking/handler.py` state machine requires explicit confirmation before create_booking()
- **Why:** Prevents accidental double-bookings; matches conversation flow

---

## Common Development Tasks

### Adding a New Deterministic Business Fact
Edit `core/guardrails.py`, function `deterministic_business_reply()`:
```python
if any(kw in query_norm for kw in ["new_keyword_vi", "new_keyword_en"]):
    return "Dạ [response in Vietnamese]. Answer in English: [response]."
```

### Adding a New Tool
1. Define schema in `tools_schema.py` → function name, description, parameters
2. Implement handler in `tools/handlers.py` → API call + formatting
3. Wire tool in `core/orchestrator.py` → check for intent, call handler
4. Update system prompt if priority routing needed

### Modifying Booking Flow
Edit `booking/handler.py` and `booking/state.py`:
- `BookingState` enum: add states if new flow step needed
- `handle_booking_issue()` / `handle_booking_contact()` / `handle_booking_confirm()` — state handlers

### Tuning Cache or Memory Policy
- `core/cache_policy.py` → TTL, key generation, cache conditions
- `core/memory/memory_policy.py` → what facts to store, how long to keep

### Language-Specific Behavior
Check `core/intent_router.py:detect_user_language()`:
- Returns "vi" or "en"
- Used in `core/orchestrator.py` to select system prompt language
- Booking state machine respects language in responses

---

## Debugging & Troubleshooting

### LLM Not Calling Tools (Always Returns Booking Message)
**Symptom:** Response is always "Dạ mình có thể hỗ trợ..." instead of calling tools.

**Root cause:** Missing `ENABLE_NATIVE_TOOL_CALL=1` OR wrong `--chat-template`.

**Check:**
```bash
tail -20 cheese.log | grep "Chat format"
# Should show: "srv  params_from_: Chat format: Qwen"
# If shows "Hermes 2 Pro" → wrong template
```

**Fix:**
```bash
pkill -f cheese-server
sleep 2
# Restart with BOTH flags (see "Running the System" section)
```

### Multi-Question Queries Incomplete
**Symptom:** "Bạn có dịch vụ nào và giá bao nhiêu?" returns only services, not prices.

**Root cause:** `--n-predict 300` too low (each tool call ~100-150 tokens).

**Fix:**
```bash
# Increase in cheese-server startup
--n-predict 350  # or 400
```

### Import Error: "pomaidb"
**Symptom:** `ImportError: cannot import name 'pomaidb'`

**Root cause:** Vector DB not built.

**Fix:**
```bash
cd ~/fixago_rag
make pomaidb
```

### Backend API Connection Refused
**Symptom:** "Connection refused on port 3001"

**Fix:**
```bash
cd ~/Fix-Go-BackEnd-API
npm run start:prod
```

---

## System Prompt Critical Rules

The system prompt in `system_prompt.txt` defines:
- **Role:** Fixie, Fixago assistant for home repair
- **Language protocol:** Pure Vietnamese input → reply Vietnamese; pure English → English; mixed → Vietnamese
- **Tool calling priority:** Keywords like "dịch vụ", "giá", "khuyến mãi" → immediate tool calls (no text response)
- **Tone:** Concise (max 2 sentences), polite, action-oriented
- **Guardrails:** Emergency handling (gas, fire), off-topic pivot

**Important:** System prompt changes require all three services restarted (especially LLM, as it caches prompts).

---

## Environment & Dependencies

**Python 3.9+** with:
- Flask (Flask server)
- requests (HTTP client)
- dotenv (configuration)

**System dependencies:**
- cmake, build-essential (for C++ builds)
- golang 1.20+ (for cheesepath)
- git (for submodules)

**Configuration:** `.env` (created from `.env.example`)
- `BACKEND_API_URL=http://127.0.0.1:3001/api/v1`
- `LLM_API_URL=http://127.0.0.1:8080/v1/chat/completions`
- `RAG_PORT=8081`

---

## Memory System (Phase 4)

The project includes a persistent conversation memory system:

- **Memory types:** UserInfo (name, phone, address), ServicePreference, BookingHistory, Issues
- **Memory policy:** Keeps facts across turns, masks PII in logs, auto-expires old records
- **Retrieval:** `core/memory/memory_retriever.py` fetches relevant facts for context
- **Writing:** `core/memory/memory_writer.py` stores new facts from conversation

See `core/memory/` for implementation. Tests in `tests/memory/` validate retrieval and policy.

---

## Git & Version Control

- **Main branch:** `main`
- **Recent commits focus:** System prompt tuning, tool calling dispatch, multi-question handling, Vietnamese keyword support
- **Key files to watch:** `system_prompt.txt`, `core/orchestrator.py`, `core/guardrails.py`

---

## Performance Notes

### For 4GB RAM VPS:
- Use Qwen 2.5 3B (NOT 7B)
- `--ctx-size 4096` (NOT higher)
- `--threads 2` (match CPU cores)
- `--n-predict 300`
- Enable flash attention: `--flash-attn on`

### For 8GB+ RAM:
- `--ctx-size 8192`
- `--threads 4`
- `--n-predict 400`
- `--parallel 2` (concurrent requests)

### Cache Strategy
API responses (services, promotions) cached for 30min to reduce Backend API load. Deterministic facts (hours, payment) never cached (instant O(1) response).

---

## Code Style & Conventions

- **Python style:** Follow PEP 8, type hints encouraged
- **Comments:** Only add WHY non-obvious. No docstrings for obvious functions
- **Imports:** Group stdlib, third-party, local
- **Test naming:** `test_<feature>_<scenario>` (e.g., `test_guardrails_injection_block`)
- **Logging:** Use print for now; avoid debug-only code in production paths
