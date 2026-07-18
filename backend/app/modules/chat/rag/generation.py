from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_openai import ChatOpenAI

from app.core.config import get_settings
from app.core.llm_providers import get_provider_config
from app.modules.chat.rag.prompts import CITATION_INSTRUCTION, ResponseMode, get_system_prompt
from app.modules.settings.service import get_llm_api_key, get_llm_chat_model, get_llm_provider


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


def generate_answer(
    question: str,
    context: str,
    model: str | None = None,
    response_mode: ResponseMode = "researcher",
    history: list[dict] | None = None,
    citations: list[dict] | None = None,
) -> str:
    api_key, _ = get_llm_api_key()
    if not api_key:
        raise ValueError("LLM_API_KEY is not configured.")

    if not context:
        raise ValueError("No extractable text was found in the selected PDFs.")

    provider = get_llm_provider()
    config = get_provider_config(provider)

    citation_instruction = _build_citation_instruction(citations or [])
    system_prompt = get_system_prompt(response_mode).format(
        context=context,
        citation_instruction=citation_instruction,
    )

    # Build the message list: system → history turns → current question.
    # History is a list of {"role": "user"|"assistant", "content": str} dicts.
    messages: list = [SystemMessage(content=system_prompt)]
    for msg in (history or []):
        if msg.get("role") == "user":
            messages.append(HumanMessage(content=msg["content"]))
        elif msg.get("role") == "assistant":
            messages.append(AIMessage(content=msg["content"]))
    messages.append(HumanMessage(content=question))

    base_url = config["base_url"] or get_settings().llm_base_url
    selected_model = model or get_llm_chat_model()[0] or config["default_model"]

    llm = ChatOpenAI(
        api_key=api_key,
        base_url=base_url,
        model=selected_model,
        temperature=0,
        # Provider-specific fields (e.g. DeepSeek's thinking toggle).
        # Empty dict for providers that don't need extra fields.
        extra_body=config["extra_body"],
    )

    return StrOutputParser().invoke(llm.invoke(messages))
