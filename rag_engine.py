import os
import sys
import ctypes
import shutil
import requests
import threading

rag_lock = threading.Lock()

# Setup import paths for pomaidb and pomaicache
workspace_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(workspace_dir, "pomaidb", "python"))
sys.path.insert(0, os.path.join(workspace_dir, "pomaicache", "build"))

# Set POMAI_C_LIB environment variable if not already set
if not os.environ.get("POMAI_C_LIB"):
    os.environ["POMAI_C_LIB"] = os.path.join(workspace_dir, "pomaidb", "build", "libpomai_c.so")

import pomaidb
import pomaicache

# Data directories
data_dir = os.path.join(workspace_dir, "data")
pomaidb_dir = os.path.join(data_dir, "pomaidb")
pomaicache_dir = os.path.join(data_dir, "pomaicache")

# Clean/Delete existing PomaiDB data directory to prevent chunk ID collision on restart
if os.path.exists(pomaidb_dir):
    try:
        shutil.rmtree(pomaidb_dir)
        print("Cleaned existing PomaiDB directory.")
    except Exception as e:
        print(f"Could not clean PomaiDB directory: {e}")

os.makedirs(data_dir, exist_ok=True)

# Initialize Databases
print("Initializing PomaiDB and PomaiCache...")
db = pomaidb.open_db(pomaidb_dir, dim=384, shards=1)
pomaidb.create_rag_membrane(db, "docs", dim=384, shard_count=1)
print("Created 'docs' RAG membrane.")

cache = pomaicache.Cache(data_dir=pomaicache_dir, memory_limit_bytes=128 * 1024 * 1024)
print("Databases initialized successfully.")

# Setup single global pipeline instance using ctypes to maintain monotonic next_chunk_id_
opts = pomaidb._lib._pomai_rag_chunk_options()
opts.struct_size = ctypes.sizeof(pomaidb._lib._pomai_rag_chunk_options())
opts.max_chunk_bytes = 512
opts.max_doc_bytes = 4 * 1024 * 1024
opts.max_chunks_per_batch = 32
opts.overlap_bytes = 0

pipeline = ctypes.c_void_p()
pomaidb._check(
    pomaidb._lib.pomai_rag_pipeline_create(
        db, b"docs", 384, ctypes.byref(opts), ctypes.byref(pipeline)
    )
)
print("RAG pipeline initialized.")

def ingest_document(doc_id, text):
    with rag_lock:
        text_buf = text.encode("utf-8")
        pomaidb._check(
            pomaidb._lib.pomai_rag_ingest_document(
                pipeline, int(doc_id), text_buf, len(text_buf)
            )
        )
        pomaidb.freeze(db)

def retrieve_context(query, top_k=5):
    with rag_lock:
        query_buf = query.encode("utf-8")
        max_len = 65536
        out_buf = ctypes.create_string_buffer(max_len)
        out_len = ctypes.c_size_t()
        pomaidb._check(
            pomaidb._lib.pomai_rag_retrieve_context_buf(
                pipeline, query_buf, len(query_buf), top_k, out_buf, max_len, ctypes.byref(out_len)
            )
        )
        if out_len.value == 0:
            return ""
        return out_buf.value[:out_len.value].decode("utf-8", errors="replace")

def normalize_query(query):
    query_lower = query.lower()
    accents_map = {
        "sua": "sửa",
        "dien": "điện",
        "nuoc": "nước",
        "lanh": "lạnh",
        "xay": "xây",
        "dung": "dựng",
        "thach": "thạch",
        "cao": "cao",
        "chi tiet": "chi tiết"
    }
    boost_terms = []
    for k, v in accents_map.items():
        if k in query_lower:
            boost_terms.append(v)
    if boost_terms:
        new_terms = [term for term in boost_terms if term not in query_lower]
        if new_terms:
            query = query + " " + " ".join(new_terms)
    return query

def tokenize_text(text):
    """Query Cheesebrain model server for prompt tokens."""
    try:
        response = requests.post("http://127.0.0.1:8080/tokenize", json={"content": text}, timeout=10)
        if response.status_code == 200:
            return response.json().get("tokens", [])
    except Exception as e:
        print(f"Tokenize failed: {e}")
    return [ord(c) for c in text]

# Seed initial documents
SEEDS = [
    (1001, "Fixago là nền tảng đặt thợ sửa chữa điện, nước, điện lạnh, xây dựng, thạch cao uy tín hàng đầu."),
    (1002, "Dịch vụ sửa chữa điện của Fixago bao gồm khắc phục sự cố chập cháy điện, đi lại đường dây điện âm tường, lắp đặt thiết bị điện gia dụng như bóng đèn, ổ cắm và tủ điện."),
    (1003, "Dịch vụ sửa chữa nước của Fixago bao gồm thông nghẹt đường ống nước, sửa vòi sen bị rò rỉ, thay đường ống nước mới, lắp đặt bồn cầu và máy bơm nước."),
    (1004, "Dịch vụ điện lạnh của Fixago bao gồm bảo dưỡng điều hòa, nạp gas máy lạnh, sửa tủ lạnh không lạnh và lắp đặt máy giặt."),
    (1005, "Dịch vụ sửa chữa xây dựng của Fixago bao gồm sơn sửa nhà cửa, chống thấm dột tường nhà, ốp lát gạch nền và sửa chữa ban công."),
    (1006, "Dịch vụ trần thạch cao của Fixago bao gồm đóng trần thạch cao nổi, làm vách ngăn thạch cao cách âm và sửa chữa các tấm thạch cao bị nứt bể.")
]

print("Seeding initial documents into PomaiDB RAG...")
for doc_id, text in SEEDS:
    ingest_document(doc_id, text)
print("Seeding complete.")
