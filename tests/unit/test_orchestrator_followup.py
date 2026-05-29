import os
os.environ.setdefault("FIXAGO_TEST_MODE", "1")

from core.orchestrator import run_legacy_fast_path
import rag_engine


def test_short_yes_after_service_clarification_calls_groups(monkeypatch):
    def fake_execute_tool(tool_str, messages, used_tools):
        used_tools.append("Tool [Backend API]: GET /services/groups")
        return "Fixago cung cấp các dịch vụ: Điện, Nước và Xây dựng."

    monkeypatch.setattr("core.orchestrator.execute_tool", fake_execute_tool)

    history = [
        {
            "role": "assistant",
            "content": "Xin lỗi, mình chưa nhận được câu hỏi chính xác. Bạn muốn biết Fixago có dịch vụ gì không?",
        }
    ]
    messages = history + [{"role": "user", "content": "co"}]
    used_tools = []

    answer = run_legacy_fast_path("co", history, messages, used_tools)

    assert "Điện" in answer
    assert used_tools == ["Tool [Backend API]: GET /services/groups"]


def test_tool_answer_get_services_deterministic(monkeypatch):
    """get_services now uses format_services_direct (no LLM) — output is deterministic."""
    from core.orchestrator import execute_tool
    from tools.handlers import FetchResult

    services = [
        {"name": "Kiểm tra điện test-cache", "unitPrice": 150000, "estimatedTime": 30},
    ]

    def fake_fetch_raw_services(search):
        return FetchResult(ok=True, data=services)

    monkeypatch.setattr("core.orchestrator.fetch_raw_services", fake_fetch_raw_services)

    messages = [{"role": "system", "content": "system"}, {"role": "user", "content": "gia sua dien the nao"}]

    first = execute_tool('CALL_TOOL: get_services(search="điện")', messages, [])
    second = execute_tool('CALL_TOOL: get_services(search="điện")', messages, [])

    # Deterministic — same input always gives same output
    assert first == second
    # Contains price data
    assert "150" in first or "VNĐ" in first or "Kiểm tra" in first
