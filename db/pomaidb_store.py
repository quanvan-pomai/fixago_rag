"""
db/pomaidb_store.py
-------------------
PomaiDB vector store: initialization, document ingestion, context retrieval,
and the seed data loaded on startup.

All heavy C-extension calls live here. The rest of the app should never
import pomaidb or ctypes directly.
"""
import ctypes
import logging
import os
import shutil
import unicodedata
from pathlib import Path
from typing import Any, Dict
from core.lexicon import FIXAGO_SYNONYMS

logger = logging.getLogger("fixago.pomaidb_store")

# ── Path resolution ──────────────────────────────────────────────────────────

workspace_dir    = Path(os.environ.get("RAG_WORKSPACE_DIR", Path(__file__).resolve().parent.parent)).resolve()
data_dir         = Path(os.environ.get("RAG_DATA_DIR",      workspace_dir / "data")).resolve()
pomaidb_dir      = Path(os.environ.get("POMAIDB_DIR",       data_dir / "pomaidb")).resolve()
pomaidb_python_dir = Path(os.environ.get("POMAIDB_PYTHON_DIR", workspace_dir / "pomaidb" / "python")).resolve()
pomaidb_c_lib    = Path(os.environ.get("POMAI_C_LIB",       workspace_dir / "pomaidb" / "build" / "libpomai_c.so")).resolve()

# ── Config ───────────────────────────────────────────────────────────────────

RAG_DIM                  = int(os.environ.get("RAG_DIM",                  "384"))
RAG_SHARDS               = int(os.environ.get("RAG_SHARDS",               "1"))
RAG_MEMBRANE             = os.environ.get("RAG_MEMBRANE",                 "docs")
RAG_MAX_CHUNK_BYTES      = int(os.environ.get("RAG_MAX_CHUNK_BYTES",      "512"))
RAG_MAX_DOC_BYTES        = int(os.environ.get("RAG_MAX_DOC_BYTES",        str(4 * 1024 * 1024)))
RAG_MAX_CHUNKS_PER_BATCH = int(os.environ.get("RAG_MAX_CHUNKS_PER_BATCH", "32"))
RAG_OVERLAP_BYTES        = int(os.environ.get("RAG_OVERLAP_BYTES",        "0"))
RAG_RESET_ON_START       = os.environ.get("RAG_RESET_ON_START", "false").lower() in {"1", "true", "yes", "on"}
RAG_SEED_ON_START        = os.environ.get("RAG_SEED_ON_START",  "true").lower()  in {"1", "true", "yes", "on"}

# ── Seed documents ───────────────────────────────────────────────────────────

SEEDS = [
    (1001, "Fixago là nền tảng đặt thợ sửa chữa điện, nước, điện lạnh, xây dựng, thạch cao uy tín hàng đầu."),
    (1002, "Dịch vụ sửa chữa điện của Fixago bao gồm khắc phục sự cố chập cháy điện, đi lại đường dây điện âm tường, lắp đặt thiết bị điện gia dụng như bóng đèn, ổ cắm và tủ điện."),
    (1003, "Dịch vụ sửa chữa nước của Fixago bao gồm thông nghẹt đường ống nước, sửa vòi sen bị rò rỉ, thay đường ống nước mới, lắp đặt bồn cầu và máy bơm nước."),
    (1004, "Dịch vụ điện lạnh của Fixago bao gồm bảo dưỡng điều hòa, nạp gas máy lạnh, sửa tủ lạnh không lạnh và lắp đặt máy giặt."),
    (1005, "Dịch vụ sửa chữa xây dựng của Fixago bao gồm sơn sửa nhà cửa, chống thấm dột tường nhà, ốp lát gạch nền và sửa chữa ban công."),
    (1006, "Dịch vụ trần thạch cao của Fixago bao gồm đóng trần thạch cao nổi, làm vách ngăn thạch cao cách âm và sửa chữa các tấm thạch cao bị nứt bể."),

    # FAQ: Response time and booking
    (2001, "Thời gian đáp ứng của Fixago tùy thuộc vào vị trí của khách hàng đến địa điểm thợ. Khách hàng có thể đặt lịch bất kỳ ngày nào muốn, tổng cộng sẽ tốn khoảng 15-30 phút tùy tình hình đường xá. Khách hàng có thể đặt lịch trực tiếp trên website, trong app mobile hoặc liên hệ trực tiếp với Fixie để được hỗ trợ đặt lịch."),

    # FAQ: Technician tracking
    (2002, "Khách hàng có thể biết thợ sẽ đến khi nào bằng cách thợ sẽ liên hệ trước khi đến, hoặc khách hàng có thể theo dõi vị trí thợ thông qua ứng dụng mobile của Fixago."),

    # FAQ: Travel fee included
    (2003, "Chi phí dịch vụ của Fixago đã bao gồm phí di chuyển, không phải trả thêm. Giá trên website là giá cuối cùng mà khách hàng sẽ thanh toán."),
]

# ── Internal helpers ─────────────────────────────────────────────────────────

def _validate_doc_id(doc_id: Any) -> int:
    try:
        value = int(doc_id)
    except Exception as exc:
        raise ValueError("doc_id must be an integer") from exc
    if value < 0:
        raise ValueError("doc_id must be non-negative")
    return value


def _validate_text(text: Any, field_name: str = "text") -> str:
    if text is None:
        raise ValueError(f"{field_name} is required")
    value = str(text).strip()
    if not value:
        raise ValueError(f"{field_name} must not be empty")
    if len(value.encode("utf-8")) > RAG_MAX_DOC_BYTES:
        raise ValueError(f"{field_name} exceeds max size of {RAG_MAX_DOC_BYTES} bytes")
    return value


