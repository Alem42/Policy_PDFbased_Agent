from __future__ import annotations

import json
import logging
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
from app.modules.settings.service import get_llm_api_key, get_llm_chat_model, get_llm_provider

logger = logging.getLogger(__name__)

REASON_LLM_JUDGED_INSUFFICIENT = (
    "The retrieved excerpts are similar in wording but don't actually contain "
    "information that answers your question."
)


def format_context(pages: list[dict]) -> tuple[str, bool]:
    sections: list[str] = []
    used_characters = 0
    truncated = False

    for i, page in enumerate(pages):
        text = page["text"]
        if not text:
            continue

        # Number each excerpt so the LLM can place [N] citation markers that map
        # to the citations list built in retrieve_context_node (same order).
        page_num = page.get("page") or page.get("page_start") or "?"
        section = f"[{i + 1}] {page['file']}, page {page_num}\n{text}"
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
    """Build the numbered source list injected into the system prompt."""
    if not citations:
        return ""
    lines = []
    for i, c in enumerate(citations, 1):
        page_str = f", page {c['page']}" if c.get("page") else ""
        lines.append(f"[{i}] {c.get('title', 'Unknown document')}{page_str}")
    return CITATION_INSTRUCTION.format(source_list="\n".join(lines))


def _build_messages(
    system_prompt: str,
    history: list[dict] | None,
    question: str,
) -> list:
    # Build the message list: system → history turns → current question.
    # History is a list of {"role": "user"|"assistant", "content": str} dicts.
    messages: list = [SystemMessage(content=system_prompt)]
    for msg in history or []:
        if msg.get("role") == "user":
            messages.append(HumanMessage(content=msg["content"]))
        elif msg.get("role") == "assistant":
            messages.append(AIMessage(content=msg["content"]))
    messages.append(HumanMessage(content=question))
    return messages


def resolve_generation_target(model: str | None) -> tuple[str, str, dict]:
    """Resolve (provider, selected_model, provider_config) for a chat request.

    `model` may carry an explicit "<provider>/<model-id>" prefix chosen
    per-message from the chat UI; otherwise falls back to the admin-configured
    default provider/model. Shared by generate_answer and
    generate_answer_streaming so both agree on which model ultimately answers,
    and by the /chat/stream router so it knows what to persist/report before
    generation has actually produced anything.
    """
    default_provider = get_llm_provider()
    provider, requested_model = resolve_provider_and_model(model, default_provider)
    config = get_provider_config(provider)

    # The global "default chat model" override only applies when no explicit
    # per-message provider was requested — it wouldn't make sense to apply an
    # e.g. DeepSeek model override to a message that explicitly asked for OpenAI.
    if provider == default_provider:
        selected_model = requested_model or get_llm_chat_model()[0] or config["default_model"]
    else:
        selected_model = requested_model or config["default_model"]
    if not selected_model:
        raise ValueError(f"No model specified for provider '{provider}'.")

    return provider, selected_model, config


def _parse_judge_verdict(raw: str) -> tuple[bool, str | None]:
    """Parse the evidence-judge LLM's verdict, tolerating minor formatting slop
    (e.g. a ```json ... ``` fence some models add despite being told not to).
    """
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text[4:] if text.lower().startswith("json") else text
        text = text.strip()
    try:
        data = json.loads(text)
        sufficient = bool(data.get("sufficient", True))
        if sufficient:
            return True, None
        return False, (data.get("reason") or None) or REASON_LLM_JUDGED_INSUFFICIENT
    except (json.JSONDecodeError, AttributeError, TypeError):
        # Fail open on unparseable output -- don't block a user over a
        # formatting slip in this secondary check; trust the cheap gate.
        logger.warning("Evidence-judge LLM returned unparseable output: %r", raw[:200])
        return True, None


