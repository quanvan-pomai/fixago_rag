import requests
import time

URL = "http://127.0.0.1:8081/api/v1/rag/query"
history = []

def chat(query):
    print(f"\n[USER]: {query}")
    payload = {
        "query": query,
        "history": history,
        "use_cache": False
    }
    
    start = time.time()
    resp = requests.post(URL, json=payload)
    end = time.time()
    
    if resp.status_code == 200:
        data = resp.json()
        ai_resp = data.get("response", "")
        print(f"[AI] (took {end-start:.2f}s): {ai_resp}")
        
        history.append({"role": "user", "content": query})
        history.append({"role": "assistant", "content": ai_resp})
    else:
        print(f"[ERROR]: {resp.status_code} - {resp.text}")

print("=== BẮT ĐẦU TEST LUỒNG BOOKING TỰ ĐỘNG ===")
chat("Nhà tôi bị chập điện, đặt lịch thợ tới sửa giúp tôi")
chat("Tôi tên Toàn, sđt 0987654321, nhà ở 123 Lê Lợi")
chat("Xác nhận tạo đơn đi bạn")
