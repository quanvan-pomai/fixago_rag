#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════════════
# Restart All Services: LLM + Backend API + RAG Server
# ═══════════════════════════════════════════════════════════════════════════════

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$SCRIPT_DIR"

echo "═══════════════════════════════════════════════════════════════════════════════"
echo "🔄 RESTARTING ALL FIXAGO SERVICES"
echo "═══════════════════════════════════════════════════════════════════════════════"

# ─────────────────────────────────────────────────────────────────────────────────
# 1. Kill existing processes
# ─────────────────────────────────────────────────────────────────────────────────
echo ""
echo "🛑 Step 1: Killing existing processes..."

pkill -f "python server" || true
pkill -f "cheese-server" || true
pkill -f "npm.*start" || true

sleep 2
echo "✅ All processes terminated"

# ─────────────────────────────────────────────────────────────────────────────────
# 2. Start LLM Server (Cheesebrain)
# ─────────────────────────────────────────────────────────────────────────────────
echo ""
echo "🚀 Step 2: Starting LLM Server (Cheesebrain on :8080)..."

nohup env ENABLE_NATIVE_TOOL_CALL=1 \
  ./cheesebrain/build/bin/cheese-server \
  --model ./models/qwen2.5-3b-instruct-q5_0.gguf \
  --host 0.0.0.0 \
  --port 8080 \
  --ctx-size 4096 \
  --flash-attn on \
  --threads 4 \
  --n-predict 300 \
  --parallel 1 \
  --chat-template qwen \
  > cheese.log 2>&1 &

echo "⏳ Waiting for LLM server to start..."
sleep 5

# Check if LLM server is responding
for i in {1..10}; do
  if curl -s http://localhost:8080/health > /dev/null 2>&1; then
    echo "✅ LLM Server ready"
    break
  fi
  if [ $i -eq 10 ]; then
    echo "❌ LLM Server failed to start"
    tail -20 cheese.log
    exit 1
  fi
  echo "  Attempt $i/10..."
  sleep 2
done

# ─────────────────────────────────────────────────────────────────────────────────
# 3. Start Backend API (Fix-Go-BackEnd-API)
# ─────────────────────────────────────────────────────────────────────────────────
echo ""
echo "🚀 Step 3: Starting Backend API (on :3001)..."

if [ -d "../Fix-Go-BackEnd-API" ]; then
  cd ../Fix-Go-BackEnd-API
  npm run start:prod > backend.log 2>&1 &
  cd "$SCRIPT_DIR"

  echo "⏳ Waiting for Backend API to start..."
  sleep 5

  for i in {1..10}; do
    if curl -s http://localhost:3001/api/v1/health > /dev/null 2>&1; then
      echo "✅ Backend API ready"
      break
    fi
    if [ $i -eq 10 ]; then
      echo "⚠️  Backend API may not be ready, continuing anyway..."
      break
    fi
    echo "  Attempt $i/10..."
    sleep 2
  done
else
  echo "⚠️  Backend API directory not found, skipping..."
fi

# ─────────────────────────────────────────────────────────────────────────────────
# 4. Start RAG Server
# ─────────────────────────────────────────────────────────────────────────────────
echo ""
echo "🚀 Step 4: Starting RAG Server (on :8081)..."

source venv/bin/activate
python server.py > rag.log 2>&1 &

echo "⏳ Waiting for RAG server to start..."
sleep 8

# Check if RAG server is responding
for i in {1..10}; do
  if curl -s http://localhost:8081/api/v1/rag/query > /dev/null 2>&1; then
    echo "✅ RAG Server ready"
    break
  fi
  if [ $i -eq 10 ]; then
    echo "⚠️  RAG Server may not be ready yet (still initializing)..."
    break
  fi
  echo "  Attempt $i/10..."
  sleep 2
done

# ─────────────────────────────────────────────────────────────────────────────────
# 5. Verify all services
# ─────────────────────────────────────────────────────────────────────────────────
echo ""
echo "═══════════════════════════════════════════════════════════════════════════════"
echo "✅ ALL SERVICES STARTED"
echo "═══════════════════════════════════════════════════════════════════════════════"
echo ""
echo "Service Status:"
echo "  🟢 LLM Server (Cheesebrain)  :8080  $(curl -s http://localhost:8080/health > /dev/null && echo '✅' || echo '⚠️')"
echo "  🟢 Backend API              :3001  $(curl -s http://localhost:3001/api/v1/health > /dev/null && echo '✅' || echo '⚠️')"
echo "  🟢 RAG Server               :8081  $(curl -s http://localhost:8081/health > /dev/null && echo '✅' || echo '⚠️')"
echo ""
echo "Logs:"
echo "  - LLM:     tail -f cheese.log"
echo "  - RAG:     tail -f rag.log"
echo "  - Backend: cd ../Fix-Go-BackEnd-API && tail -f backend.log"
echo ""
echo "Test System:"
echo "  curl -X POST http://127.0.0.1:8081/api/v1/rag/query \\"
echo "    -H 'Content-Type: application/json' \\"
echo "    -d '{\"query\": \"Máy lạnh bao nhiêu tiền?\", \"history\": []}'"
echo ""
echo "═══════════════════════════════════════════════════════════════════════════════"
