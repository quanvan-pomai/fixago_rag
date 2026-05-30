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

## Step-by-Step Setup Guide

### 1. Prerequisites

**Install system dependencies:**
```bash
# On Ubuntu 20.04 / Debian 11 / Ubuntu 22.04
sudo apt update && sudo apt install -y \
  git cmake build-essential python3 python3-pip python3-venv \
  golang-go curl wget

# Install Hugging Face CLI (needed to download model)
pip install --upgrade huggingface-hub

# Verify installations
python3 --version     # Need 3.9+
go version            # Need 1.20+
cmake --version       # Need 3.15+
huggingface-cli -V    # Verify HF CLI installed
```

### 2. Clone Repository

```bash
git clone https://github.com/quanvan-pomai/fixago_rag.git
cd fixago_rag
```

### 3. Build All Components

**Build cheesebrain, pomaidb, pomaicache, and Python venv:**
```bash
chmod +x build.sh
./build.sh
```

This step takes **5-15 minutes** depending on your CPU. It:
- Builds cheesebrain C++ LLM server (uses CMake + Make)
- Builds pomaidb vector database (C++)
- Creates Python virtual environment with dependencies
- Compiles everything in release mode

**Verify build succeeded:**
```bash
# Check all required binaries exist
test -f ./cheesebrain/build/bin/cheese-server && echo "✓ cheese-server OK" || echo "✗ FAILED"
test -f ./pomaidb/build/lib/libpomai_core.so && echo "✓ pomaidb OK" || echo "✗ FAILED"
test -d ./venv && echo "✓ venv OK" || echo "✗ FAILED"
```

### 4. Download the LLM Model

**Important:** This downloads a **4-5GB file** (Qwen 2.5 3B quantized to Q4_K_M format).

```bash
# Create models directory
mkdir -p ./models

# Download Qwen 2.5 3B (optimized for 4GB RAM VPS)
# This will cache the model locally for faster subsequent runs
huggingface-cli download Qwen/Qwen2.5-3B-Instruct-GGUF \
  qwen2.5-3b-instruct-q4_k_m.gguf \
  --local-dir ./models
```

**Why Q4_K_M?** 
- Size: ~4.5GB (compressed to fit in 4GB RAM when loaded)
- Quality: Very high (minimal quality loss vs full-precision)
- Speed: Fast inference on consumer hardware
- Quantization: 4-bit K-means clustering

**Alternative models:**
```bash
# If 4GB still too much, try Q3_K_M (3.5GB, slightly lower quality):
huggingface-cli download Qwen/Qwen2.5-3B-Instruct-GGUF \
  qwen2.5-3b-instruct-q3_k_m.gguf \
  --local-dir ./models

# For 8GB+ RAM, use Q5_K_M (7GB, higher quality):
huggingface-cli download Qwen/Qwen2.5-3B-Instruct-GGUF \
  qwen2.5-3b-instruct-q5_k_m.gguf \
  --local-dir ./models
```

**Verify model downloaded:**
```bash
ls -lh ./models/qwen*.gguf
# Should show: qwen2.5-3b-instruct-q4_k_m.gguf (4.5G)
```

### 5. Configure Environment

```bash
cp .env.example .env

# Edit .env if needed (defaults work for local development):
# - BACKEND_API_URL=http://127.0.0.1:3001/api/v1
# - LLM_API_URL=http://127.0.0.1:8080/v1/chat/completions
# - RAG_PORT=8081

cat .env
```

---

## Running All Services

The system requires **3 independent services** running simultaneously in separate terminals (or use `screen`/`tmux`).

```
                    ┌─────────────────────────────────┐
                    │  CLIENT SENDS QUERY TO :8081    │
                    └──────────────────┬──────────────┘
                                       │
                 ┌─────────────────────┼─────────────────────┐
                 ▼                     ▼                     ▼
        ┌────────────────┐   ┌──────────────────┐   ┌──────────────────┐
        │ LLM :8080      │   │ Backend API :3001│   │ RAG Server :8081 │
        │ (Qwen 3B)      │   │ (NestJS/Node)    │   │ (Python/Flask)   │
        │ cheese-server  │   │ Fix-Go-BackEnd   │   │ Orchestrator     │
        └────────────────┘   └──────────────────┘   └──────────────────┘
```

