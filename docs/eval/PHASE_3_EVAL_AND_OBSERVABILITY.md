# Phase 3 — Evaluation and Observability

## 1. Running Tests

All tests are self-contained — no real backend API or LLM required.

```bash
# All tests (unit + conversation scenarios)
FIXAGO_TEST_MODE=1 pytest tests/unit/ tests/eval/ -v

# Unit tests only (fastest)
FIXAGO_TEST_MODE=1 pytest tests/unit/ -v

# Conversation scenarios only
FIXAGO_TEST_MODE=1 pytest tests/eval/ -v

# Single test file
FIXAGO_TEST_MODE=1 pytest tests/unit/test_intent_router.py -v
```

`FIXAGO_TEST_MODE=1` is also set automatically by `tests/conftest.py` when running pytest from the
project root, so the explicit env var is optional when using `pytest` directly.

---

## 2. Adding a New Conversation Scenario

Copy this template into `tests/eval/test_conversation_scenarios.py`:

```python
def test_MY_scenario(app_client):
    sid = "test-MY-" + uuid.uuid4().hex[:6]
    sc, data = _q(app_client, "Your query here", sid)
    assert sc == 200
    assert data["session_id"] == sid
    resp = data["response"].lower()
    # Assert key tokens appear in response
    assert "expected_word" in resp
    # Assert no leaks
    assert "CALL_TOOL" not in data["response"]
    assert "[DỮ LIỆU HỆ THỐNG" not in data["response"]
```

For multi-turn booking scenarios:
```python
def test_MY_booking(app_client):
    sid = "test-MY-" + uuid.uuid4().hex[:6]
    _q(app_client, "Đặt thợ sửa điện", sid)                           # turn 1
    _q(app_client, "Tên X, SĐT 0912345678, địa chỉ ABC", sid)         # turn 2
    sc, data = _q(app_client, "Xác nhận", sid)                         # turn 3
    assert any("Tạo đơn" in str(t) for t in data.get("tool_calls", []))
```

To use a backend error scenario, create a separate function and override the patch:
```python
def test_MY_error_scenario():
    from server import app
    app.config["TESTING"] = True
    with patch("tools.handlers.fetch_raw_groups", return_value=MOCK_ERR):
        client = app.test_client()
        sc, data = _q(client, "Fixago có dịch vụ gì?")
    assert "chưa lấy được" in data["response"]
```

---

## 3. Path Taxonomy

Every request records a `path` in the trace log. The possible values are:

| Path | Meaning |
|------|---------|
| `guardrail` | Prompt injection detected — request blocked before any processing |
| `static_fallback` | One of the fast-path static handlers fired (hours/safety/off-topic/booking) |
| `cache_hit` | Response served from the response cache (use_cache=True) |
| `legacy_tool` | Went through the full legacy orchestration pipeline (tool + LLM) |
| `native_tool` | Went through native function-calling pipeline (ENABLE_NATIVE_TOOL_CALL=1) |
| `error` | Unhandled exception in the request handler |

---

## 4. Trace Log Schema

Every request emits one line at INFO level from the `fixago.trace` logger:

```
trace id=<12-char-hex> sess=<8-char-prefix> path=<path> intent=<intent|-> svc=<svc|->
      tools=<count> cache=<True|False> backend_ok=<True|False> llm=<True|False>
      valid=<ok|fixed|blocked> lat=<ms>ms q=<query-preview>
```

Fields:

| Field | Description |
|-------|-------------|
| `id` | 12-character hex trace ID, unique per request |
| `sess` | First 8 characters of session_id |
| `path` | See Path Taxonomy above |
| `intent` | Detected CALL_TOOL string (e.g. `CALL_TOOL: get_services(search="điện")`) or `-` |
| `svc` | Normalized service category or `-` |
| `tools` | Number of backend tool calls made |
| `cache` | `True` if served from response cache |
| `backend_ok` | `False` if any backend fetch failed |
| `llm` | `True` if the LLM was called |
| `valid` | `ok` = response passed validation; `fixed` = validator rewrote it; `blocked` = blocked |
| `lat` | End-to-end request latency in milliseconds |
| `q` | First 80 characters of query, with phone numbers masked |

Tool audit events emit on `fixago.tool_audit`:
```
tool_audit trace=<id> tool=<name> ok=<True|False> items=<n> cache=<True|False>
           lat=<ms>ms err=<error_type|->
```

---

## 5. PII Policy — What Must Never Be Logged

The following MUST NOT appear in any log output:

- **Full phone numbers** — masked to `0912****678` format by `mask_phone()`
- **Full addresses** — never log address fields; use `[address_redacted]` if needed
- **Customer names** — use `[name_redacted]` if needed
- **System prompt content** — never log the system prompt text
- **Full backend API payload** — only logged at DEBUG level, never INFO
- **Session booking_state dict** — never log the raw booking state

The `query_preview` field in the trace log applies `mask_phone()` and limits to 80 characters.

To grep for potential PII leaks in logs:
```bash
grep -E "(09[0-9]{8}|0[3-9][0-9]{8})" rag.log | head -5
```
If this returns anything other than masked forms like `091****678`, investigate.

---

## 6. Known Limitations

1. **Mock LLM ≠ real Qwen 3B** — The `_llm_mock` function in conversation tests returns
   deterministic strings keyed on data block tokens. Real model responses vary. The tests
   verify the pipeline structure (routing, injection, session, leaks) but not model quality.

2. **Booking flow in tests uses extractor** — The booking extractor (`booking/extractor.py`)
   runs normally in tests. Its regex patterns are stable but occasionally wrong on edge-case
   phone formats — if a booking test fails, check phone normalization first.

3. **Cache scenarios** — Tests that simulate cache hits use `FakeCacheStore` (in-memory dict).
   Real cache TTL, eviction, and serialization behavior is only tested in the live server.

4. **No-accent routing** — `detect_tool_intent` for no-accent queries depends on
   `normalize_noaccent()` substitutions. If a new no-accent synonym is needed, add it to
   `_NOACCENT_MAP` in `core/intent_router.py` and add a test in `test_intent_router.py`.

5. **ENABLE_NATIVE_TOOL_CALL path** — Conversation tests do not test the native function-calling
   path (`ENABLE_NATIVE_TOOL_CALL=1`) because it requires cheese-server `--jinja` mode. The
   `run_native_tool_path` logic is unit-tested via `test_guardrails.py` static_fallback checks.
