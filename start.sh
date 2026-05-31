#!/bin/bash
set -e
cd "$(dirname "$0")"

echo "======================================"
echo "  Fixago RAG — Start All Services     "
echo "======================================"

# --- 1. Cheese-server (LLM engine) ---
echo ""
echo "[1/2] Starting cheese-server (LLM engine)..."

MODEL=${MODEL:-./models/qwen2.5-3b-instruct-q5_0.gguf}
LLM_PORT=${LLM_PORT:-8080}

if ! [ -f "$MODEL" ]; then
  echo "ERROR: Model file not found: $MODEL"
  exit 1
fi

nohup ./cheesebrain/build/bin/cheese-server \
  --model "$MODEL" \
  --host 0.0.0.0 --port "$LLM_PORT" \
  --ctx-size 8192 --flash-attn on \
  --threads 8 --n-predict 400 --parallel 2 \
  --chat-template qwen \
  > cheese.log 2>&1 &

CHEESE_PID=$!
echo "  cheese-server PID: $CHEESE_PID"
echo "  Waiting 6s for LLM to warm up..."
sleep 6

# Verify cheese-server started
if ! kill -0 $CHEESE_PID 2>/dev/null; then
  echo "ERROR: cheese-server failed to start. Check cheese.log"
  exit 1
fi
echo "  LLM engine ready ✓"

# --- 2. RAG Server ---
echo ""
echo "[2/2] Starting RAG server (Python/Flask)..."

source venv/bin/activate
export ENABLE_NATIVE_TOOL_CALL=1

nohup python server.py > rag.log 2>&1 &
RAG_PID=$!
echo "  RAG server PID: $RAG_PID"
sleep 3

# Verify RAG server started
if ! kill -0 $RAG_PID 2>/dev/null; then
  echo "ERROR: RAG server failed to start. Check rag.log"
  exit 1
fi

echo ""
echo "======================================"
echo "  ✅ All services running!"
echo "======================================"
echo "  Swagger UI:  http://127.0.0.1:8081/docs"
echo "  Health:      http://127.0.0.1:8081/api/v1/health"
echo ""
echo "  Logs:"
echo "    LLM:  tail -f cheese.log"
echo "    RAG:  tail -f rag.log"
echo ""
echo "  To stop:  pkill -f cheese-server; pkill -f 'python server.py'"
echo "======================================"
