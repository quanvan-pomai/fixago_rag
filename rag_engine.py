import os
import sys
import ctypes
import shutil
import threading
import logging
import unicodedata
import requests
from pathlib import Path
from typing import Any, Dict, List, Optional

logging.basicConfig(
    level=os.environ.get("RAG_LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s"
)

logger = logging.getLogger("fixago.rag_engine")

rag_lock = threading.RLock()

workspace_dir = Path(os.environ.get("RAG_WORKSPACE_DIR", Path(__file__).resolve().parent)).resolve()
data_dir = Path(os.environ.get("RAG_DATA_DIR", workspace_dir / "data")).resolve()
pomaidb_dir = Path(os.environ.get("POMAIDB_DIR", data_dir / "pomaidb")).resolve()
pomaicache_dir = Path(os.environ.get("POMAICACHE_DIR", data_dir / "pomaicache")).resolve()

pomaidb_python_dir = Path(os.environ.get("POMAIDB_PYTHON_DIR", workspace_dir / "pomaidb" / "python")).resolve()
pomaicache_build_dir = Path(os.environ.get("POMAICACHE_BUILD_DIR", workspace_dir / "pomaicache" / "build")).resolve()
pomaidb_c_lib = Path(os.environ.get("POMAI_C_LIB", workspace_dir / "pomaidb" / "build" / "libpomai_c.so")).resolve()

sys.path.insert(0, str(pomaidb_python_dir))
sys.path.insert(0, str(pomaicache_build_dir))

os.environ.setdefault("POMAI_C_LIB", str(pomaidb_c_lib))

RAG_DIM = int(os.environ.get("RAG_DIM", "384"))
RAG_SHARDS = int(os.environ.get("RAG_SHARDS", "1"))
RAG_MEMBRANE = os.environ.get("RAG_MEMBRANE", "docs")
RAG_MAX_CHUNK_BYTES = int(os.environ.get("RAG_MAX_CHUNK_BYTES", "512"))
RAG_MAX_DOC_BYTES = int(os.environ.get("RAG_MAX_DOC_BYTES", str(4 * 1024 * 1024)))
RAG_MAX_CHUNKS_PER_BATCH = int(os.environ.get("RAG_MAX_CHUNKS_PER_BATCH", "32"))
RAG_OVERLAP_BYTES = int(os.environ.get("RAG_OVERLAP_BYTES", "0"))
RAG_RESET_ON_START = os.environ.get("RAG_RESET_ON_START", "false").lower() in {"1", "true", "yes", "on"}
RAG_SEED_ON_START = os.environ.get("RAG_SEED_ON_START", "true").lower() in {"1", "true", "yes", "on"}
RAG_TOKENIZER_URL = os.environ.get("RAG_TOKENIZER_URL", "http://127.0.0.1:8080/tokenize")
RAG_TOKENIZER_TIMEOUT = float(os.environ.get("RAG_TOKENIZER_TIMEOUT", "10"))
RAG_CACHE_MEMORY_LIMIT_BYTES = int(os.environ.get("RAG_CACHE_MEMORY_LIMIT_BYTES", str(128 * 1024 * 1024)))

try:
    import pomaidb
except Exception as exc:
    raise RuntimeError(f"Cannot import pomaidb from {pomaidb_python_dir}: {exc}") from exc

try:
    import pomaicache
except Exception as exc:
    raise RuntimeError(f"Cannot import pomaicache from {pomaicache_build_dir}: {exc}") from exc


class RagEngineError(RuntimeError):
    pass


def ensure_directories() -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    pomaicache_dir.mkdir(parents=True, exist_ok=True)


def reset_database_if_requested() -> None:
    if not RAG_RESET_ON_START:
        return

    if pomaidb_dir.exists():
        shutil.rmtree(pomaidb_dir)
        logger.warning("PomaiDB directory reset: %s", pomaidb_dir)


def validate_doc_id(doc_id: Any) -> int:
    try:
        value = int(doc_id)
    except Exception as exc:
        raise ValueError("doc_id must be an integer") from exc

    if value < 0:
        raise ValueError("doc_id must be non-negative")

    return value


def validate_text(text: Any, field_name: str = "text") -> str:
    if text is None:
        raise ValueError(f"{field_name} is required")

    value = str(text).strip()

    if not value:
        raise ValueError(f"{field_name} must not be empty")

    encoded = value.encode("utf-8")

    if len(encoded) > RAG_MAX_DOC_BYTES:
        raise ValueError(f"{field_name} exceeds max size of {RAG_MAX_DOC_BYTES} bytes")

    return value


def create_chunk_options():
    opts = pomaidb._lib._pomai_rag_chunk_options()
    opts.struct_size = ctypes.sizeof(pomaidb._lib._pomai_rag_chunk_options())
    opts.max_chunk_bytes = RAG_MAX_CHUNK_BYTES
    opts.max_doc_bytes = RAG_MAX_DOC_BYTES
    opts.max_chunks_per_batch = RAG_MAX_CHUNKS_PER_BATCH
    opts.overlap_bytes = RAG_OVERLAP_BYTES
    return opts


def initialize_database():
    ensure_directories()
    reset_database_if_requested()

    db_instance = pomaidb.open_db(str(pomaidb_dir), dim=RAG_DIM, shards=RAG_SHARDS)

    try:
        pomaidb.create_rag_membrane(db_instance, RAG_MEMBRANE, dim=RAG_DIM, shard_count=RAG_SHARDS)
    except Exception as exc:
        message = str(exc).lower()
        if "exist" not in message and "already" not in message and "duplicate" not in message:
            raise

    cache_instance = pomaicache.Cache(
        data_dir=str(pomaicache_dir),
        memory_limit_bytes=RAG_CACHE_MEMORY_LIMIT_BYTES
    )

    opts = create_chunk_options()
    pipeline_instance = ctypes.c_void_p()

    pomaidb._check(
        pomaidb._lib.pomai_rag_pipeline_create(
            db_instance,
            RAG_MEMBRANE.encode("utf-8"),
            RAG_DIM,
            ctypes.byref(opts),
            ctypes.byref(pipeline_instance)
        )
    )

    if not pipeline_instance:
        raise RagEngineError("Failed to initialize RAG pipeline")

    logger.info("PomaiDB initialized at %s", pomaidb_dir)
    logger.info("PomaiCache initialized at %s", pomaicache_dir)
    logger.info("RAG membrane initialized: %s", RAG_MEMBRANE)

    return db_instance, cache_instance, pipeline_instance


def freeze_database() -> None:
    try:
        pomaidb.freeze(db)
    except Exception as exc:
        logger.warning("PomaiDB freeze failed: %s", exc)


def ingest_document(doc_id: Any, text: Any) -> Dict[str, Any]:
    safe_doc_id = validate_doc_id(doc_id)
    safe_text = validate_text(text, "text")
    text_buf = safe_text.encode("utf-8")

    with rag_lock:
        pomaidb._check(
            pomaidb._lib.pomai_rag_ingest_document(
                pipeline,
                safe_doc_id,
                text_buf,
                len(text_buf)
            )
        )
        freeze_database()

    return {
        "doc_id": safe_doc_id,
        "bytes": len(text_buf),
        "status": "ingested"
    }


def retrieve_context(query: Any, top_k: int = 5, max_len: int = 65536) -> str:
    safe_query = validate_text(query, "query")

    try:
        safe_top_k = int(top_k)
    except Exception as exc:
        raise ValueError("top_k must be an integer") from exc

    if safe_top_k <= 0:
        safe_top_k = 1

    if safe_top_k > 20:
        safe_top_k = 20

    query_buf = safe_query.encode("utf-8")
    out_buf = ctypes.create_string_buffer(max_len)
    out_len = ctypes.c_size_t()

    with rag_lock:
        pomaidb._check(
            pomaidb._lib.pomai_rag_retrieve_context_buf(
                pipeline,
                query_buf,
                len(query_buf),
                safe_top_k,
                out_buf,
                max_len,
                ctypes.byref(out_len)
            )
        )

    if out_len.value <= 0:
        return ""

    return out_buf.raw[:out_len.value].decode("utf-8", errors="replace").strip()


def strip_vietnamese_accents(text: str) -> str:
    normalized = unicodedata.normalize("NFD", text)
    without_marks = "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")
    return without_marks.replace("đ", "d").replace("Đ", "D")


