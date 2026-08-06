from __future__ import annotations

import re

from app.modules.embedding import service as embedding
from app.modules.reranking import service as reranking

MIN_CONTEXT_CHARACTERS = 200
MAX_VECTOR_DISTANCE = 0.45
MIN_RERANKER_SCORE = -7.0

REASON_NO_TEXT = "No extractable text was found in the selected documents."
REASON_LOW_RELEVANCE = (
    "The selected documents do not contain passages closely related to your question."
)
REASON_SHORT_CONTEXT = "Too little relevant text was retrieved to support a reliable answer."

# Named laws and policy instruments are factual identifiers, not merely search
# keywords. Dense retrieval can correctly recognise that two passages are about
# the same broad topic while still returning the wrong Act or framework. Keep
# this deliberately narrow: only title-cased names ending in a known instrument
# type are checked, so ordinary questions and semantic paraphrases are unchanged.
_NAMED_INSTRUMENT = re.compile(
    r"\b((?:(?:[A-Z][A-Za-z0-9'’.-]*|\d{4})\s+){1,7}"
    r"(?:Act|Bill|Regulations?|Standard|Framework|Policy|Plan))\b"
)
_GENERIC_INSTRUMENT_TERMS = {
    "act",
    "ai",
    "bill",
    "framework",
    "plan",
    "policy",
    "regulation",
    "regulations",
    "s",
    "standard",
}

_WORD = re.compile(r"[a-z0-9]+")
_STOP_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "do",
    "does",
    "for",
    "from",
    "how",
    "in",
    "is",
    "it",
    "may",
    "of",
    "on",
    "one",
    "or",
    "the",
    "this",
    "to",
    "what",
    "when",
    "which",
    "who",
}


def max_vector_distance() -> float:
    """Return the active embedding model's evidence cutoff."""

    try:
        return embedding.evidence_distance_threshold()
    except Exception:
        return MAX_VECTOR_DISTANCE


def min_reranker_score() -> float:
    """Return the active reranker provider's evidence floor."""

    try:
        return reranking.min_reranker_score()
    except Exception:
        return MIN_RERANKER_SCORE


def lexical_support(question: str, text: str) -> tuple[int, float]:
    """Return matched meaningful query terms and query-term coverage.

    This is a deterministic backstop for embedding providers whose cosine
    scales differ from the configured threshold. It is not used alone for weak
    matches; it must agree with the reranker or have very strong coverage.
    """

    query_terms = {word for word in _WORD.findall(question.lower()) if word not in _STOP_WORDS}
    if not query_terms:
        return 0, 0.0
    text_terms = set(_WORD.findall(text.lower()))
    matches = len(query_terms & text_terms)
    return matches, matches / len(query_terms)


def _unsupported_named_instrument(question: str, evidence_text: str) -> str | None:
    """Return the first explicit instrument name not supported by the evidence.

    Matching every question word would make the gate brittle. Instead, this
    checks only the distinctive terms in an explicitly named Act, Standard,
    Framework, etc. For example, broad Australian AI-policy text cannot support
    a question about the fictional "2031 Quantum AI Act" unless both ``2031``
    and ``quantum`` occur in the retrieved evidence.
    """

    evidence_terms = set(_WORD.findall(evidence_text.lower()))
    for match in _NAMED_INSTRUMENT.finditer(question):
        name = match.group(1).strip()
        distinctive_terms = {
            term
            for term in _WORD.findall(name.lower())
            if term not in _GENERIC_INSTRUMENT_TERMS
        }
        if distinctive_terms and not distinctive_terms.issubset(evidence_terms):
            return name
    return None


def is_chunk_relevant(question: str, chunk: dict) -> bool:
    """Combine dense, reranker, and lexical signals conservatively."""

    distance_passes = float(chunk.get("distance", 1.0)) <= max_vector_distance()
    reranker_score = chunk.get("reranker_score")
    reranker_passes = (
        reranker_score is None or float(reranker_score) >= min_reranker_score()
    )
    if distance_passes:
        return reranker_passes

    matches, coverage = lexical_support(question, chunk.get("text", ""))
    lexical_passes = matches >= 2 and coverage >= 0.30
    if not lexical_passes:
        return False
    if reranker_score is not None:
        return reranker_passes
    return matches >= 3 and coverage >= 0.60


def assess_evidence_sufficiency(
    *,
    question: str,
    raw_chunks: list[dict],
    pages: list[dict],
    context: str,
    has_embeddings: bool,
) -> tuple[bool, str | None]:
    """Apply the deterministic evidence gate to retrieved content."""

    if has_embeddings:
        if not raw_chunks:
            return False, REASON_LOW_RELEVANCE
        relevant_chunks = [chunk for chunk in raw_chunks if is_chunk_relevant(question, chunk)]
        if not relevant_chunks:
            return False, REASON_LOW_RELEVANCE
        evidence_text = "\n".join(
            [context] + [str(chunk.get("text", "")) for chunk in relevant_chunks]
        )
        unsupported_name = _unsupported_named_instrument(question, evidence_text)
        if unsupported_name:
            return (
                False,
                f'The retrieved passages do not mention the explicitly named '
                f'instrument "{unsupported_name}".',
            )
        if len(context.strip()) < MIN_CONTEXT_CHARACTERS:
            return False, REASON_SHORT_CONTEXT
        return True, None

    clean_context = context.strip()
    if len(clean_context) < MIN_CONTEXT_CHARACTERS:
        if pages and sum(len(page.get("text", "")) for page in pages) >= MIN_CONTEXT_CHARACTERS:
            evidence_text = "\n".join(str(page.get("text", "")) for page in pages)
        else:
            return False, REASON_NO_TEXT
    else:
        evidence_text = clean_context
    unsupported_name = _unsupported_named_instrument(question, evidence_text)
    if unsupported_name:
        return (
            False,
            f'The retrieved passages do not mention the explicitly named '
            f'instrument "{unsupported_name}".',
        )
    if len(clean_context) < MIN_CONTEXT_CHARACTERS:
        return (True, None) if pages else (False, REASON_NO_TEXT)
    return True, None
