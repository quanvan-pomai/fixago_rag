"""
core/retrieval.py
Decision function for whether to perform RAG vector retrieval on a given request.
"""


_SKIP_RAG_CONFIRMATIONS = {"ok", "oke", "yes", "chốt", "xác nhận", "đặt đi", "confirm", "co", "có"}

_TOOL_SELF_SUFFICIENT = ("get_services", "get_groups", "get_promotions", "create_booking")


def should_retrieve_context(query: str, tool_name: str | None = None, booking_state: dict = None) -> bool:
    """
    Return True only when RAG retrieval adds value.

    Skip when:
    - A backend tool already provides the facts (get_services etc.)
    - User is just confirming or providing contact info
    - User is in booking confirmation state
    """
    if tool_name and any(t in tool_name for t in _TOOL_SELF_SUFFICIENT):
        return False

    q = (query or "").strip().lower()
    if q in _SKIP_RAG_CONFIRMATIONS:
        return False

    if booking_state and booking_state.get("awaiting_confirmation"):
        return False

    return True
