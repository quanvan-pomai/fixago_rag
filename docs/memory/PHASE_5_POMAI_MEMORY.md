# Phase 5 — Pomai Memory

Pomai Memory stores source-aware knowledge state, not raw answer text. It is a bounded layer on top of the existing PomaiCache key-value store and is used only when policy allows it.

## Memory Layers

| Layer | Scope | TTL | Purpose |
|---|---|---:|---|
| Session Memory | `session` | 2 hours | Active flow state, current booking state, recent summary |
| User Preference Memory | `user` | 180 days | Harmless style/language preferences |
| Business Knowledge Memory | `business` | 90 days | Trusted Fixago facts with source and timestamp |
| Tool Result Cache | `tool` | 30 minutes | Short summaries of groups/services/promotions results |
| Semantic Conversation Summary | `semantic` | 7 days | Useful decisions/tasks/summaries without raw chat logs |

Booking contact data remains in `core/session.py` only. Phone numbers, full addresses, and names are not written to long-term memory.

## Schema

Every `MemoryEntry` has:

- `id`
- `scope`
- `type`
- `content`
- `normalized_content`
- `source`
- `confidence`
- `created_at`
- `updated_at`
- `expires_at`
- `ttl_ms`
- `tags`
- optional `user_id`, `session_id`, `trace_id`, `data_hash`
- `pii_level`
- `allowed_for_prompt`

Entries without source, confidence, and TTL are rejected by policy-level writers.

## PII Rules

Detected PII:

- phone numbers
- emails
- addresses
- booking names
- tokens/API keys

Rules:

- High PII is never injected into prompts.
- Phone/address/name are session-only for booking flow.
- Tokens and secrets are rejected.
- Summaries are masked before write.
- Trace logs include only memory ids/counts/types/scopes, not raw memory content.

Mask examples:

- phone: `09******12`
- address: `[address_redacted]`
- name: `[name_redacted]`
- secret: `[secret_redacted]`

## Retrieval Ranking

Ranking uses:

```text
score = relevance + recency + confidence + scope_weight - pii_penalty - staleness_penalty
```

Default limits:

- `MEMORY_MAX_PROMPT_ENTRIES=5`
- `MEMORY_MAX_PROMPT_TOKENS=350`

Tool memory never overrides fresh backend data. It is fallback context only.

## Context Injection

Memory is injected after tool data and before RAG context:

```text
[NGỮ CẢNH BỘ NHỚ — dùng như thông tin phụ, không bịa thêm]
- User prefers concise, direct technical answers.
- Current project decision: TensorFlow is native core of dm; DM_Block is optional.
[/NGỮ CẢNH BỘ NHỚ]
```

Memory is context, not instruction. The model must not treat memory as higher priority than tool/backend data.

## Write Policy

Stored:

- explicit user preferences
- trusted business facts
- project decisions
- unresolved tasks
- session summaries
- tool result summaries with TTL

Rejected:

- prompt injection
- unsafe requests
- raw LLM output as fact
- low-confidence guesses
- one-off random chat
- long-term phone/address/name
- passwords/secrets/tokens

## Debug Endpoint

`GET /api/v1/memory/debug?session_id=...`

Enabled only when:

- `FIXAGO_DEBUG=1`
- `X-Admin-Token` matches `FIXAGO_ADMIN_TOKEN`

The endpoint returns masked metadata and previews only. It does not expose raw PII.

## Adding A Memory Type

1. Add or reuse a `MemoryType` in `core/memory/memory_types.py`.
2. Add a write rule in `MemoryWritePolicy`.
3. Add retrieval behavior in `MemoryRetrievalPolicy`.
4. Add tests for write, retrieval, PII, and context injection.

