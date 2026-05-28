"""tests/context/test_context_builder.py — ContextBuilder tests."""
import pytest
from core.context_builder import ContextBuilder
from core.policy import PolicyType, ResponsePolicy


def _policy(policy_type=PolicyType.SERVICE_PRICE, instruction="", temperature=0.15,
             cache=True, rag=False):
    return ResponsePolicy(
        policy_type=policy_type,
        llm_instruction=instruction,
        should_cache=cache,
        retrieve_rag=rag,
        temperature=temperature,
    )


BUILDER = ContextBuilder()


def test_policy_instruction_appended_to_system():
    p = _policy(instruction="Tối đa 4 bullet.")
    ctx = BUILDER.build(query="test", history=[], data_block=None,
                        rag_context=None, policy=p)
    assert "Tối đa 4 bullet." in ctx.system_prompt


def test_no_instruction_no_extra_line():
    p = _policy(instruction="")
    ctx = BUILDER.build(query="test", history=[], data_block=None,
                        rag_context=None, policy=p)
    assert "[HƯỚNG DẪN PHẢN HỒI]" not in ctx.system_prompt


def test_temperature_matches_policy():
    p = _policy(temperature=0.1)
    ctx = BUILDER.build(query="test", history=[], data_block=None,
                        rag_context=None, policy=p)
    assert ctx.temperature == 0.1


def test_data_block_in_user_message():
    p = _policy()
    ctx = BUILDER.build(query="test", history=[], data_block="svc_data",
                        rag_context=None, policy=p)
    last_user = next(m for m in reversed(ctx.messages) if m["role"] == "user")
    assert "svc_data" in last_user["content"]
    assert "DỮ LIỆU HỆ THỐNG" in last_user["content"]


def test_no_data_block_no_header():
    p = _policy()
    ctx = BUILDER.build(query="myquery", history=[], data_block=None,
                        rag_context=None, policy=p)
    last_user = next(m for m in reversed(ctx.messages) if m["role"] == "user")
    assert "DỮ LIỆU HỆ THỐNG" not in last_user["content"]
    assert "myquery" in last_user["content"]


def test_rag_context_appended_when_present():
    p = _policy()
    ctx = BUILDER.build(query="q", history=[], data_block=None,
                        rag_context="rag_info", policy=p)
    last_user = next(m for m in reversed(ctx.messages) if m["role"] == "user")
    assert "rag_info" in last_user["content"]


def test_history_included_in_messages():
    p = _policy()
    history = [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"}]
    ctx = BUILDER.build(query="q", history=history, data_block=None,
                        rag_context=None, policy=p)
    roles = [m["role"] for m in ctx.messages]
    assert "system" in roles
    assert roles.count("user") >= 2


def test_messages_start_with_system():
    p = _policy()
    ctx = BUILDER.build(query="q", history=[], data_block=None,
                        rag_context=None, policy=p)
    assert ctx.messages[0]["role"] == "system"