def _create_chunk_options(pomaidb_lib):
    opts = pomaidb_lib._lib._pomai_rag_chunk_options()
    opts.struct_size         = ctypes.sizeof(pomaidb_lib._lib._pomai_rag_chunk_options())
    opts.max_chunk_bytes     = RAG_MAX_CHUNK_BYTES
    opts.max_doc_bytes       = RAG_MAX_DOC_BYTES
    opts.max_chunks_per_batch = RAG_MAX_CHUNKS_PER_BATCH
    opts.overlap_bytes       = RAG_OVERLAP_BYTES
    return opts


# ── Public query normalization ───────────────────────────────────────────────

def strip_vietnamese_accents(text: str) -> str:
    normalized = unicodedata.normalize("NFD", text)
    without_marks = "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")
    return without_marks.replace("đ", "d").replace("Đ", "D")


def normalize_query(query: Any) -> str:
    """Expand query with Vietnamese synonyms for better RAG recall."""
    raw = _validate_text(query, "query")
    q_lower = raw.lower()
    q_no_accents = strip_vietnamese_accents(q_lower)

    synonym_groups = FIXAGO_SYNONYMS

    additions = []
    seen: set = set()
    for canonical, variants in synonym_groups.items():
        canonical_no_acc = strip_vietnamese_accents(canonical.lower())
        matched = canonical in q_lower or canonical_no_acc in q_no_accents
        if not matched:
            for v in variants:
                if v in q_lower or strip_vietnamese_accents(v) in q_no_accents:
                    matched = True
                    break
        if matched and canonical not in q_lower and canonical not in seen:
            additions.append(canonical)
            seen.add(canonical)

    return (raw + " " + " ".join(additions)) if additions else raw


# ── Store class ──────────────────────────────────────────────────────────────

class PomaiDBStore:
    """Wraps the PomaiDB C extension for ingestion and retrieval."""

    def __init__(self, lock):
        import sys
        sys.path.insert(0, str(pomaidb_python_dir))
        os.environ.setdefault("POMAI_C_LIB", str(pomaidb_c_lib))

        try:
            import pomaidb as _pomaidb
        except Exception as exc:
            raise RuntimeError(f"Cannot import pomaidb from {pomaidb_python_dir}: {exc}") from exc

        self._lib   = _pomaidb
        self._lock  = lock
        self._db, self._pipeline = self._init()

    def _init(self):
        data_dir.mkdir(parents=True, exist_ok=True)

        if RAG_RESET_ON_START and pomaidb_dir.exists():
            shutil.rmtree(pomaidb_dir)
            logger.warning("PomaiDB directory reset: %s", pomaidb_dir)

        db = self._lib.open_db(str(pomaidb_dir), dim=RAG_DIM, shards=RAG_SHARDS)

        try:
            self._lib.create_rag_membrane(db, RAG_MEMBRANE, dim=RAG_DIM, shard_count=RAG_SHARDS)
        except Exception as exc:
            msg = str(exc).lower()
            if "exist" not in msg and "already" not in msg and "duplicate" not in msg:
                raise

        opts = _create_chunk_options(self._lib)
        pipeline = ctypes.c_void_p()
        self._lib._check(
            self._lib._lib.pomai_rag_pipeline_create(
                db, RAG_MEMBRANE.encode("utf-8"), RAG_DIM,
                ctypes.byref(opts), ctypes.byref(pipeline)
            )
        )
        if not pipeline:
            raise RuntimeError("Failed to initialize RAG pipeline")

        logger.info("PomaiDB initialized at %s", pomaidb_dir)
        return db, pipeline

    def _freeze(self):
        try:
            self._lib.freeze(self._db)
        except Exception as exc:
            logger.warning("PomaiDB freeze failed: %s", exc)

    def ingest(self, doc_id: Any, text: Any) -> Dict[str, Any]:
        safe_id   = _validate_doc_id(doc_id)
        safe_text = _validate_text(text, "text")
        buf       = safe_text.encode("utf-8")
        with self._lock:
            self._lib._check(
                self._lib._lib.pomai_rag_ingest_document(
                    self._pipeline, safe_id, buf, len(buf)
                )
            )
            self._freeze()
        return {"doc_id": safe_id, "bytes": len(buf), "status": "ingested"}

    def retrieve(self, query: Any, top_k: int = 5, max_len: int = 65536) -> str:
        safe_query = _validate_text(query, "query")
        safe_top_k = max(1, min(int(top_k), 20))
        qbuf   = safe_query.encode("utf-8")
        outbuf = ctypes.create_string_buffer(max_len)
        outlen = ctypes.c_size_t()
        with self._lock:
            self._lib._check(
                self._lib._lib.pomai_rag_retrieve_context_buf(
                    self._pipeline, qbuf, len(qbuf), safe_top_k,
                    outbuf, max_len, ctypes.byref(outlen)
                )
            )
        if outlen.value <= 0:
            return ""
        return outbuf.raw[:outlen.value].decode("utf-8", errors="replace").strip()

    def seed(self):
        if not RAG_SEED_ON_START:
            return
        failures = []
        for doc_id, text in SEEDS:
            try:
                self.ingest(doc_id, text)
            except Exception as exc:
                failures.append((doc_id, str(exc)))
        if failures:
            logger.warning("Seed completed with failures: %s", failures)
        else:
            logger.info("Seed completed successfully")


class FakePomaiDBStore:
    """No-op vector store used in FIXAGO_TEST_MODE — no C extension needed."""

    def ingest(self, doc_id, text):
        pass

    def retrieve(self, query, top_k=5, max_len=65536):
        return ""

    def seed(self):
        pass
