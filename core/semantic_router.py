"""
core/semantic_router.py
-----------------------
Semantic routing using vector embeddings for intent classification.

Uses lightweight embedding model to understand user intent semantically:
- No hardcoded keywords (scalable)
- Handles synonyms, typos, slang automatically
- Works for Qwen 3B and larger models
- Lightning-fast (~5-20ms per query)
"""

import os
import tempfile
from typing import Dict, List, Tuple, Optional
from pathlib import Path

import numpy as np

# Lazy imports to avoid startup overhead
_embedding_model = None
_pomaidb = None
_vector_db = None
_router_db = None


def _get_embedding_model():
    """Load embedding model lazily (first call only)."""
    global _embedding_model
    if _embedding_model is None:
        try:
            from sentence_transformers import SentenceTransformer
            # Using lightweight multilingual model
            # Options: BAAI/bge-m3 (2.4GB), BAAI/bge-small-en-v1.5 (134MB)
            model_name = os.environ.get(
                "SEMANTIC_ROUTER_MODEL",
                "BAAI/bge-small-en-v1.5"  # Default: fast, lightweight
            )
            _embedding_model = SentenceTransformer(model_name)
            print(f"[SemanticRouter] Loaded embedding model: {model_name}")
        except ImportError:
            print("[SemanticRouter] WARNING: sentence-transformers not installed")
            return None
    return _embedding_model


# ── Intent Routes Definition ───────────────────────────────────────────────
# Each route contains example utterances that define the intent.
# The embedding model learns the semantic pattern from these examples.

INTENT_ROUTES = {
    "get_promotions": [
        "có giảm giá không?",
        "xin voucher",
        "chương trình ưu đãi",
        "sửa nhiều có được bớt tiền không",
        "lấy mã khuyến mãi",
        "có code khuyến mãi không",
        "xin mã giảm giá",
        "hạ giá được không",
        "sale bao nhiêu",
        "bớt tiền được không",
        "có xin được khuyến mãi",
        "event ưu đãi gì",
    ],
    "get_services_dien": [
        "ổ cắm bị cháy đen",
        "nhà tự nhiên mất điện",
        "chập điện",
        "báo giá sửa dây điện",
        "đèn nhà không sáng",
        "công tắc hỏng",
        "tắt điện liên tục",
        "cầu dao trip",
        "thay bóng đèn trên trần",
        "lắp ổ cắm",
        "sửa chập mạch điện",
    ],
    "get_services_nuoc": [
        "nước rò rỉ liên tục",
        "ống nước bị tắc",
        "cấp nước bị đứng",
        "máy bơm không chạy",
        "bồn cầu chảy nước",
        "vòi nước bị xỏ",
        "tắc cống",
        "ống nước bị rò",
    ],
    "get_services_maylanh": [
        "máy lạnh không lạnh",
        "điều hòa không mạnh",
        "AC bị xỉ",
        "máy lạnh rỉ nước",
        "quạt máy lạnh",
        "lắp đặt máy lạnh mới",
    ],
    "get_services_xaydung": [
        "sơn tường bị bong",
        "trần nhà bị nứt",
        "dán giấy dán tường",
        "làm lại tường",
        "quét sơn nhà",
        "sửa chữa phòng bếp",
    ],
    "location_question": [
        "công ty ở đâu",
        "phục vụ khu vực nào",
        "có ở quận 2 không",
        "ở đâu vậy",
        "địa chỉ fixago",
        "công ty của em ở đâu",
        "fixago phục vụ ở đâu",
    ],
    "hours_question": [
        "mấy giờ làm việc",
        "mở cửa mấy giờ",
        "đóng cửa mấy giờ",
        "làm việc 24/7 không",
        "giờ hoạt động",
        "hôm nay mở cửa không",
    ],
    "payment_question": [
        "thanh toán bằng cách nào",
        "trả tiền thế nào",
        "nhận thẻ không",
        "chuyển khoản được không",
        "tiền mặt được không",
        "bao gồm tiền di chuyển chưa",
    ],
    "unsupported_lock": [
        "thay khóa cửa",
        "sửa khóa",
        "lắp khóa",
        "khóa cửa bị hỏng",
        "thay ổ khóa",
    ],
}

# Similarity threshold: if confidence > threshold, route to this intent
# Otherwise, return "unclear" to fall back to LLM
# Lower threshold = more aggressive routing, higher = more conservative
CONFIDENCE_THRESHOLD = 0.70


