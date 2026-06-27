from __future__ import annotations

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from app.core.config import get_settings
from app.services.settings_service import get_llm_api_key, get_llm_chat_model

SYSTEM_PROMPT = """You are a careful PDF question-answering assistant.
Answer the user's question using only the supplied PDF text.
If the PDF text does not contain enough information, say that you cannot determine
the answer from the uploaded PDFs.
Reply in the same language as the user's question.
When useful, mention the source file and page number.

PDF text:
{context}
"""


def format_context(pages: list[dict]) -> tuple[str, bool]:
    sections: list[str] = []
    used_characters = 0
    truncated = False

    for page in pages:
        text = page["text"]
        if not text:
            continue

        section = f"[Source: {page['file']}, page {page['page']}]\n{text}"
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


def generate_answer(
    question: str,
    context: str,
    model: str | None = None,
) -> str:
    api_key, _ = get_llm_api_key()
    if not api_key:
        raise ValueError("LLM_API_KEY is not configured.")

    if not context:
        raise ValueError("No extractable text was found in the selected PDFs.")

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", SYSTEM_PROMPT),
            ("human", "{question}"),
        ]
    )
    llm = ChatOpenAI(
        api_key=api_key,
        base_url=get_settings().llm_base_url,
        model=model or get_llm_chat_model()[0],
        temperature=0,
        extra_body={"thinking": {"type": "disabled"}},
    )
    chain = prompt | llm | StrOutputParser()
    return chain.invoke({"question": question, "context": context})
