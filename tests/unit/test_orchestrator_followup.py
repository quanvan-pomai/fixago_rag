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


def test_tool_answer_cache_uses_backend_data_hash(monkeypatch):
    from core.orchestrator import execute_tool
    from tools.handlers import FetchResult

    if hasattr(rag_engine.cache, "_store"):
        rag_engine.cache._store.clear()

    calls = {"llm": 0}
    services = [
        {"name": "Kiểm tra điện test-cache", "unitPrice": 150000, "estimatedTime": 30},
    ]

    def fake_fetch_raw_services(search):
        return FetchResult(ok=True, data=services)

    def fake_llm_chat(messages, temperature=0.15):
        calls["llm"] += 1
        assert len(messages) <= 2
        return "Dạ giá sửa điện tham khảo từ 150.000 VNĐ."

    monkeypatch.setattr("core.orchestrator.fetch_raw_services", fake_fetch_raw_services)
    monkeypatch.setattr("core.orchestrator.llm_chat", fake_llm_chat)

    messages = [{"role": "system", "content": "system"}, {"role": "user", "content": "gia sua dien the nao"}]

    first = execute_tool('CALL_TOOL: get_services(search="điện")', messages, [])
    second = execute_tool('CALL_TOOL: get_services(search="điện")', messages, [])

    assert first == second
    assert calls["llm"] == 1
