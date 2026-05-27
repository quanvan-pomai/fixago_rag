# Fixago RAG — Agentic Customer Service Engine

An agentic AI-powered customer service system for **Fixago**, a home repair booking platform. The system combines a local LLM inference engine, a custom vector database (RAG), a prompt cache layer, and a NestJS backend API to create a fully autonomous booking agent.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        CLIENT (Browser / Script)                │
└──────────────────────────────┬──────────────────────────────────┘
                               │ HTTP POST /api/v1/rag/query
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│              RAG Server  (Python / Flask)  :8081                 │
│                                                                  │
│  1. Prompt Injection Filter                                      │
│  2. PomaiDB  — Vector retrieval (RAG context)                    │
│  3. PomaiCache — KV + prompt-prefix cache                        │
│  4. Cheesebrain — Local LLM inference  ──────────────────────┐  │
│  5. Tool Dispatcher (get_groups / get_services / booking)    │  │
└──────────────────────────────┬───────────────────────────────┘  │
                               │                                   │
               ┌───────────────┴────────────────────┐             │
               ▼                                    ▼             │
┌──────────────────────────┐   ┌──────────────────────────────┐   │
│  Fix-Go Backend API      │   │  Cheesebrain LLM Server      │◄──┘
│  (NestJS)  :3001         │   │  (cheese-server)  :8080      │
│  /services/groups        │   │  Qwen 2.5 GGUF model         │
│  /services               │   │  OpenAI-compatible API       │
│  /bookings               │   └──────────────────────────────┘
└──────────────────────────┘
```

**Components:**

| Component | What it does |
|---|---|
| `cheesebrain` | C++ LLM inference server (fork of llama.cpp), serves OpenAI-compatible `/v1/chat/completions` |
| `pomaidb` | C++ vector database used for RAG — stores and retrieves semantic context chunks |
| `pomaicache` | C++ KV + prompt-prefix cache to avoid redundant LLM calls |
| `cheesepath` | Go utility library |
| `server.py` | Main Flask RAG server — orchestrates the full agentic pipeline |
| `rag_engine.py` | Python wrapper around PomaiDB and PomaiCache |
| Fix-Go Backend API | NestJS REST API for service listings and booking creation |

---

## Requirements

### System

| Requirement | Minimum | Recommended |
|---|---|---|
| OS | Ubuntu 20.04 / Debian 11 | Ubuntu 22.04+ |
| CPU | x86_64, 4 cores | 8+ cores |
| RAM | 6 GB | 16 GB |
| Disk | 10 GB free | 20 GB |

### Software Dependencies

Install the following before anything else:

```bash
# Build tools
sudo apt update
sudo apt install -y git cmake build-essential python3 python3-pip python3-venv curl

# Go (required for cheesepath)
sudo apt install -y golang-go
# OR install latest Go manually:
# https://go.dev/doc/install

# Node.js v18+ (required for Fix-Go Backend API)
curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash -
sudo apt install -y nodejs

# MySQL 8.0 (required for Fix-Go Backend API)
sudo apt install -y mysql-server
```

Verify versions:

```bash
cmake --version   # Need 3.14+
python3 --version # Need 3.9+
go version        # Need 1.20+
node --version    # Need 18+
mysql --version   # Need 8.0+
```

### Model File

You need a **GGUF** model file placed in the `models/` directory. Recommended models (pick one):

| Model | Size | Speed | Quality |
|---|---|---|---|
| `qwen2.5-3b-instruct-q4_k_m.gguf` | ~2 GB | Fast (CPU) | Good |
| `qwen2.5-7b-instruct-q4_k_m.gguf` | ~4.5 GB | Slow (CPU) | Better |

**Download from Hugging Face:**

```bash
# 3B model (recommended for CPU)
huggingface-cli download Qwen/Qwen2.5-3B-Instruct-GGUF \
  qwen2.5-3b-instruct-q4_k_m.gguf \
  --local-dir ./models

