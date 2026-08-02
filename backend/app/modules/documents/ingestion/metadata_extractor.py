from __future__ import annotations

import json
import re
from datetime import date

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

from app.core.ai.chat_models import (
    create_chat_client,
    resolve_generation_target,
)
from app.modules.documents.ingestion.language_detect import detect_language
from app.modules.documents.ingestion.policy_matcher import match_policy_areas
from app.modules.documents.taxonomy_service import get_leaf_labels, get_taxonomy_tree

# Excerpt budget split across the document. Head is weighted heaviest because
# policy docs front-load the important metadata (title, country, main themes);
# the mid/tail slices surface secondary policy areas the head never mentions.
EXCERPT_HEAD_CHARS = 9_000
EXCERPT_MID_CHARS = 5_000
EXCERPT_TAIL_CHARS = 2_000

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
- "policy_areas" must contain 3 to 6 SUBCATEGORY labels chosen only from the
  taxonomy below. Pick the leaf subcategory wording (right-hand side), not the
  parent. Copy the wording exactly.
  Taxonomy (Parent: subcategories):
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


def _format_taxonomy(tree: list[dict]) -> str:
    """Render the tree as 'Parent: childA, childB' lines for the prompt."""
    return "\n  ".join(f"{g['parent']}: {', '.join(g['children'])}" for g in tree)


def infer_language(text: str) -> str | None:
    """Crude keyword fallback, used only when lingua returns nothing."""
    sample = text[:20_000].lower()
    if not sample.strip():
        return None
    if re.search("[Ѐ-ӿ]", sample):  # Cyrillic block
        return "Bulgarian"
    if any(word in sample for word in ("transformaci", "polit", "digitalizaci")):
        return "Spanish"
    if any(word in sample for word in ("strat", "numer", "gouvernance")):
        return "French"
    return "English"


def _resolve_language(metadata_language: str | None, excerpt: str) -> str | None:
    """LLM value -> lingua detection -> crude heuristic."""
    if metadata_language:
        return metadata_language
    return detect_language(excerpt) or infer_language(excerpt)


def normalise_metadata(metadata: dict, filename: str, leaf_labels: list[str] | None = None) -> dict:
    year = metadata.get("year")
    try:
        year = int(year) if year is not None else None
    except (TypeError, ValueError):
        year = None

    labels = leaf_labels if leaf_labels is not None else get_leaf_labels()
    return {
        "title": metadata.get("title") or filename,
        "summary": metadata.get("summary"),
        "source_type": metadata.get("source_type"),
        "source_organisation": metadata.get("source_organisation"),
        "country_region": metadata.get("country_region"),
        "language": metadata.get("language"),
        "year": year,
        "publication_date": _clean_date(metadata.get("publication_date")),
        # 方案①: snap free-form labels onto canonical taxonomy leaves via embeddings.
        "policy_areas": match_policy_areas(_clean_list(metadata.get("policy_areas")), labels),
        "keywords": _clean_list(metadata.get("keywords")),
        "stakeholders": _clean_list(metadata.get("stakeholders")),
        "implementation_risks": _clean_list(metadata.get("implementation_risks")),
        "metadata_json": metadata,
    }


def _build_excerpt(pages: list[dict]) -> str:
    """Weighted head/mid/tail sample so secondary areas aren't missed."""
    full = "\n".join(
        f"[Page {page['page']}]\n{page.get('text', '')}\n" for page in pages if page.get("text")
    ).strip()

    budget = EXCERPT_HEAD_CHARS + EXCERPT_MID_CHARS + EXCERPT_TAIL_CHARS
    if len(full) <= budget:
        return full

    head = full[:EXCERPT_HEAD_CHARS]
    mid_start = max(EXCERPT_HEAD_CHARS, (len(full) - EXCERPT_MID_CHARS) // 2)
    mid = full[mid_start : mid_start + EXCERPT_MID_CHARS]
    tail = full[-EXCERPT_TAIL_CHARS:]
    return "\n[...]\n".join([head, mid, tail])


def generate_document_metadata(
    filename: str,
    pages: list[dict],
    model: str | None = None,
) -> tuple[dict, str | None]:
    excerpt = _build_excerpt(pages)
    tree = get_taxonomy_tree()
    leaf_labels = [child for group in tree for child in group["children"]]

    if not excerpt:
        return normalise_metadata({}, filename, leaf_labels), None

    try:
        provider, selected_model, _ = resolve_generation_target(model)
        llm = create_chat_client(provider, selected_model)
    except ValueError:
        metadata = normalise_metadata({}, filename, leaf_labels)
        metadata["language"] = _resolve_language(None, excerpt)
        return metadata, None

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", METADATA_PROMPT),
            ("human", "Extract metadata for {filename}."),
        ]
    )
    chain = prompt | llm | StrOutputParser()
    response = chain.invoke(
        {
            "excerpt": excerpt,
            "filename": filename,
            "taxonomy": _format_taxonomy(tree),
        }
    )
    metadata = normalise_metadata(_extract_json(response), filename, leaf_labels)
    metadata["language"] = _resolve_language(metadata.get("language"), excerpt)
    return metadata, selected_model