def normalize_query(query: Any) -> str:
    raw = validate_text(query, "query")
    q_lower = raw.lower()
    q_no_accents = strip_vietnamese_accents(q_lower)

    synonym_groups = {
        "điện": [
            "dien", "chập", "chap", "ổ cắm", "o cam", "bóng đèn", "bong den",
            "công tắc", "cong tac", "tủ điện", "tu dien", "aptomat", "cb"
        ],
        "nước": [
            "nuoc", "ống nước", "ong nuoc", "rò nước", "ro nuoc", "nghẹt",
            "nghet", "vòi sen", "voi sen", "bồn cầu", "bon cau", "máy bơm", "may bom"
        ],
        "điện lạnh": [
            "dien lanh", "máy lạnh", "may lanh", "điều hòa", "dieu hoa",
            "tủ lạnh", "tu lanh", "nạp gas", "nap gas", "không lạnh", "khong lanh"
        ],
        "xây dựng": [
            "xay dung", "sơn", "son", "chống thấm", "chong tham",
            "ốp lát", "op lat", "gạch", "gach", "ban công", "ban cong"
        ],
        "thạch cao": [
            "thach cao", "trần", "tran", "vách ngăn", "vach ngan",
            "nứt", "nut", "bể", "be"
        ],
        "sửa chữa": [
            "sua", "sửa", "hỏng", "hong", "lỗi", "loi", "khắc phục", "khac phuc"
        ],
        "giá": [
            "gia", "bao nhiêu", "bao nhieu", "báo giá", "bao gia", "chi phí", "chi phi"
        ]
    }

    additions = []

    for canonical, variants in synonym_groups.items():
        canonical_no_accents = strip_vietnamese_accents(canonical.lower())
        if canonical in q_lower or canonical_no_accents in q_no_accents:
            if canonical not in q_lower:
                additions.append(canonical)
            continue

        for variant in variants:
            variant_no_accents = strip_vietnamese_accents(variant.lower())
            if variant in q_lower or variant_no_accents in q_no_accents:
                if canonical not in q_lower:
                    additions.append(canonical)
                break

    seen = set()
    unique_additions = []

    for item in additions:
        if item not in seen:
            seen.add(item)
            unique_additions.append(item)

    if unique_additions:
        return raw + " " + " ".join(unique_additions)

    return raw


