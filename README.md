# Fixago RAG — Agentic Customer Service Chatbot

An AI-powered customer service chatbot for **Fixago**, a home repair booking platform. The system runs a local LLM (`Qwen 2.5 3B`) on your VPS with native tool calling, RAG for knowledge retrieval, and a NestJS backend API for real service data.

**Key features:**
- ✅ Multi-turn conversation with booking state tracking
- ✅ Native tool calling (get_groups, get_services, get_promotions, create_booking)
- ✅ Deterministic business facts (hours, payment, area) answered in <1ms
- ✅ RAG-powered knowledge retrieval for repair questions
- ✅ Prompt injection protection
- ✅ Language-aware (Vietnamese + English)

---

## Quick Start (< 5 minutes)

### 1. Prerequisites

```bash
# On Ubuntu 20.04 / Debian 11
sudo apt update && sudo apt install -y \
  git cmake build-essential python3 python3-pip python3-venv \
  golang-go curl

# Verify
python3 --version  # Need 3.9+
go version         # Need 1.20+
```

### 2. Clone & Build

```bash
git clone https://github.com/quanvan-pomai/fixago_rag.git
cd fixago_rag

chmod +x build.sh
./build.sh
```

This builds: `cheesebrain`, `pomaidb`, `pomaicache`, and creates `venv/`.

### 3. Download Model

```bash
# Download Qwen 2.5 3B (recommended for 4GB RAM VPS)
huggingface-cli download Qwen/Qwen2.5-3B-Instruct-GGUF \
  qwen2.5-3b-instruct-q4_k_m.gguf \
  --local-dir ./models
```

### 4. Set Environment

```bash
cp .env.example .env
# Edit if needed (defaults work for local dev)
```

---

## Running the System

You need **3 terminals** running simultaneously (or use `screen`/`tmux`).

### Terminal 1: LLM Server (Cheesebrain)

```bash
cd ~/fixago_rag

# For 4GB RAM VPS:
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
```

Wait for:
```
main: model loaded
main: server is listening on http://0.0.0.0:8080
```

**Key flags (CRITICAL):**
- `ENABLE_NATIVE_TOOL_CALL=1` — **REQUIRED** for tool calling
- `--chat-template qwen` — **REQUIRED** for Qwen 2.5 native tool calling format
- `--n-predict 300` — Allows multi-question scenarios (2-3 tool calls)
- `--threads 2` — Match your CPU cores (2-4 for VPS)
- `--flash-attn on` — Optimizes attention for faster inference

### Terminal 2: Backend API

```bash
cd ~/Fix-Go-BackEnd-API
npm run start:prod
```

Wait for:
```
Application is running on: http://localhost:3001/api/v1
```

### Terminal 3: RAG Server

```bash
cd ~/fixago_rag
source venv/bin/activate
python server.py
```

Wait for:
```
Seeding complete.
Starting RAG server on port 8081...
Running on http://127.0.0.1:8081
```

### Verify All Running

```bash
# Test LLM server
curl http://localhost:8080/health

# Test backend API
curl http://localhost:3001/api/v1/health

# Test RAG server (should return quick response)
curl -X POST http://localhost:8081/api/v1/rag/query \
  -H "Content-Type: application/json" \
  -d '{"query": "Fixago làm việc mấy giờ?", "history": []}'
```

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                    CLIENT (Browser / API)                       │
└──────────────────────────────┬──────────────────────────────────┘
                               │ POST /api/v1/rag/query
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│              RAG Server  (Python)  :8081                         │
│  ├─ Prompt injection filter                                      │
│  ├─ Deterministic business layer (hours, payment, area)          │
│  ├─ Off-topic detection                                          │
│  ├─ Booking state machine                                        │
│  ├─ Native tool calling (LLM + function schemas)                 │
│  └─ RAG context retrieval (PomaiDB)                              │
└──────────────────────────────┬───────────────────────────────────┘
                               │
               ┌───────────────┼────────────────────┐
               ▼               ▼                    ▼
        ┌──────────┐  ┌──────────────┐  ┌──────────────────┐
        │ LLM      │  │ Backend API  │  │ Vector DB        │
        │ (Qwen    │  │ (NestJS)     │  │ (PomaiDB)        │
        │ 3B)      │  │ :3001        │  │ RAG vectors      │
        │ :8080    │  │              │  │                  │
        └──────────┘  └──────────────┘  └──────────────────┘
```

**Components:**

| Component | Purpose |
|-----------|---------|
| `cheesebrain` (cheese-server) | Local LLM inference (Qwen 2.5 3B), OpenAI-compatible API |
| `pomaidb` | Vector database for RAG context retrieval |
| `pomaicache` | KV + prompt cache (unused in this deployment) |
| `server.py` | Main orchestrator: routing, tool calling, state tracking |
| `system_prompt.txt` | LLM instructions for tool calling and multi-turn logic |
| Fix-Go Backend API | Real service data API (groups, services, promotions, bookings) |


---

## Testing

### Test Information Queries (36 scenarios)

```bash
cd fixago_rag
source venv/bin/activate
python tests/run_info_tests.py
```

Tests:
- ✅ Service overview (get_groups)
- ✅ Pricing (get_services)
- ✅ Working hours (deterministic: 24/7)
- ✅ Payment method (deterministic: cash/bank)
- ✅ Promotions (get_promotions)
- ✅ Unsupported services (lock rejection)
- ✅ Off-topic detection
- ✅ Edge cases (multi-question, mixed language, location names)

Expected: **100% pass rate (36/36)**

### Test Full Booking Flow

```bash
python tests/test_full_scenarios.py
```

Tests:
- Standard multi-turn booking
- Service queries with tool calling
- Price inquiries
- Prompt injection blocking

---

## API Reference

### POST /api/v1/rag/query

```bash
curl -X POST http://localhost:8081/api/v1/rag/query \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Bạn có dịch vụ gì?",
    "history": [],
    "use_cache": false
  }'
