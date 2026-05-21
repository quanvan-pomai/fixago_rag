#!/usr/bin/env python3
import os
import hashlib
import requests
from flask import Flask, request, jsonify

# Import the clean RAG engine components
import rag_engine

app = Flask(__name__)

@app.route("/api/v1/rag/ingest", methods=["POST"])
def ingest():
    data = request.json or {}
    doc_id = data.get("doc_id")
    text = data.get("text")
    if doc_id is None or not text:
        return jsonify({"status": "error", "message": "Missing 'doc_id' or 'text'"}), 400
    
    try:
        rag_engine.ingest_document(int(doc_id), text)
        return jsonify({"status": "success", "message": f"Document {doc_id} ingested successfully"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/v1/rag/retrieve", methods=["POST"])
def retrieve():
    data = request.json or {}
    query = data.get("query")
    top_k = data.get("top_k", 5)
    if not query:
        return jsonify({"status": "error", "message": "Missing 'query'"}), 400
    
    try:
        norm_query = rag_engine.normalize_query(query)
        context = rag_engine.retrieve_context(norm_query, top_k=int(top_k))
        return jsonify({"status": "success", "context": context})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/v1/rag/query", methods=["POST"])
def query_rag():
    data = request.json or {}
    query = data.get("query")
    system_prompt = data.get(
        "system_prompt",
        "Bạn là trợ lý ảo hỗ trợ tìm kiếm thông tin của Fixago. Bạn chỉ được phép trả lời dựa trên ngữ cảnh (Context) được cung cấp. Tuyệt đối không tự suy diễn, không tự thêm thắt hay bắt chước (mimic) các thông tin không có trong ngữ cảnh. Nếu câu hỏi không thể trả lời được bằng ngữ cảnh đã cho, hãy trả lời chính xác là: 'Xin lỗi, tôi không tìm thấy thông tin này trong tài liệu hướng dẫn.'"
    )
    use_cache = data.get("use_cache", True)
    
    if not query:
        return jsonify({"status": "error", "message": "Missing 'query'"}), 400
    
    # 1. Retrieve Context from PomaiDB
    try:
        norm_query = rag_engine.normalize_query(query)
        context = rag_engine.retrieve_context(norm_query, top_k=3)
    except Exception as e:
        print(f"RAG retrieval failed: {e}")
        context = ""
        
    # 2. Build final prompt template
    prompt = f"System: {system_prompt}\nContext: {context}\nQuestion: {query}"
    
    # 3. Tokenize Prompt
    tokens = rag_engine.tokenize_text(prompt)
    
    # 4. Prompt Cache lookup using PomaiCache
    prompt_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    cache_key = f"pomai_cache:response:{prompt_hash}"
    
    if use_cache:
        try:
            cached_val = rag_engine.cache.get(cache_key)
            if cached_val:
                p_get_res = rag_engine.cache.prompt_get(tokens)
                return jsonify({
                    "status": "success",
                    "response": cached_val.decode("utf-8"),
                    "source": "cache",
                    "cache_metrics": p_get_res
                })
        except Exception as e:
            print(f"Cache lookup failed: {e}")
            
    # 5. Call Cheesebrain LLM
    try:
        llm_response = requests.post(
            "http://127.0.0.1:8080/v1/chat/completions",
            json={
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Chỉ dựa vào ngữ cảnh sau đây để trả lời câu hỏi, không suy diễn hay bắt chước gì thêm:\nNgữ cảnh: {context}\n\nCâu hỏi: {query}"}
                ],
                "temperature": 0.0
            },
            timeout=120
        )
        if llm_response.status_code != 200:
            return jsonify({"status": "error", "message": f"LLM server returned status {llm_response.status_code}"}), 500
        
        result_json = llm_response.json()
        answer = result_json["choices"][0]["message"]["content"]
        
        # 6. Cache the result in PomaiCache
        if use_cache:
            try:
                # Cache full response in KV store (10 minutes)
                rag_engine.cache.set(cache_key, answer.encode("utf-8"), ttl_ms=600000)
                # Cache prompt prefix tokens in AI artifact cache layer (10 minutes)
                rag_engine.cache.prompt_put(tokens, answer.encode("utf-8"), ttl_ms=600000)
            except Exception as e:
                print(f"Cache write failed: {e}")
            
        return jsonify({
            "status": "success",
            "response": answer,
            "source": "llm",
            "cache_metrics": {"hit": False, "cached_tokens": 0, "savings_ratio": 0.0}
        })
        
    except Exception as e:
        return jsonify({"status": "error", "message": f"LLM query failed: {e}"}), 500


if __name__ == "__main__":
    port = int(os.environ.get("RAG_PORT", 8081))
    print(f"Starting RAG server on port {port}...")
    app.run(host="0.0.0.0", port=port, debug=False)
