"""
core/cache_policy.py
Cache decision rules and cache key construction.
"""
import hashlib
import json

from core.policy import ResponsePolicy


def should_cache_response(policy: ResponsePolicy, backend_ok: bool) -> bool:
    """Cache only when the policy allows it and the backend returned good data."""
    return policy.should_cache and backend_ok


def make_cache_key(
    system_prompt: str,
    history: str,
    data_block: str,
    rag_context: str,
    query: str,
) -> str:
    """
    Build a deterministic cache key that includes tool data, preventing stale
    cached responses when backend prices change between requests.
    """
    payload = json.dumps(
        [system_prompt, history, data_block or "", rag_context or "", query],
        ensure_ascii=False,
        sort_keys=True,
    )
    return f"pomai_cache:response:{hashlib.sha256(payload.encode()).hexdigest()}"
