"""
core/orchestrator_simple.py
Simplified orchestration for experiment branch.

Pure LLM-driven flow:
1. Input query
2. LLM reads system_prompt → decides which tool to call
3. Check data cache for that tool
4. If cached, feed data to LLM immediately
5. If not cached, call backend API → cache result → feed to LLM
6. LLM generates response based on data

No keyword checks, no deterministic functions.
Everything based on system_prompt instruction.
"""
import json
from typing import Optional, Tuple

import rag_engine
from core.cache_policy import make_cache_key, should_cache_response
from core.session import SessionManager
from core.tracer import RequestTrace
from llm_client.client import llm_chat_with_tools
from tools.handlers import (
    fetch_raw_groups, fetch_raw_services, fetch_raw_promotions,
    format_groups_for_llm, format_services_direct, format_promotions_for_llm,
    handle_get_groups, handle_get_services, handle_get_promotions,
    handle_create_booking,
)


def get_cached_or_fresh_data(tool_name: str, search_arg: Optional[str] = None) -> Tuple[list, bool]:
    """
    Check cache first. If miss, fetch from API and cache.
    Returns: (data, was_cached)
    """
    # Build cache key based on tool and args
    cache_key = f"tool_data:{tool_name}"
    if search_arg:
        cache_key += f":{search_arg}"

    # Try cache
    cached = rag_engine.cache.get(cache_key)
    if cached is not None:
        return json.loads(cached), True

    # Cache miss - fetch from API
    if tool_name == "get_groups":
        result = fetch_raw_groups()
    elif tool_name == "get_services":
        result = fetch_raw_services(search_arg or "all")
    elif tool_name == "get_promotions":
        result = fetch_raw_promotions()
    else:
        return [], False

    # Cache the raw data (30 min TTL for services/groups, 10 min for promotions)
    ttl_ms = 10 * 60 * 1000 if tool_name == "get_promotions" else 30 * 60 * 1000
    data = result.data if hasattr(result, 'data') else []

    rag_engine.cache.set(cache_key, json.dumps(data), ttl_ms)

    return data, False


def run_pure_llm_path(
    query: str,
    history: list,
    system_prompt: str,
    session_id: str,
    trace: RequestTrace,
) -> dict:
    """
    Pure LLM-driven orchestration.

    Flow:
    1. LLM reads system_prompt and decides what to do
    2. LLM calls appropriate tool (get_groups, get_services, get_promotions, create_booking)
    3. For each tool call, check cache first, then fetch
    4. Feed data to LLM
    5. LLM generates response

    No pre-checks, no keyword extraction.
    """

    # Call LLM with tools enabled
    response, tool_calls = llm_chat_with_tools(
        query=query,
        history=history,
        system_prompt=system_prompt,
        session_id=session_id,
    )

    # Process tool calls if any
    used_tools = []
    tool_results = {}

    for tool_call in tool_calls:
        tool_name = tool_call.get("function", {}).get("name", "")
        tool_args = tool_call.get("function", {}).get("arguments", {})

        if tool_name == "get_groups":
            # No args - just get all groups
            data, was_cached = get_cached_or_fresh_data("get_groups")
            formatted = format_groups_for_llm(data)
            tool_results[tool_name] = formatted
            used_tools.append(f"get_groups (cached={was_cached})")

        elif tool_name == "get_services":
            # May have category arg
            search_arg = tool_args.get("category", "all")
            data, was_cached = get_cached_or_fresh_data("get_services", search_arg)
            formatted = format_services_direct(data, search_arg)
            tool_results[tool_name] = formatted
            used_tools.append(f"get_services (cached={was_cached})")

        elif tool_name == "get_promotions":
            # No args - just get promotions
            data, was_cached = get_cached_or_fresh_data("get_promotions")
            formatted = format_promotions_for_llm(data)
            tool_results[tool_name] = formatted
            used_tools.append(f"get_promotions (cached={was_cached})")

        elif tool_name == "create_booking":
            # Handle booking creation
            name = tool_args.get("name", "")
            phone = tool_args.get("phone", "")
            address = tool_args.get("address", "")
            description = tool_args.get("description", "")

            result = handle_create_booking(name, phone, address, description)
            tool_results[tool_name] = result
            used_tools.append("create_booking")

    # If tools were called, feed results back to LLM for final response
    if tool_results:
        # Second LLM call with tool results
        final_response, _ = llm_chat_with_tools(
            query=query,
            history=history + [
                {"role": "assistant", "content": response},
                {"role": "user", "content": f"Tool results: {json.dumps(tool_results)}"},
            ],
            system_prompt=system_prompt,
            session_id=session_id,
        )
        response = final_response

    return {
        "status": "success",
        "response": response,
        "source": "llm",
        "tool_calls": used_tools,
        "session_id": session_id,
    }