def check_evidence_sufficiency_llm(
    question: str,
    citations: list[dict],
    model: str | None = None,
) -> tuple[bool, str | None]:
    """Second, semantic evidence gate -- runs only after the cheap vector-
    distance/reranker threshold (see rag/evidence.py) already passed.

    That cheap gate only measures embedding closeness, which can be
    deceptively high for topically unrelated policy-language text (e.g. a
    question about Russian policy can score "close enough" against documents
    about Chile's data centers or financial-AI principles, simply because
    they share generic policy vocabulary). This asks the LLM itself, using
    only short excerpt summaries (not the full context) so the call stays
    small and fast -- this is a non-streaming, short-output request that
    gates whether the real (streamed) generation call happens at all.
    """
    if not citations:
        return True, None  # Nothing to judge against; trust the cheap gate.

    try:
        provider, selected_model, config = resolve_generation_target(model)
        api_key, _ = get_llm_api_key(provider)
    except ValueError:
        return True, None  # Fail open -- don't block over a config problem.
    if not api_key:
        return True, None

    excerpt_lines = []
    for i, c in enumerate(citations[:8]):
        page = f", page {c['page']}" if c.get("page") else ""
        quote = (c.get("quote") or "").strip().replace("\n", " ")[:200]
        excerpt_lines.append(f"[{i + 1}] {c.get('title', 'Unknown document')}{page}: {quote}")
    excerpt_summary = "\n".join(excerpt_lines)

    judge_prompt = (
        "You are a strict relevance judge for a document Q&A system. Given a "
        "user question and short excerpts retrieved by a vector search, decide "
        "whether the excerpts actually contain information that can answer the "
        "question -- not merely text that is topically or vocabulary-similar.\n\n"
        f"Question: {question}\n\n"
        f"Retrieved excerpts:\n{excerpt_summary}\n\n"
        "Respond with ONLY a compact JSON object and nothing else: "
        '{"sufficient": true or false, "reason": "one short sentence if false, else null"}'
    )

    base_url = config["base_url"] or get_settings().llm_base_url
    llm = ChatOpenAI(
        api_key=api_key,
        base_url=base_url,
        model=selected_model,
        temperature=0,
        extra_body=config["extra_body"],
    )
    try:
        raw = StrOutputParser().invoke(llm.invoke([HumanMessage(content=judge_prompt)]))
    except Exception:
        # Fail open -- an infra hiccup in this secondary check shouldn't block
        # the user from getting an answer the cheap gate already approved.
        logger.exception("Evidence-judge LLM call failed; falling back to the cheap gate.")
        return True, None

    return _parse_judge_verdict(raw)


def generate_answer(
    question: str,
    context: str,
    model: str | None = None,
    response_mode: ResponseMode = "researcher",
    history: list[dict] | None = None,
    citations: list[dict] | None = None,
    answer_mode: AnswerMode = "analysis",
) -> tuple[str, str]:
    """Generate the answer text. Returns (answer, resolved_model) where
    resolved_model is "<provider>/<model-id>", persisted per-message so chat
    history can show which model actually answered.
    """
    provider, selected_model, config = resolve_generation_target(model)

    api_key, _ = get_llm_api_key(provider)
    if not api_key:
        raise ValueError(f"No API key is configured for provider '{provider}'.")

    if not context and answer_mode == "analysis":
        raise ValueError("No extractable text was found in the selected PDFs.")

    citation_instruction = _build_citation_instruction(citations or [])
    system_prompt = get_system_prompt(response_mode, answer_mode).format(
        context=context or "(No relevant excerpts were retrieved from the selected documents.)",
        citation_instruction=citation_instruction,
    )
    messages = _build_messages(system_prompt, history, question)

    base_url = config["base_url"] or get_settings().llm_base_url

    llm = ChatOpenAI(
        api_key=api_key,
        base_url=base_url,
        model=selected_model,
        temperature=0,
        # Provider-specific fields (e.g. DeepSeek's thinking toggle).
        # Empty dict for providers that don't need extra fields.
        extra_body=config["extra_body"],
    )

    answer = StrOutputParser().invoke(llm.invoke(messages))
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
    """Async generator that yields raw text chunks from the LLM as they arrive.

    Supports the same per-message provider/model selection as generate_answer
    (see resolve_generation_target) — the caller (chat_stream router) resolves
    the target once up front to know what to persist/report, and this
    function resolves it again (cheap, deterministic) to build its own client.
    """
    provider, selected_model, config = resolve_generation_target(model)

    api_key, _ = get_llm_api_key(provider)
    if not api_key:
        raise ValueError(f"No API key is configured for provider '{provider}'.")

    if not context and answer_mode == "analysis":
        raise ValueError("No extractable text was found in the selected PDFs.")

    citation_instruction = _build_citation_instruction(citations or [])
    system_prompt = get_system_prompt(response_mode, answer_mode).format(
        context=context or "(No relevant excerpts were retrieved from the selected documents.)",
        citation_instruction=citation_instruction,
    )
    messages = _build_messages(system_prompt, history, question)

    base_url = config["base_url"] or get_settings().llm_base_url

    llm = ChatOpenAI(
        api_key=api_key,
        base_url=base_url,
        model=selected_model,
        temperature=0,
        extra_body=config["extra_body"],
    )

    async for chunk in llm.astream(messages):
        if chunk.content:
            yield str(chunk.content)
