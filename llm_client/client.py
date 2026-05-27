"""
llm_client/client.py
--------------------
All communication with the cheesebrain LLM server:
  - Plain chat completion
  - Native function-calling chat completion (--jinja mode)
  - Second-pass summarization call
  - GBNF grammar file loader
"""
import json
import logging
import os
from typing import Any, Dict, List, Optional, Tuple

import requests

from tools_schema import FIXAGO_TOOLS

logger = logging.getLogger("fixago.llm_client")

LLM_URL = os.environ.get("LLM_URL", "http://127.0.0.1:8080/v1/chat/completions")


LLM_TIMEOUT = int(os.environ.get("LLM_TIMEOUT", "120"))


def llm_chat(
    messages: List[Dict],
    temperature: float = 0.0,
    timeout: int = None,
    grammar: Optional[str] = None,
) -> str:
    """Plain chat completion. Optionally constrain output with a GBNF grammar."""
    if timeout is None:
        timeout = LLM_TIMEOUT
    payload: Dict[str, Any] = {
        "messages": messages,
        "temperature": temperature,
        "stream": False,
    }
    if grammar:
        payload["grammar"] = grammar

    try:
        resp = requests.post(LLM_URL, json=payload, timeout=timeout)
    except requests.exceptions.Timeout:
        logger.warning("llm_chat timed out after %ss", timeout)
        return "Dạ mình đang xử lý hơi chậm, bạn thử lại sau giây lát nhé."
    if resp.status_code != 200:
        err = resp.text[:300]
        # Context size exceeded — trim history and retry once
        if resp.status_code == 400 and "exceed_context_size" in err:
            logger.warning("Context size exceeded, trimming messages and retrying")
            trimmed = _trim_messages(messages)
            try:
                resp2 = requests.post(LLM_URL, json={**payload, "messages": trimmed}, timeout=timeout)
                if resp2.status_code == 200:
                    return resp2.json()["choices"][0]["message"]["content"]
            except Exception:
                pass
            return "Dạ mình chưa thể xử lý câu hỏi này lúc này. Bạn thử hỏi ngắn gọn hơn nhé."
        raise RuntimeError(f"LLM server error {resp.status_code}: {err}")
    return resp.json()["choices"][0]["message"]["content"]


def _trim_messages(messages: List[Dict]) -> List[Dict]:
    """
    Reduce messages to fit a small context window.
    Keep: system prompt (truncated) + last 2 user/assistant turns + current user message.
    """
    system = next((m for m in messages if m.get("role") == "system"), None)
    non_system = [m for m in messages if m.get("role") != "system"]

    # Truncate system prompt to ~300 chars (first paragraph only)
    trimmed_system = []
    if system:
        content = (system.get("content") or "")[:400]
        trimmed_system = [{"role": "system", "content": content}]

    # Keep only last 3 non-system messages (prev assistant + current user at minimum)
    recent = non_system[-3:] if len(non_system) > 3 else non_system

    return trimmed_system + recent


def llm_chat_with_tools(
    messages: List[Dict],
    temperature: float = 0.0,
    timeout: int = 300,
) -> Tuple[Optional[str], Any, Dict]:
    """
    Native OpenAI-style function calling (requires cheese-server --jinja).

    Returns:
        (tool_name, tool_args, raw_message)  — when model called a tool
        (None, text_response, raw_message)   — when model replied with text
    """
    payload = {
        "messages": messages,
        "temperature": temperature,
        "tools": FIXAGO_TOOLS,
        "tool_choice": "auto",
    }
    resp = requests.post(LLM_URL, json=payload, timeout=timeout)
    if resp.status_code != 200:
        raise RuntimeError(f"LLM server error {resp.status_code}: {resp.text[:200]}")

    message = resp.json()["choices"][0]["message"]
    tool_calls = message.get("tool_calls")

    if tool_calls:
        tc = tool_calls[0]
        try:
            args = json.loads(tc["function"]["arguments"])
        except Exception:
            args = {}
        return tc["function"]["name"], args, message

    return None, message.get("content", ""), message


def llm_summarize(
    messages: List[Dict],
    api_context: str,
    instruction: str,
    timeout: int = None,
) -> str:
    """
    Second-pass LLM call: append tool result + instruction, get a natural response.
    Used after get_groups / get_promotions to produce friendly prose.
    """
    if timeout is None:
        timeout = LLM_TIMEOUT
    next_messages = list(messages) + [
        {"role": "user", "content": f"{api_context}\n\n{instruction}"}
    ]
    return llm_chat(next_messages, temperature=0.2, timeout=timeout)


def load_grammar(filename: str) -> str:
    """
    Load a GBNF grammar file from the grammars/ directory.
    Strips comment lines. Returns empty string on any failure.
    """
    try:
        path = os.path.join(os.path.dirname(__file__), "..", "grammars", filename)
        with open(path, "r", encoding="utf-8") as f:
            lines = [l for l in f if not l.strip().startswith("#")]
            return "".join(lines).strip()
    except Exception:
        return ""
