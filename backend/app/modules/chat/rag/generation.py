from __future__ import annotations

from collections.abc import AsyncGenerator

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.output_parsers import StrOutputParser

from app.core.ai.chat_models import create_chat_client, resolve_generation_target
from app.modules.chat.rag.prompts import (
    CITATION_INSTRUCTION,
    AnswerMode,
    ResponseMode,
    final_style_reminder,
    get_system_prompt,
)
from app.modules.retrieval.formatting import format_context

__all__ = ["create_chat_client", "format_context", "resolve_generation_target"]


def _build_citation_instruction(citations: list[dict]) -> str:
    if not citations:
        return ""
    lines = []
    for index, citation in enumerate(citations, 1):
        page = f", page {citation['page']}" if citation.get("page") else ""
        lines.append(
            f"[{index}] {citation.get('title', 'Unknown document')}{page}"
        )
    return CITATION_INSTRUCTION.format(source_list="\n".join(lines))


def _build_messages(
    system_prompt: str,
    history: list[dict] | None,
    question: str,
) -> list:
    messages: list = [SystemMessage(content=system_prompt)]
    for message in history or []:
        if message.get("role") == "user":
            messages.append(HumanMessage(content=message["content"]))
        elif message.get("role") == "assistant":
            messages.append(AIMessage(content=message["content"]))
    messages.append(HumanMessage(content=question))
    return messages


def _generation_messages(
    question: str,
    context: str,
    response_mode: ResponseMode,
    answer_mode: AnswerMode,
    history: list[dict] | None,
    citations: list[dict] | None,
) -> list:
    if not context and answer_mode == "analysis":
        raise ValueError("No extractable text was found in the selected PDFs.")
    system_prompt = get_system_prompt(response_mode, answer_mode).format(
        context=context
        or "(No relevant excerpts were retrieved from the selected documents.)",
        citation_instruction=_build_citation_instruction(citations or []),
    )
    # Append the style reminder to the FINAL user message: the highest-weight
    # position for DeepSeek-style models, and the strongest counter to earlier
    # answers in the history acting as in-context formatting examples.
    question = f"{question}\n\n{final_style_reminder(answer_mode)}"
    return _build_messages(
        system_prompt,
        history,
        question,
    )


def generate_answer(
    question: str,
    context: str,
    model: str | None = None,
    response_mode: ResponseMode = "researcher",
    history: list[dict] | None = None,
    citations: list[dict] | None = None,
    answer_mode: AnswerMode = "analysis",
) -> tuple[str, str]:
    provider, selected_model, _ = resolve_generation_target(model)
    messages = _generation_messages(
        question,
        context,
        response_mode,
        answer_mode,
        history,
        citations,
    )
    answer = StrOutputParser().invoke(
        create_chat_client(provider, selected_model).invoke(messages)
    )
    return answer, f"{provider}/{selected_model}"


async def generate_answer_streaming(
    question: str,
    context: str,
    model: str | None = None,
    response_mode: ResponseMode = "researcher",
    history: list[dict] | None = None,
    citations: list[dict] | None = None,
    answer_mode: AnswerMode = "analysis",
) -> AsyncGenerator[str, None]:
    provider, selected_model, _ = resolve_generation_target(model)
    messages = _generation_messages(
        question,
        context,
        response_mode,
        answer_mode,
        history,
        citations,
    )
    async for chunk in create_chat_client(provider, selected_model).astream(messages):
        if chunk.content:
            yield str(chunk.content)