# 7B model (split into 2 parts — must merge after download)
huggingface-cli download Qwen/Qwen2.5-7B-Instruct-GGUF \
  qwen2.5-7b-instruct-q4_k_m-00001-of-00002.gguf \
  qwen2.5-7b-instruct-q4_k_m-00002-of-00002.gguf \
  --local-dir ./models
```

> If you downloaded the 7B model in 2 parts, merge them after the build step — see [Merging Split GGUF](#merging-split-gguf-files) below.

---

## First-Time Setup

### Step 1 — Clone the Repository

```bash
git clone https://github.com/quanvan-pomai/fixago_rag.git
cd fixago_rag
```

### Step 2 — Build All C++ and Go Components

Run the one-shot build script. This will initialize submodules, compile everything, and set up the Python virtual environment:

```bash
chmod +x build.sh
./build.sh
```

What it does internally:
1. `git submodule update --init --recursive` — pulls `cheesebrain`, `pomaidb`, `pomaicache`, `cheesepath`
2. `make cheesebrain` — compiles the LLM inference server
3. `make pomaidb` — compiles the vector database
4. `make pomaicache` — compiles the prompt cache
5. `make cheesepath` — compiles the Go utility
6. Creates `venv/` and installs Python dependencies

> ⏱️ First build takes **5–15 minutes** depending on your CPU. Subsequent builds are incremental.

If the script fails, you can build each component individually:

```bash
make cheesebrain   # Build LLM server only
make pomaidb       # Build vector DB only
make pomaicache    # Build cache only
make cheesepath    # Build Go lib only
make status        # Check submodule status
```

### Optional — Optimized Cheesebrain CPU Build

For CPU-only VPS deployments, rebuild `cheese-server` in Release mode with native CPU optimization. This can improve token generation speed on weak CPUs.

Run this on the same machine that will run `cheese-server`:

```bash
cmake -S cheesebrain -B cheesebrain/build \
  -DCMAKE_BUILD_TYPE=Release \
  -DGGML_NATIVE=ON \
  -DGGML_OPENMP=ON \
  -DCHEESE_BUILD_TESTS=OFF \
  -DCHEESE_BUILD_EXAMPLES=OFF \
  -DCHEESE_BUILD_TOOLS=ON \
  -DCHEESE_BUILD_SERVER=ON

cmake --build cheesebrain/build --target cheese-server -j2
```

The configure output should include something like:

```text
Adding CPU backend variant ggml-cpu: -march=native
```

Do not build with `GGML_NATIVE=ON` on one machine and copy the binary to a different VPS unless the CPUs are compatible. For best results, build directly on the VPS.

### Step 3 — Configure Environment

Copy the example env file and edit it:

```bash
cp .env.example .env
```

Default values work out of the box for local development:

```env
RAG_PORT=8081
BACKEND_API_URL=http://127.0.0.1:3001/api/v1
LLM_API_URL=http://127.0.0.1:8080/v1/chat/completions
```

### Step 4 — Set Up the Fix-Go Backend API

```bash
cd ../Fix-Go-BackEnd-API   # or wherever your backend is located

# Copy and configure the backend .env
cp .env.example .env
# Edit .env — set DATABASE_URL, DB credentials, JWT_SECRET, PORT=3001

# Set up the MySQL database
mysql -u root -p -e "CREATE DATABASE fixngo_db; CREATE USER 'fixago_user'@'localhost' IDENTIFIED BY 'your_password'; GRANT ALL ON fixngo_db.* TO 'fixago_user'@'localhost';"

# Install dependencies and run database migrations
npm install
npx prisma migrate deploy
npx prisma db seed   # optional: seeds initial service data

# Start the backend
npm run start:prod
```

The backend will be available at `http://localhost:3001/api/v1`.  
Swagger docs: `http://localhost:3001/api/docs`

---

## Running the System

You need **3 terminals** running simultaneously.

### Terminal 1 — LLM Inference Server (Cheesebrain)

Recommended low-resource config for a **4 GB RAM / 2 CPU core** machine:

