"""Contextual chunk headers (Anthropic-style Contextual Retrieval).

For each chunk we ask the LLM for one short sentence situating it within the
document. That sentence is PREPENDED to the text we embed (so an isolated chunk
carries document/section context and retrieves better) — but the original text
is still what we store and show in citations.

Cost is bounded by conditioning on the (already generated) title + summary
rather than the whole document. Full-document context with provider prompt
caching is a future upgrade. Calls run in a small thread pool and fail open:
a chunk whose header call fails is simply embedded without a header.
"""

from __future__ import annotations

import logging
import re
from concurrent.futures import ThreadPoolExecutor

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from app.core.config import get_settings
from app.modules.settings.service import get_llm_api_key, get_llm_chat_model

logger = logging.getLogger(__name__)

_MAX_WORKERS = 6           # parallel header calls per document
_CHUNK_SNIPPET_CHARS = 1200  # cap excerpt sent to the LLM
_MAX_HEADER_CHARS = 240

CONTEXT_PROMPT = """You situate an excerpt within its source policy document.
Given the document title, summary, and an excerpt, write ONE short sentence
(max 25 words) naming the specific topic/section this excerpt covers and how it
fits the document. Output only that sentence, no preamble, no quotes.

Document title: {title}
Document summary: {summary}

Excerpt:
{chunk}
"""


def _sanitize(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip().strip('"').strip()
    return cleaned[:_MAX_HEADER_CHARS]


def build_contextual_headers(
    chunks: list[dict],
    *,
    title: str | None,
    summary: str | None,
    model: str | None = None,
) -> list[str]:
    """One situating sentence per chunk; '' where unavailable (fail-open)."""
    api_key, _ = get_llm_api_key()
    if not api_key or not chunks:
        return ["" for _ in chunks]

    selected_model = model or get_llm_chat_model()[0]
    prompt = ChatPromptTemplate.from_messages([("system", CONTEXT_PROMPT)])
    llm = ChatOpenAI(
        api_key=api_key,
        base_url=get_settings().llm_base_url,
        model=selected_model,
        temperature=0,
        extra_body={"thinking": {"type": "disabled"}},
    )
    chain = prompt | llm | StrOutputParser()
    doc_title = title or "Untitled document"
    doc_summary = summary or "(no summary available)"

    def _one(chunk: dict) -> str:
        try:
            raw = chain.invoke(
                {
                    "title": doc_title,
                    "summary": doc_summary,
                    "chunk": chunk["text"][:_CHUNK_SNIPPET_CHARS],
                }
            )
            return _sanitize(raw)
        except Exception as exc:
            logger.warning("Contextual header failed for a chunk: %s", exc)
            return ""

    with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as pool:
        return list(pool.map(_one, chunks))
