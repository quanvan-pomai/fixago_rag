import os
os.environ.setdefault("FIXAGO_TEST_MODE", "1")

from core.orchestrator import run_legacy_fast_path


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
