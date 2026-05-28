"""
core/context_builder.py
Unified context assembly for LLM calls.
Wraps existing prompt_builder helpers without changing the [DỮ LIỆU HỆ THỐNG] format.
"""
from dataclasses import dataclass
from typing import Iterable, List, Optional

from core.memory.memory_retriever import format_memory_block
from core.memory.memory_types import ScoredMemoryEntry
from core.policy import ResponsePolicy
from core.prompt_builder import build_system_prompt, compact_history


@dataclass
class BuiltContext:
    system_prompt: str
    messages: List[dict]     # ready to pass to llm_chat()
    temperature: float


class ContextBuilder:
    def build(
        self,
        *,
        query: str,
        history: list,
        data_block: Optional[str],
        rag_context: Optional[str],
        policy: ResponsePolicy,
        booking_state: Optional[dict] = None,
        enable_native_tool_call: bool = False,
        detected_intent: Optional[str] = None,
        catalog: str = "",
        memory_entries: Optional[Iterable[ScoredMemoryEntry]] = None,
    ) -> BuiltContext:
        """
        Assemble system prompt and message list for the LLM.

        Appends policy.llm_instruction to the system prompt when non-empty.
        Data block and RAG context are injected into the user message using the
        existing [DỮ LIỆU HỆ THỐNG] format so downstream validators keep working.
        """
        base = build_system_prompt(
            base=_load_base_prompt(),
            booking_state=booking_state or {},
            enable_native_tool_call=enable_native_tool_call,
            detected_intent=detected_intent,
            catalog=catalog,
        )

        instruction = (policy.llm_instruction or "").strip()
        system = f"{base}\n\n[HƯỚNG DẪN PHẢN HỒI]: {instruction}" if instruction else base

        compacted = compact_history(history, max_items=6)
        messages = [{"role": "system", "content": system}]
        messages.extend(compacted)

        # Assemble user message
        memory_block = format_memory_block(memory_entries or [])

        if data_block:
            user_content = (
                f"[DỮ LIỆU HỆ THỐNG — chỉ dùng thông tin này để trả lời, không bịa thêm]\n"
                f"{data_block}\n"
                f"[/DỮ LIỆU]\n\n"
            )
            if memory_block:
                user_content += f"{memory_block}\n\n"
            if rag_context:
                user_content += f"Ngữ cảnh tham khảo:\n{rag_context}\n\n"
            user_content += query
        elif rag_context:
            prefix = f"{memory_block}\n\n" if memory_block else ""
            user_content = f"{prefix}Ngữ cảnh tham khảo:\n{rag_context}\n\nCâu hỏi của khách:\n{query}"
        else:
            user_content = f"{memory_block}\n\n{query}" if memory_block else query

        messages.append({"role": "user", "content": user_content})

        return BuiltContext(
            system_prompt=system,
            messages=messages,
            temperature=policy.temperature,
        )


def _load_base_prompt() -> str:
    from core.prompt_builder import load_system_prompt
    return load_system_prompt()