```

**Response:**
```json
{
  "status": "success",
  "response": "Dạ Fixago cung cấp dịch vụ sửa chữa nhà...",
  "source": "llm",
  "tool_calls": ["get_groups()"],
  "cache_metrics": {"hit": false}
}
```

---

## Troubleshooting

### ❌ "Dạ mình có thể hỗ trợ..." (always booking message)

**Problem:** LLM is not calling tools — missing `ENABLE_NATIVE_TOOL_CALL=1` OR `--chat-template qwen`.

**Solution:** Check cheese-server logs:

```bash
tail -20 ~/fixago_rag/cheese.log | grep "Chat format"
```

Should show:
```
srv  params_from_: Chat format: Qwen
```

If it shows "Hermes 2 Pro" instead, restart with both flags:

```bash
pkill -f cheese-server
sleep 2

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

sleep 3
tail -20 cheese.log | grep "Chat format"
```

Both flags are **REQUIRED**:
- `ENABLE_NATIVE_TOOL_CALL=1` — enables `/v1/chat/completions` to accept `tools` parameter
- `--chat-template qwen` — tells cheese-server to use Qwen's native function calling format

### ❌ Multi-question queries return partial responses

**Problem:** `--n-predict` too low for 2-3 questions.  
**Solution:** Increase to 300-400:

```bash
# Current: --n-predict 200
# Change to: --n-predict 300 or 350
```

Each tool call (~get_groups + get_services) needs ~100-150 tokens.

### ❌ "Connection refused" on port 3001

**Problem:** Backend API not running.  
**Solution:**
```bash
cd ~/Fix-Go-BackEnd-API
npm run start:prod
```

### ❌ "ImportError: pomaidb"

**Problem:** Vector DB not built.  
**Solution:**
```bash
cd ~/fixago_rag
make pomaidb
```

### ❌ "Model not found"

**Problem:** GGUF file missing.  
**Solution:**
```bash
huggingface-cli download Qwen/Qwen2.5-3B-Instruct-GGUF \
  qwen2.5-3b-instruct-q4_k_m.gguf \
  --local-dir ./models
```

### ❌ OOM or slow responses

**For 4GB RAM VPS:**
- Use `qwen2.5-3b-instruct-q4_k_m.gguf` (NOT 7B)
- Set `--ctx-size 4096` (NOT higher)
- Set `--threads 2` (match your CPU cores)
- Increase swap: `fallocate -l 4G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile`

---

## Project Structure

```
fixago_rag/
├── cheesebrain/              # LLM server (cheese-server binary)
├── pomaidb/                  # Vector database
├── models/                   # GGUF model files
├── core/
│   ├── guardrails.py         # Injection, off-topic, deterministic business facts
│   ├── intent_router.py      # Language detection, keyword normalization
│   └── orchestrator.py       # Main routing: static → business → booking → tools
├── booking/
│   ├── extractor.py          # Contact info extraction (name, phone, address)
│   ├── handler.py            # Booking flow & state tracking
│   └── state.py              # Multi-turn state (issue, contact, confirmation)
├── system_prompt.txt         # LLM instructions (CRITICAL: tool calling priority)
├── server.py                 # Flask RAG server
├── tests/
│   ├── run_info_tests.py     # Information query tests (36 scenarios)
│   └── test_full_scenarios.py # Booking flow tests
└── .env.example              # Configuration template
```

---

## Configuration Tips

### For 4GB RAM + 2 Core VPS:

```bash
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
```

### For 8GB RAM + 4 Core VPS:

```bash
nohup env ENABLE_NATIVE_TOOL_CALL=1 \
./cheesebrain/build/bin/cheese-server \
  --model ./models/qwen2.5-3b-instruct-q4_k_m.gguf \
  --host 0.0.0.0 \
  --port 8080 \
  --ctx-size 8192 \
  --flash-attn on \
  --threads 4 \
  --n-predict 400 \
  --parallel 2 \
  --chat-template qwen \
  > cheese.log 2>&1 &
```

**Critical flags that MUST be present:**
- `ENABLE_NATIVE_TOOL_CALL=1` — enables tool calling
- `--chat-template qwen` — Qwen 2.5 requires this for function calling
- `--n-predict 300+` — allows multi-question scenarios with multiple tool calls

**Scalable parameters:**
- `--ctx-size`: Larger (4096→8192) for longer conversations
- `--threads`: Match your CPU cores (2→4)
- `--n-predict`: Higher (300→400) for more complex responses
- `--parallel`: More (1→2) for concurrent requests (increases memory)
