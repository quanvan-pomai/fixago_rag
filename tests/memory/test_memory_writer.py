"""Pomai Memory writer tests."""
from core.memory.memory_store import MemoryStore
from core.memory.memory_types import MemoryScope, MemoryType
from core.memory.memory_writer import MemoryWriter


class TinyCache:
    def __init__(self):
        self.data = {}

    def get(self, key):
        return self.data.get(key)

    def set(self, key, value, ttl_ms=0):
        self.data[key] = value if isinstance(value, bytes) else str(value).encode()
        return True


def test_update_after_turn_stores_preference():
    store = MemoryStore(cache=TinyCache())
    writer = MemoryWriter(store=store)
    count = writer.update_after_turn(query="Trả lời ngắn gọn thôi", response="Dạ", session_id="s1")
    entries = store.list(scopes=[MemoryScope.USER], session_id="s1")
    assert count == 1
    assert entries[0].type == MemoryType.PREFERENCE


def test_update_after_turn_does_not_store_contact_long_term():
    store = MemoryStore(cache=TinyCache())
    writer = MemoryWriter(store=store)
    count = writer.update_after_turn(
        query="Tôi tên Nam, số 0901234567, địa chỉ 12 Nguyễn Trãi",
        response="Bạn xác nhận nhé?",
        session_id="s1",
    )
    assert count == 0
    assert store.list(scopes=[MemoryScope.USER]) == []


def test_tool_result_gets_ttl_and_hash():
    store = MemoryStore(cache=TinyCache())
    writer = MemoryWriter(store=store)
    count = writer.update_after_turn(
        query="Sửa điện bao nhiêu?",
        response="Giá tham khảo 150.000 VNĐ",
        tool_calls=['Tool [Backend API]: GET /services?search="điện"'],
        session_id="s1",
    )
    entries = store.list(scopes=[MemoryScope.TOOL], session_id="s1")
    assert count == 1
    assert entries[0].type == MemoryType.TOOL_RESULT
    assert entries[0].ttl_ms and entries[0].ttl_ms > 0
    assert entries[0].data_hash


def test_session_summary_masks_pii():
    store = MemoryStore(cache=TinyCache())
    writer = MemoryWriter(store=store)
    history = [{"role": "user", "content": f"Turn {i} 0901234567"} for i in range(8)]
    count = writer.update_after_turn(
        query="ok",
        response="done",
        session={"history": history},
        session_id="s1",
    )
    summaries = store.list(scopes=[MemoryScope.SEMANTIC], session_id="s1")
    assert count == 1
    assert summaries
    assert "0901234567" not in summaries[0].content

