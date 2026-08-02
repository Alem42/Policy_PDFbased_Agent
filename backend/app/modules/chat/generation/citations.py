import re

_CITATION_MARKER = re.compile(r"\[(\d+)\]")


def cited_evidence_sources(
    evidence_sources: list,
    citations: list[dict],
    answer: str,
) -> list:
    """Return only evidence tiers actually cited in the final answer.

    A full-corpus hit from a document already surfaced by selected-document
    search is not labelled as wider-library evidence.
    """

    cited_numbers = {int(match) for match in _CITATION_MARKER.findall(answer)}
    if not cited_numbers:
        return []
    internal_document_ids = {
        citation.get("document_id")
        for citation in citations
        if citation.get("tier") == "internal" and citation.get("document_id")
    }
    cited_tiers: set = set()
    for citation in citations:
        if citation.get("number") not in cited_numbers:
            continue
        tier = citation.get("tier")
        if not tier:
            continue
        if tier == "full_corpus" and citation.get("document_id") in internal_document_ids:
            continue
        cited_tiers.add(tier)
    return [source for source in evidence_sources if source in cited_tiers]