---

### Terminal 1: Start LLM Server (Cheesebrain) on :8080

This runs the Qwen 2.5 3B model with native tool calling enabled.

**Step 1: Open Terminal 1**
```bash
cd ~/fixago_rag
```

**Step 2: Start cheese-server (choose your hardware)**

<details>
<summary>For <b>4GB RAM VPS</b> (2 CPU cores)</summary>

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
</details>

<details>
<summary>For <b>8GB+ RAM VPS</b> (4 CPU cores)</summary>

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
</details>

**Step 3: Wait for startup and verify**

```bash
# Watch the log in real-time (Ctrl+C to exit)
tail -f cheese.log

# You should see within 10-30 seconds:
# main: model loaded
# main: server is listening on http://0.0.0.0:8080
```

**Step 4: Test LLM is responding** (in a NEW terminal window)

```bash
# Test basic connectivity
curl -X GET http://localhost:8080/health

# Test LLM inference with a simple query
curl -X POST http://localhost:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-3.5-turbo",
    "messages": [{"role": "user", "content": "Hello"}],
    "temperature": 0.7
  }' | jq '.choices[0].message.content'
```

**⚠️ CRITICAL FLAGS — MUST ALL BE PRESENT:**

| Flag | Purpose | Impact if Missing |
|------|---------|-----------------|
| `ENABLE_NATIVE_TOOL_CALL=1` | Environment variable enabling tool calling | Tools won't be called; LLM just chats |
| `--chat-template qwen` | Uses Qwen's native function calling format | Wrong format used (Hermes 2 Pro); tools fail |
| `--n-predict 300` | Max output tokens (allows 2-3 tool calls) | Multi-question queries incomplete |
| `--ctx-size 4096` | Context window (4GB RAM) | OOM crash if too high |
| `--threads 2` | CPU threads (match your cores) | Slow inference if too low |
| `--flash-attn on` | GPU-like attention optimization | 50% slower without it |

**⚠️ VERIFICATION CHECKLIST:**

```bash
# Check cheese-server is running
ps aux | grep cheese-server | grep -v grep

# Check port 8080 is listening
netstat -tlnp | grep 8080

# Check log shows correct chat format
tail -20 cheese.log | grep "Chat format"
# Should show: "Chat format: Qwen" NOT "Hermes 2 Pro"
```

---

### Terminal 2: Start Backend API on :3001

The Backend API provides real service data (groups, services, prices, bookings).

```bash
cd ~/Fix-Go-BackEnd-API

# Start in production mode
npm run start:prod
```

**Expected output:**
```
[INFO] Application is running on: http://localhost:3001/api/v1
```

**Verify it's working:**
```bash
curl http://localhost:3001/api/v1/health
# Should return: {"status": "ok"}
```

---

### Terminal 3: Start RAG Server on :8081

The RAG Server is the main orchestrator that coordinates LLM, backend API, and vector DB.

```bash
cd ~/fixago_rag

# Activate Python virtual environment
source venv/bin/activate

# Start the Flask server
python server.py
```

**Expected output:**
```
Seeding complete.
Starting RAG server on port 8081...
Running on http://127.0.0.1:8081
```

**Verify it's working:**
```bash
curl -X POST http://localhost:8081/api/v1/rag/query \
  -H "Content-Type: application/json" \
  -d '{"query": "Fixago làm việc mấy giờ?", "history": []}'

# Should return within 1-2 seconds (deterministic response):
# {"status": "success", "response": "Dạ Fixago hoạt động 24/7..."}
```

---

### Final Verification: Test Full System

Once all 3 services are running, verify end-to-end:

```bash
# 1. Test LLM is serving
curl http://localhost:8080/health

# 2. Test Backend API is serving
curl http://localhost:3001/api/v1/health

# 3. Test RAG Server is serving
curl -X POST http://localhost:8081/api/v1/rag/query \
  -H "Content-Type: application/json" \
  -d '{"query": "Bạn có dịch vụ gì?", "history": []}'
```

**All three should respond successfully.** If any fails, see Troubleshooting section below.

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

### ❌ LLM Not Calling Tools (Always Returns "Dạ mình có thể hỗ trợ...")