def fallback_tokenize(text: str) -> List[int]:
    return list(text.encode("utf-8"))


def tokenize_text(text: Any) -> List[int]:
    safe_text = str(text or "")

    if not safe_text:
        return []

    try:
        response = requests.post(
            RAG_TOKENIZER_URL,
            json={"content": safe_text},
            timeout=RAG_TOKENIZER_TIMEOUT
        )

        if response.status_code == 200:
            payload = response.json()
            tokens = payload.get("tokens", [])

            if isinstance(tokens, list):
                clean_tokens = []
                for token in tokens:
                    try:
                        clean_tokens.append(int(token))
                    except Exception:
                        continue

                if clean_tokens:
                    return clean_tokens

    except Exception as exc:
        logger.warning("Tokenizer request failed: %s", exc)

    return fallback_tokenize(safe_text)


def cache_get(key: str) -> Optional[bytes]:
    if not key:
        return None

    with rag_lock:
        value = cache.get(key)

    return value


def cache_set(key: str, value: bytes, ttl_ms: int = 600000) -> bool:
    if not key:
        return False

    if not isinstance(value, bytes):
        value = str(value).encode("utf-8")

    with rag_lock:
        cache.set(key, value, ttl_ms=ttl_ms)

    return True


def prompt_cache_get(tokens: List[int]) -> Any:
    if not tokens:
        return None

    with rag_lock:
        return cache.prompt_get(tokens)


def prompt_cache_put(tokens: List[int], value: bytes, ttl_ms: int = 600000) -> bool:
    if not tokens:
        return False

    if not isinstance(value, bytes):
        value = str(value).encode("utf-8")

    with rag_lock:
        cache.prompt_put(tokens, value, ttl_ms=ttl_ms)

    return True


def healthcheck() -> Dict[str, Any]:
    status = {
        "ok": True,
        "workspace_dir": str(workspace_dir),
        "data_dir": str(data_dir),
        "pomaidb_dir": str(pomaidb_dir),
        "pomaicache_dir": str(pomaicache_dir),
        "rag_dim": RAG_DIM,
        "rag_shards": RAG_SHARDS,
        "rag_membrane": RAG_MEMBRANE,
        "reset_on_start": RAG_RESET_ON_START,
        "seed_on_start": RAG_SEED_ON_START
    }

    try:
        test_context = retrieve_context("Fixago", top_k=1)
        status["retrieve_ok"] = isinstance(test_context, str)
    except Exception as exc:
        status["ok"] = False
        status["retrieve_ok"] = False
        status["error"] = str(exc)

    return status


SEEDS = [
    (
        1001,
        "Fixago là nền tảng đặt thợ sửa chữa điện, nước, điện lạnh, xây dựng, thạch cao uy tín hàng đầu."
    ),
    (
        1002,
        "Dịch vụ sửa chữa điện của Fixago bao gồm khắc phục sự cố chập cháy điện, đi lại đường dây điện âm tường, lắp đặt thiết bị điện gia dụng như bóng đèn, ổ cắm và tủ điện."
    ),
    (
        1003,
        "Dịch vụ sửa chữa nước của Fixago bao gồm thông nghẹt đường ống nước, sửa vòi sen bị rò rỉ, thay đường ống nước mới, lắp đặt bồn cầu và máy bơm nước."
    ),
    (
        1004,
        "Dịch vụ điện lạnh của Fixago bao gồm bảo dưỡng điều hòa, nạp gas máy lạnh, sửa tủ lạnh không lạnh và lắp đặt máy giặt."
    ),
    (
        1005,
        "Dịch vụ sửa chữa xây dựng của Fixago bao gồm sơn sửa nhà cửa, chống thấm dột tường nhà, ốp lát gạch nền và sửa chữa ban công."
    ),
    (
        1006,
        "Dịch vụ trần thạch cao của Fixago bao gồm đóng trần thạch cao nổi, làm vách ngăn thạch cao cách âm và sửa chữa các tấm thạch cao bị nứt bể."
    )
]


def seed_initial_documents() -> None:
    if not RAG_SEED_ON_START:
        return

    failures = []

    for doc_id, text in SEEDS:
        try:
            ingest_document(doc_id, text)
        except Exception as exc:
            failures.append((doc_id, str(exc)))

    if failures:
        logger.warning("Seed completed with failures: %s", failures)
    else:
        logger.info("Seed completed successfully")


db, cache, pipeline = initialize_database()
seed_initial_documents()