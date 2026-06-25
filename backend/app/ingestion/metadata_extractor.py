from __future__ import annotations

import json
import re
from datetime import date

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from app.core.config import get_settings
from app.ingestion.taxonomy import POLICY_TAXONOMY, normalise_policy_areas
from app.services.settings_service import get_llm_api_key, get_llm_chat_model

METADATA_PROMPT = """You extract structured metadata from policy documents.
Return only valid JSON. Do not wrap it in markdown.
All human-readable metadata values must be written in English, even when the
document excerpt is written in another language. Keep names concise and
normalised so the same concept receives the same English label across files.

Use this schema:
{{
  "title": string | null,
  "summary": string | null,
  "source_type": string | null,
  "source_organisation": string | null,
  "country_region": string | null,
  "language": string | null,
  "year": number | null,
  "publication_date": string | null,
  "policy_areas": string[],
  "keywords": string[],
  "stakeholders": string[],
  "implementation_risks": string[]
}}

Rules:
- "language" must be the main document language in English, for example
  "English", "Spanish", "French", or "Bulgarian".
- "country_region", "source_type", "source_organisation", "stakeholders",
  "implementation_risks", "policy_areas", and "keywords" must all be English labels.
- "publication_date" must use YYYY-MM-DD when known, otherwise null.
- "policy_areas" must contain 3 to 6 labels selected only from this fixed taxonomy:
  {taxonomy}
- "keywords" must contain 5 to 12 English keywords.
- Translate titles and summaries to English when needed.

Document excerpt:
{excerpt}
"""


def _extract_json(text: str) -> dict:
    clean = text.strip()
    if clean.startswith("```"):
        clean = re.sub(r"^```(?:json)?", "", clean).strip()
        clean = re.sub(r"```$", "", clean).strip()

    try:
        value = json.loads(clean)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", clean, flags=re.DOTALL)
        if not match:
            raise
        value = json.loads(match.group(0))

    return value if isinstance(value, dict) else {}


def _clean_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _clean_date(value: object) -> str | None:
    if not value:
        return None
    clean = str(value).strip()
    try:
        date.fromisoformat(clean)
    except ValueError:
        return None
    return clean


def infer_language(text: str) -> str | None:
    sample = text[:20_000].lower()
    if not sample.strip():
        return None
    if re.search(r"[\u0400-\u04ff]", sample):
        return "Bulgarian"
    if any(word in sample for word in ("transformaci", "polit", "digitalizaci")):
        return "Spanish"
    if any(word in sample for word in ("strat", "numer", "gouvernance")):
        return "French"
    return "English"


def normalise_metadata(metadata: dict, filename: str) -> dict:
    year = metadata.get("year")
    try:
        year = int(year) if year is not None else None
    except (TypeError, ValueError):
        year = None

    return {
        "title": metadata.get("title") or filename,
        "summary": metadata.get("summary"),
        "source_type": metadata.get("source_type"),
        "source_organisation": metadata.get("source_organisation"),
        "country_region": metadata.get("country_region"),
        "language": metadata.get("language"),
        "year": year,
        "publication_date": _clean_date(metadata.get("publication_date")),
        "policy_areas": normalise_policy_areas(_clean_list(metadata.get("policy_areas"))),
        "keywords": _clean_list(metadata.get("keywords")),
        "stakeholders": _clean_list(metadata.get("stakeholders")),
        "implementation_risks": _clean_list(metadata.get("implementation_risks")),
        "metadata_json": metadata,
    }


def generate_document_metadata(
    filename: str,
    pages: list[dict],
    model: str | None = None,
) -> tuple[dict, str | None]:
    # Metadata uses a bounded excerpt instead of the full PDF to keep ingestion
    # predictable for large documents and avoid excessive model context usage.
    excerpt_parts: list[str] = []
    used_characters = 0
    for page in pages:
        text = page.get("text", "")
        if not text:
            continue
        section = f"[Page {page['page']}]\n{text}\n"
        remaining = 16_000 - used_characters
        if remaining <= 0:
            break
        excerpt_parts.append(section[:remaining])
        used_characters += len(section)

    excerpt = "\n".join(excerpt_parts).strip()
    if not excerpt:
        return normalise_metadata({}, filename), None

    api_key, _ = get_llm_api_key()
    if not api_key:
        metadata = normalise_metadata({}, filename)
        metadata["language"] = infer_language(excerpt)
        return metadata, None

    selected_model = model or get_llm_chat_model()[0]
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", METADATA_PROMPT),
            ("human", "Extract metadata for {filename}."),
        ]
    )
    llm = ChatOpenAI(
        api_key=api_key,
        base_url=get_settings().llm_base_url,
        model=selected_model,
        temperature=0,
        extra_body={"thinking": {"type": "disabled"}},
    )
    chain = prompt | llm | StrOutputParser()
    response = chain.invoke(
        {
            "excerpt": excerpt,
            "filename": filename,
            "taxonomy": ", ".join(POLICY_TAXONOMY),
        }
    )
    metadata = normalise_metadata(_extract_json(response), filename)
    if not metadata.get("language"):
        metadata["language"] = infer_language(excerpt)
    return metadata, selected_model