**Symptom:** Response is always the generic booking message instead of calling tools.

**Root Cause:** One or both CRITICAL flags missing:
- `ENABLE_NATIVE_TOOL_CALL=1` not set as environment variable
- `--chat-template qwen` not passed to cheese-server

**Diagnostic Steps:**

1. **Check if cheese-server is running:**
```bash
ps aux | grep cheese-server | grep -v grep
# Should show the process; if not, start it
```

2. **Check the chat format in logs:**
```bash
tail -30 cheese.log | grep -i "chat format"
```

Should show:
```
srv  params_from_: Chat format: Qwen
```

If it shows "Hermes 2 Pro" or "unknown", the wrong format is being used.

3. **Check if ENABLE_NATIVE_TOOL_CALL was set:**
```bash
grep ENABLE_NATIVE_TOOL_CALL cheese.log
```

Should have a message confirming tool calling is enabled.

**Solution — Restart cheese-server with BOTH flags:**

```bash
# Kill the old process
pkill -f cheese-server
sleep 2

# Restart with BOTH required flags
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

# Wait for startup
sleep 5

# Verify format is correct
tail -20 cheese.log | grep "Chat format"
```

**Why both flags matter:**
- `ENABLE_NATIVE_TOOL_CALL=1` → Enables the `/v1/chat/completions` endpoint to accept `tools` parameter
- `--chat-template qwen` → Tells cheese-server to format function calls using Qwen's native format (NOT Hermes 2 Pro)

Without either flag, the LLM receives the tools parameter but doesn't know how to format responses as function calls.

---

### ❌ Multi-Question Queries Return Partial Responses

**Symptom:** Query like "Bạn có dịch vụ gì và giá bao nhiêu?" only returns services, not prices.

**Root Cause:** `--n-predict` too low to generate multiple tool calls and responses.

**How it works:**
- Each tool call needs ~100-150 tokens to encode/decode
- Multi-question queries (2-3 questions) need ~300-400 tokens total
- If `--n-predict 200`, output gets truncated

**Solution:**

```bash
# Check current n-predict value
grep "n-predict" cheese.log

# If you see 200 or lower, restart with higher value:
pkill -f cheese-server
sleep 2

# For multi-questions, use n-predict 350+
nohup env ENABLE_NATIVE_TOOL_CALL=1 \
./cheesebrain/build/bin/cheese-server \
  --model ./models/qwen2.5-3b-instruct-q4_k_m.gguf \
  --host 0.0.0.0 \
  --port 8080 \
  --ctx-size 4096 \
  --flash-attn on \
  --threads 2 \
  --n-predict 350 \
  --parallel 1 \
  --chat-template qwen \
  > cheese.log 2>&1 &
```

**Recommended values:**
- Single questions: `--n-predict 300`
- Multi-questions (2-3): `--n-predict 350-400`
- Complex scenarios: `--n-predict 500`

---

### ❌ "Connection refused" on Port 3001

**Symptom:** Error: `Connection refused on localhost:3001`

**Root Cause:** Backend API not running or failed to start.

**Diagnostic:**
```bash
# Check if process is running
ps aux | grep "Fix-Go-BackEnd" | grep -v grep

# Check if port 3001 is listening
netstat -tlnp | grep 3001
lsof -i :3001
```

**Solution:**

```bash
# Navigate to backend repo
cd ~/Fix-Go-BackEnd-API

# Start in production mode
npm run start:prod

# Should see:
# Application is running on: http://localhost:3001/api/v1
```

If it fails, check:
```bash
# Verify dependencies installed
npm list

# Rebuild if needed
npm install

# Check for port conflicts
lsof -i :3001
```

---

### ❌ "ImportError: pomaidb" or Vector DB Not Found

**Symptom:** Error when starting RAG server: `ImportError: cannot import name 'pomaidb'`

**Root Cause:** Vector database was not built during `./build.sh`, or build failed.

**Diagnostic:**
```bash
# Check if pomaidb binary exists
ls -la pomaidb/build/lib/libpomai_core.so

# Check build log
tail -50 pomaidb/build/CMakeFiles/CMakeOutput.log
```

**Solution:**