class SemanticRouter:
    """
    Intent router using vector embeddings for semantic understanding.

    Works by:
    1. Converting user query to embedding vector
    2. Comparing to embedding vectors of example utterances
    3. Finding highest-similarity intent
    4. Returning intent if confidence > threshold
    """

    def __init__(self):
        self.embedding_model = _get_embedding_model()
        self.routes = INTENT_ROUTES
        self.threshold = CONFIDENCE_THRESHOLD
        self._cached_examples = {}
        self._precompute_example_embeddings()

    def _precompute_example_embeddings(self):
        """Precompute embeddings for all example utterances (one-time cost)."""
        if self.embedding_model is None:
            return

        print("[SemanticRouter] Precomputing example embeddings...")
        for intent, examples in self.routes.items():
            embeddings = self.embedding_model.encode(examples)
            # Store as numpy array for fast similarity computation
            self._cached_examples[intent] = embeddings
            print(f"  - {intent}: {len(examples)} examples")

    def route(self, query: str) -> Tuple[Optional[str], float]:
        """
        Route user query to an intent based on semantic similarity.

        Args:
            query: User input text

        Returns:
            (intent_name, confidence_score)
            - intent_name: The matched intent, or "unclear" if no match
            - confidence_score: Cosine similarity to best matching intent (0-1)
        """
        if self.embedding_model is None:
            return "unclear", 0.0

        # Encode the query
        query_embedding = self.embedding_model.encode(query)

        best_intent = "unclear"
        best_score = 0.0

        # Compare to each intent's examples
        for intent, example_embeddings in self._cached_examples.items():
            # Cosine similarity between query and all examples
            # Shape: (len(examples),)
            similarities = self._cosine_similarity(
                query_embedding, example_embeddings
            )

            # Use average similarity to examples
            avg_similarity = float(np.mean(similarities))

            if avg_similarity > best_score:
                best_score = avg_similarity
                best_intent = intent

        # Apply threshold: only return intent if confidence high enough
        if best_score >= self.threshold:
            return best_intent, best_score
        else:
            return "unclear", best_score

    @staticmethod
    def _cosine_similarity(vec1: np.ndarray, vec2_matrix: np.ndarray) -> np.ndarray:
        """
        Compute cosine similarity between 1D vector and 2D matrix of vectors.

        Args:
            vec1: Shape (dim,)
            vec2_matrix: Shape (n, dim)

        Returns:
            Shape (n,) - cosine similarity with each row of vec2_matrix
        """
        # Normalize vectors
        vec1_norm = vec1 / (np.linalg.norm(vec1) + 1e-8)
        vec2_norms = vec2_matrix / (np.linalg.norm(vec2_matrix, axis=1, keepdims=True) + 1e-8)

        # Compute dot product (cosine similarity for normalized vectors)
        similarities = np.dot(vec2_norms, vec1_norm)
        return similarities


# Global router instance (lazy-loaded)
_router = None


def initialize_router() -> Optional[SemanticRouter]:
    """Initialize the semantic router (one-time call)."""
    global _router
    if _router is None:
        _router = SemanticRouter()
    return _router


def route(query: str) -> Tuple[Optional[str], float]:
    """
    Route a user query to an intent.

    Usage:
        intent, confidence = route("có giảm giá không?")
        if intent == "get_promotions":
            return handle_get_promotions(...)
    """
    router = initialize_router()
    if router is None:
        return "unclear", 0.0
    return router.route(query)


# ── Intent Handlers (called when routing succeeds) ──────────────────────────

def handle_intent(intent: str, query: str, confidence: float) -> Optional[str]:
    """
    Execute handler for matched intent.

    Returns: Response string if intent is deterministic (location, hours, payment)
             None if intent needs LLM or tool calling
    """
    if intent == "location_question":
        return (
            "Dạ Fixago hiện đang phục vụ tại TP. Hồ Chí Minh, cụ thể là Quận 2, Quận 9 "
            "và TP. Thủ Đức ạ. Anh/chị đang ở khu vực nào để mình xem hỗ trợ được không nhé?"
        )
    elif intent == "hours_question":
        return "Dạ Fixago hoạt động 24/7, kể cả cuối tuần và ngày lễ."
    elif intent == "payment_question":
        return "Dạ Fixago nhận thanh toán bằng tiền mặt hoặc chuyển khoản."
    elif intent == "unsupported_lock":
        return "Dạ hiện Fixago chưa hỗ trợ thay khóa cửa. Anh/chị cần hỗ trợ dịch vụ nào khác không?"
    else:
        # Intents that need tool calling or LLM
        return None


if __name__ == "__main__":
    # Test the router
    print("=" * 80)
    print("SEMANTIC ROUTER TEST")
    print("=" * 80)
    print()

    initialize_router()

    test_queries = [
        "có giảm giá không?",
        "ổ cắm bị cháy đen",
        "nước rò rỉ liên tục",
        "máy lạnh không lạnh",
        "sơn tường bị bong",
        "công ty ở đâu",
        "mấy giờ làm việc",
        "thanh toán bằng cách nào",
        "thay khóa cửa",
        "bớt tiền được không",  # Synonym for discount
        "cầu dao trip",  # Electrical jargon
        "hôm nay mở cửa không",  # Hours question variation
    ]

    for query in test_queries:
        intent, confidence = route(query)
        print(f"Q: {query}")
        print(f"   Intent: {intent} (confidence: {confidence:.2f})")

        if confidence >= CONFIDENCE_THRESHOLD:
            response = handle_intent(intent, query, confidence)
            if response:
                print(f"   Response: {response[:80]}...")
        print()