```bash
cd fixago_rag

CHEESE_SQUEEZE_AGGRESSIVENESS=0 \
./cheesebrain/build/bin/cheese-server \
  --model ./models/qwen2.5-1.5b-instruct-q8_0.gguf \
  --host 0.0.0.0 \
  --port 8080 \
  --ctx-size 512 \
  --n-predict 128 \
  --threads 2 \
  --parallel 1 \
  --no-cache-prompt \
  --cache-ram 0
```

Wait until you see:
```
main: model loaded
main: server is listening on http://0.0.0.0:8080
```

**Key flags:**

| Flag | Description |
|---|---|
| `--model` | Path to your GGUF model file |
| `--threads 2` | Match the available CPU cores. Avoid setting this higher on a 2-core machine. |
| `--ctx-size 512` | Small context window to keep RAM and prompt processing low. |
| `--n-predict 128` | Shorter replies; smoother on weak CPUs than `256` or `512`. |
| `--parallel 1` | One inference slot. More slots increase memory use. |
| `--no-cache-prompt` | Disables Cheesebrain prompt/KV prompt reuse for predictable low-memory behavior. |
| `--cache-ram 0` | Disables Cheesebrain host prompt cache memory. |
| `CHEESE_SQUEEZE_AGGRESSIVENESS=0` | Disables ContextSqueezer. With `--ctx-size 512`, keep prompts short instead of compressing them. |

Notes for this project:

- Keep the API `session_id`; it preserves booking state and makes multi-turn booking smarter.
- Response cache in `server.py` is disabled by default. Send `"use_cache": true` only when intentionally testing repeated identical prompts.
- If responses feel too short, increase `--n-predict` to `192` or `256`. If the machine becomes slow, return to `128`.
- If you have more RAM/CPU, use a Q4/Q5 3B model and raise `--ctx-size` gradually, for example `1024`, then `2048`.

### Terminal 2 — Fix-Go Backend API

```bash
cd Fix-Go-BackEnd-API
npm run start:prod
```

Wait until you see:
```
Application is running on: http://localhost:3001/api/v1
```

### Terminal 3 — RAG Server

```bash
cd fixago_rag
source venv/bin/activate
python server.py
```

Wait until you see:
```
Seeding complete.
Starting RAG server on port 8081...
Running on http://127.0.0.1:8081
```

### Verify Everything is Running

```bash
# LLM server health
curl http://127.0.0.1:8080/health

# Backend health
curl http://127.0.0.1:3001/api/v1/health

# RAG server — quick retrieve test
curl -s http://127.0.0.1:8081/api/v1/rag/retrieve \
  -X POST -H "Content-Type: application/json" \
  -d '{"query": "sửa điện"}'
```

All three should return `{"status": "ok"}` or a valid JSON response.

---

## Merging Split GGUF Files

If you downloaded a model in multiple parts (e.g., the 7B model in 2 files), merge them using the built-in tool:

```bash
./cheesebrain/build/bin/cheese-gguf-split --merge \
  ./models/qwen2.5-7b-instruct-q4_k_m-00001-of-00002.gguf \
  ./models/qwen2.5-7b-instruct-q4_k_m.gguf
```

The second argument is the **output path** (merged file). The tool automatically finds the other parts in the same directory.

After merging, you can delete the split files to free disk space:

```bash
rm ./models/*-of-0000*.gguf
```

---

## API Reference

The RAG Server exposes these endpoints on port `8081`:

### `POST /api/v1/rag/query` — Main Chat Endpoint

Send a user message and conversation history. The agent will automatically call backend tools, retrieve RAG context, and return a response.

```bash
curl -X POST http://127.0.0.1:8081/api/v1/rag/query \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Fixago có dịch vụ gì?",
    "history": [],
    "use_cache": false
  }'
```

**Request body:**

| Field | Type | Description |
|---|---|---|
| `query` | string | The user's message |
| `history` | array | Previous turns: `[{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]` |
| `use_cache` | boolean | Whether to use prompt cache (default: `true`) |
| `system_prompt` | string | Override the default system prompt (optional) |

**Response:**