```bash
cd ~/fixago_rag

# Rebuild pomaidb
make clean
make pomaidb

# Or rebuild everything
./build.sh

# Verify
test -f ./pomaidb/build/lib/libpomai_core.so && echo "✓ OK" || echo "✗ FAILED"
```

---

### ❌ "Model not found" or FileNotFoundError

**Symptom:** Error: `./models/qwen2.5-3b-instruct-q4_k_m.gguf: No such file or directory`

**Root Cause:** Model GGUF file was not downloaded.

**Diagnostic:**
```bash
# Check what's in models directory
ls -lh ./models/

# Verify file size is ~4-5GB
du -h ./models/qwen*.gguf
```

**Solution:**

```bash
# Download the model (4.5GB download)
mkdir -p ./models

huggingface-cli download Qwen/Qwen2.5-3B-Instruct-GGUF \
  qwen2.5-3b-instruct-q4_k_m.gguf \
  --local-dir ./models

# Verify
ls -lh ./models/qwen2.5-3b-instruct-q4_k_m.gguf
# Should show: 4.5G or similar
```

If download is slow:
```bash
# Download with more workers
huggingface-cli download Qwen/Qwen2.5-3B-Instruct-GGUF \
  qwen2.5-3b-instruct-q4_k_m.gguf \
  --local-dir ./models \
  --resume-download
```

---

### ❌ Out of Memory (OOM) or "Cannot allocate memory"

**Symptom:** Cheese-server crashes with `Cannot allocate memory` or system becomes unresponsive.

**Root Cause:** Model + inference + context window exceeds available RAM.

**Quick checks:**
```bash
# Check free memory
free -h

# Check if cheese-server is using too much
ps aux | grep cheese-server | awk '{print $6}'  # RSS in KB
```

**Solution for 4GB RAM VPS:**

```bash
# Ensure using Q4_K_M quantization (4.5GB), not Q5 (7GB)
ls -lh ./models/
# If using wrong quantization, re-download:
rm ./models/qwen*.gguf
huggingface-cli download Qwen/Qwen2.5-3B-Instruct-GGUF \
  qwen2.5-3b-instruct-q4_k_m.gguf \
  --local-dir ./models

# Reduce context size and threads
pkill -f cheese-server
sleep 2

nohup env ENABLE_NATIVE_TOOL_CALL=1 \
./cheesebrain/build/bin/cheese-server \
  --model ./models/qwen2.5-3b-instruct-q4_k_m.gguf \
  --host 0.0.0.0 \
  --port 8080 \
  --ctx-size 2048 \
  --flash-attn on \
  --threads 1 \
  --n-predict 256 \
  --parallel 1 \
  --chat-template qwen \
  > cheese.log 2>&1 &
```

**Increase system swap (temporary relief):**
```bash
# Create 4GB swap file
sudo fallocate -l 4G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile

# Make permanent (add to /etc/fstab):
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

**Permanent solution:** Upgrade VPS to 8GB+ RAM.

---

### ❌ "ModuleNotFoundError: No module named 'dotenv'"

**Symptom:** RAG server fails to start with missing module error.

**Root Cause:** Python venv not properly activated or dependencies not installed.

**Solution:**

```bash
cd ~/fixago_rag

# Activate virtual environment
source venv/bin/activate

# Verify it's activated (prompt should show `(venv)`)

# Install/reinstall dependencies
pip install python-dotenv flask requests sentence-transformers

# Try starting server again
python server.py
```

---

### ❌ Slow Inference (10+ seconds per query)

**Symptom:** LLM responses take 30+ seconds instead of 12-20 seconds.

**Causes and solutions:**

1. **Flash attention disabled:**
```bash
# Check logs
grep "flash.attn" cheese.log

# Restart with --flash-attn on
pkill -f cheese-server
# ... restart with --flash-attn on ...
```

2. **Too many threads (context thrashing):**
```bash
# If using --threads 4+ with only 2 CPU cores, reduce:
pkill -f cheese-server
# Restart with --threads 2
```

3. **Context size too high:**
```bash
# For 4GB RAM, use --ctx-size 4096, not 8192
pkill -f cheese-server
# Restart with --ctx-size 4096
```

4. **Other processes consuming CPU/RAM:**
```bash
# Check what's running
top -b -n 1 | head -15
free -h
```

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
