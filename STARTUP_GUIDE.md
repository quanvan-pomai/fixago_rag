# 🚀 Fixago RAG — Hướng Dẫn Khởi Động Đầy Đủ

## Cấu trúc hệ thống

```
┌───────────────────────────────────────────────────────────────┐
│  Port 8081   │  RAG Server (Python/Flask)  │  server.py       │
├───────────────────────────────────────────────────────────────┤
│  Port 8080   │  LLM Engine (cheese-server) │  Qwen 2.5 3B     │
├───────────────────────────────────────────────────────────────┤
│  Port 3001   │  Backend API (NestJS)       │  (external)      │
└───────────────────────────────────────────────────────────────┘
```

---

## Bước 0: Lần đầu cài đặt (chỉ chạy 1 lần)

```bash
cd ~/pomaieco/fixago_rag
./build.sh
```

Script này sẽ tự động:
- Build `cheesebrain` (LLM runtime)
- Build `pomaidb` (vector DB)
- Build `pomaicache` (cache layer)
- Tạo Python virtualenv và cài thư viện

---

## Bước 1: Khởi động LLM Engine (cheese-server)

Chạy trong **Terminal 1** (hoặc background):

```bash
cd ~/pomaieco/fixago_rag

nohup ./cheesebrain/build/bin/cheese-server \
  --model ./models/qwen2.5-3b-instruct-q5_0.gguf \
  --host 0.0.0.0 \
  --port 8080 \
  --ctx-size 8192 \
  --flash-attn on \
  --threads 8 \
  --n-predict 400 \
  --parallel 2 \
  --chat-template qwen \
  > cheese.log 2>&1 &

echo "cheese-server PID: $!"
```

Kiểm tra server đã sẵn sàng:

```bash
curl http://127.0.0.1:8080/health
# Hoặc đọc log
tail -f cheese.log
```

> ⚠️ **Quan trọng:** Phải dùng `--chat-template qwen`. Thiếu flag này sẽ gây lỗi tool-calling.

---

## Bước 2: Cấu hình môi trường (`.env`)

Tạo file `.env` từ template (nếu chưa có):

```bash
cp .env.example .env
```

Nội dung `.env` chuẩn:

```env
RAG_PORT=8081
BACKEND_API_URL=http://127.0.0.1:3001/api/v1
LLM_API_URL=http://127.0.0.1:8080/v1/chat/completions
```

---

## Bước 3: Khởi động RAG Server

Chạy trong **Terminal 2**:

```bash
cd ~/pomaieco/fixago_rag

# Kích hoạt virtualenv
source venv/bin/activate

# BẮT BUỘC: Bật Native Tool Call
export ENABLE_NATIVE_TOOL_CALL=1

# Khởi động server
python server.py
```

Kết quả log bình thường:

```
[SERVER INIT] ENABLE_NATIVE_TOOL_CALL=True
 * Running on http://0.0.0.0:8081
```

### Chạy background (production):

```bash
source venv/bin/activate
export ENABLE_NATIVE_TOOL_CALL=1
nohup python server.py > rag.log 2>&1 &
echo "RAG Server PID: $!"
```

---

## Bước 4: Kiểm tra hệ thống

```bash
# Health check
curl http://127.0.0.1:8081/api/v1/health

# Test chat đơn giản
curl -X POST http://127.0.0.1:8081/api/v1/rag/query \
  -H "Content-Type: application/json" \
  -d '{"query": "sửa ống nước bao nhiêu?", "session_id": "test-001"}'
```

### Swagger UI (Recommended):

Mở trình duyệt → `http://127.0.0.1:8081/docs`

---

## Dừng tất cả dịch vụ

```bash
# Dừng RAG server
pkill -f "python server.py"

# Dừng cheese-server
pkill -f "cheese-server"
```

---

## Script tiện lợi — Khởi động 1 lệnh

Tạo file `start.sh`:

```bash
#!/bin/bash
set -e
cd "$(dirname "$0")"

echo "[1/2] Starting cheese-server (LLM)..."
nohup ./cheesebrain/build/bin/cheese-server \
  --model ./models/qwen2.5-3b-instruct-q5_0.gguf \
  --host 0.0.0.0 --port 8080 \
  --ctx-size 8192 --flash-attn on \
  --threads 8 --n-predict 400 --parallel 2 \
  --chat-template qwen \
  > cheese.log 2>&1 &

echo "  cheese-server PID: $!"
echo "  Waiting 5s for LLM to warm up..."
sleep 5

echo "[2/2] Starting RAG server..."
source venv/bin/activate
export ENABLE_NATIVE_TOOL_CALL=1
nohup python server.py > rag.log 2>&1 &
echo "  RAG server PID: $!"

echo ""
echo "✅ All services started!"
echo "   Swagger UI: http://127.0.0.1:8081/docs"
echo "   Health:     http://127.0.0.1:8081/api/v1/health"
echo "   LLM Log:    tail -f cheese.log"
echo "   RAG Log:    tail -f rag.log"
```

```bash
chmod +x start.sh
./start.sh
```

---

## Biến môi trường quan trọng

| Biến | Mặc định | Mô tả |
|------|----------|-------|
| `ENABLE_NATIVE_TOOL_CALL` | `0` | **Phải set = 1** để bật tool calling |
| `RAG_PORT` | `8081` | Port của RAG server |
| `BACKEND_API_URL` | `http://127.0.0.1:3001/api/v1` | URL NestJS backend |
| `LLM_API_URL` | `http://127.0.0.1:8080/v1/chat/completions` | URL LLM engine |
| `FIXAGO_DEBUG` | (unset) | Set = 1 để bật debug endpoints |
