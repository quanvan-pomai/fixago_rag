"""
core/retrieval.py
Decision function for whether to perform RAG vector retrieval on a given request.
"""
from core.intent_result import IntentResult
from core.policy import ResponsePolicy


def should_retrieve_context(
    query: str,
    intent_result: IntentResult,
    policy: ResponsePolicy,
) -> bool:
    """
    Return True only when RAG retrieval would add value.
    Tool-backed responses (get_services, get_groups, get_promotions) are self-sufficient;
    RAG would add noise and consume context tokens.
    """
    if not policy.retrieve_rag:
        return False

    tool = intent_result.tool_call_str or ""
    if "get_services" in tool:
        return False
    if "get_groups" in tool:
        return False
    if "get_promotions" in tool:
        return False

    return True
