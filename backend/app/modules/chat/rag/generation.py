from __future__ import annotations

from collections.abc import AsyncGenerator

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_openai import ChatOpenAI

from app.core.config import get_settings
from app.core.llm_providers import get_provider_config, resolve_provider_and_model
from app.modules.chat.rag.prompts import (
    CITATION_INSTRUCTION,
    AnswerMode,
    ResponseMode,
    get_system_prompt,
)
from app.modules.settings.service import (
    get_llm_chat_model,
    get_llm_provider,
    get_provider_api_key,
)


def format_context(pages: list[dict]) -> tuple[str, bool]:
    sections: list[str] = []
    used_characters = 0
    truncated = False

    for index, page in enumerate(pages):
        text = page["text"]
        if not text:
            continue
        page_num = page.get("page") or page.get("page_start") or "?"
        section = f"[{index + 1}] {page['file']}, page {page_num}\n{text}"
        remaining = get_settings().max_context_characters - used_characters
        if remaining <= 0:
            truncated = True
            break
        if len(section) > remaining:
            sections.append(section[:remaining])
            truncated = True
            break
        sections.append(section)
        used_characters += len(section)

    return "\n\n---\n\n".join(sections), truncated


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


def resolve_generation_target(model: str | None) -> tuple[str, str, dict]:
    default_provider = get_llm_provider()
    provider, requested_model = resolve_provider_and_model(model, default_provider)
    config = get_provider_config(provider)
    selected_model = (
        requested_model
        or (get_llm_chat_model() if provider == default_provider else None)
        or config["default_model"]
    )
    return provider, selected_model, config


def create_chat_client(
    provider: str,
    model: str,
    temperature: float = 0,
    max_tokens: int | None = None,
) -> ChatOpenAI:
    api_key = get_provider_api_key(provider)
    if not api_key:
        raise ValueError(f"No API key is configured for provider '{provider}'.")
    config = get_provider_config(provider)
    client_options = {
        "api_key": api_key,
        "base_url": config["base_url"],
        "model": model,
        "temperature": temperature,
        "extra_body": config["extra_body"],
    }
    if max_tokens is not None:
        client_options["max_tokens"] = max_tokens
    return ChatOpenAI(
        **client_options,
    )


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
    return _build_messages(system_prompt, history, question)


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