```json
{
  "status": "success",
  "response": "Fixago cung cấp các dịch vụ: điện, nước, điện lạnh...",
  "source": "llm",
  "tool_calls": ["Thực thi Tool: get_groups()"],
  "cache_metrics": { "hit": false }
}
```

### `POST /api/v1/rag/ingest` — Add Documents to RAG

```bash
curl -X POST http://127.0.0.1:8081/api/v1/rag/ingest \
  -H "Content-Type: application/json" \
  -d '{"doc_id": 2001, "text": "Fixago hoạt động từ 7h sáng đến 10h tối."}'
```

### `POST /api/v1/rag/retrieve` — Retrieve RAG Context Only

```bash
curl -X POST http://127.0.0.1:8081/api/v1/rag/retrieve \
  -H "Content-Type: application/json" \
  -d '{"query": "sửa điều hòa", "top_k": 3}'
```

---

## Running Tests

The test suite covers 15 real-world scenarios including the booking flow, service queries, adversarial prompts, and prompt injection attacks.

```bash
cd fixago_rag
source venv/bin/activate

# Quick booking flow test (3 turns)
python test_booking.py

# Direct LLM test (no RAG, no backend)
python test_llm.py

# Full test suite — 15 scenarios
python test_full_scenarios.py
```

> ⚠️ Make sure all 3 services (LLM server, Backend API, RAG server) are running before executing tests.

**Scenario coverage:**

| # | Scenario | Tests |
|---|---|---|
| 1 | Standard booking flow | Multi-turn, info collection, confirmation |
| 2 | Service group query | `get_groups` tool call |
| 3–5 | Service price query | `get_services` with keywords: điện, nước, lạnh |
| 6 | One-shot booking | All info provided in first message |
| 7 | Customer changes mind | State consistency across topic switches |
| 8 | Multiple faults at once | Complex service description |
| 9 | Cross-sell after booking | Context continuity |
| 10 | Invalid phone number | Model validation behavior |
| 11 | Prompt injection | Safety filter blocks 4 attack patterns |
| 12–15 | General knowledge, vague input, working hours, soft refusal | Edge cases |

---

## Project Structure

```
fixago_rag/
├── cheesebrain/          # LLM inference engine (C++ submodule)
│   └── build/bin/
│       ├── cheese-server       # LLM inference server binary
│       └── cheese-gguf-split   # GGUF split/merge tool
├── pomaidb/              # Vector database (C++ submodule)
├── pomaicache/           # Prompt cache (C++ submodule)
├── cheesepath/           # Go utility (submodule)
├── models/               # GGUF model files (not committed to git)
├── data/                 # Runtime data: PomaiDB vectors, cache files
├── venv/                 # Python virtual environment
├── server.py             # Main RAG + agentic server
├── rag_engine.py         # PomaiDB + PomaiCache Python bindings
├── demo.html             # Web chat demo UI
├── test_booking.py       # Basic booking flow test
├── test_llm.py           # Direct LLM API test
├── test_full_scenarios.py # Full 15-scenario test suite
├── build.sh              # One-shot build script
├── Makefile              # Individual component build targets
└── .env                  # Local environment config (not committed)
```

---

## Troubleshooting

**`cheese-server` not found**
→ Run `make cheesebrain` or `./build.sh` first.

**`import pomaidb` fails**
→ Run `make pomaidb` to compile the C++ library. The `.so` file must exist at `pomaidb/build/libpomai_c.so`.

**LLM response takes too long (>2 min)**
→ Use a smaller model (`3B` instead of `7B`), or increase `--threads` to match your CPU core count.

**`ECONNREFUSED` on port 3001**
→ The Fix-Go Backend API is not running. Start it with `npm run start:prod` in the backend directory.

**`[BLOCKED]` response from RAG server**
→ Your query contains a keyword flagged by the prompt injection filter (e.g., "bỏ qua", "ignore", "system prompt"). This is expected behavior.

**Disk full error during GGUF merge**
→ You need at least **N + N/2 GB** free (N = model size). Free up space before merging.
