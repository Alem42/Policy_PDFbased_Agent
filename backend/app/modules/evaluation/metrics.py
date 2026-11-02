"""Deterministic measurements, deliberately separate from semantic answer grading."""

import math
import re
import statistics
import unicodedata


def normalized(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKC", text).casefold() if c.isalnum())


def evidence_metrics(gold: list[dict], chunks: list[dict], mapping: dict) -> dict:
    if not gold:
        return {"evidence_recall_at_k": None, "mrr": None}
    ranks = []
    for item in gold:
        ranks.append(
            next(
                (
                    i
                    for i, chunk in enumerate(chunks, 1)
                    if any(
                        str(chunk.get("document_id")) == mapping.get(anchor["source_id"])
                        and chunk.get("page_start", 0) <= anchor["page"] <= chunk.get("page_end", 0)
                        and normalized(anchor["quote"]) in normalized(chunk.get("text", ""))
                        for anchor in item.get("alternatives", [item])
                    )
                ),
                None,
            )
        )
    found = [r for r in ranks if r is not None]
    return {"evidence_recall_at_k": len(found) / len(gold), "mrr": 1 / min(found) if found else 0.0}


def citation_metrics(
    answer: str, citations: list[dict], stored_chunks: list[dict], allowed_ids: list[str]
) -> dict:
    # Supports [1], [1, 2] and [1][2]. Measures provenance/format, not entailment.
    markers = [
        int(n)
        for group in re.findall(r"\[(\d+(?:\s*,\s*\d+)*)\]", answer)
        for n in re.findall(r"\d+", group)
    ]
    by_id = {str(c["id"]): c for c in stored_chunks}
    valid = []
    for marker in markers:
        citation = citations[marker - 1] if 0 < marker <= len(citations) else {}
        chunk = by_id.get(str(citation.get("chunk_id")))
        quote = normalized(citation.get("quote", ""))
        valid.append(
            bool(
                chunk
                and str(chunk["document_id"]) in allowed_ids
                and str(citation.get("document_id")) == str(chunk["document_id"])
                and citation.get("page") == chunk["page_start"]
                and quote
                and quote in normalized(chunk["text"])
            )
        )
    return {
        "citation_marker_count": len(markers),
        "invalid_citation_markers": len(valid) - sum(valid),
        "citation_integrity": sum(valid) / len(valid) if valid else None,
        "has_citations": bool(markers),
    }


def aggregate(results: list[dict]) -> dict:
    completed = [r for r in results if r.get("status") == "completed"]
    positives = [r for r in completed if r["expected_allow"]]
    negatives = [r for r in completed if not r["expected_allow"]]
    recall = [
        r["evidence_recall_at_k"] for r in positives if r.get("evidence_recall_at_k") is not None
    ]
    latencies = sorted(r["total_ms"] for r in completed)
    rates = {
        "high_evidence_allow_rate": sum(r["actual_allow"] for r in positives) / len(positives)
        if positives
        else None,
        "low_evidence_block_rate": sum(not r["actual_allow"] for r in negatives) / len(negatives)
        if negatives
        else None,
    }
    return {
        "completed": len(completed),
        "errors": len(results) - len(completed),
        "positive_cases": len(positives),
        "negative_cases": len(negatives),
        "true_allow": sum(r["actual_allow"] for r in positives),
        "false_block": sum(not r["actual_allow"] for r in positives),
        "false_allow": sum(r["actual_allow"] for r in negatives),
        "true_block": sum(not r["actual_allow"] for r in negatives),
        **rates,
        "balanced_gate_accuracy": statistics.mean(rates.values())
        if all(v is not None for v in rates.values())
        else None,
        "mean_evidence_recall_at_k": statistics.mean(recall) if recall else None,
        "mean_mrr": statistics.mean(r["mrr"] for r in positives) if positives else None,
        "invalid_citation_markers": sum(r.get("invalid_citation_markers", 0) for r in completed),
        "allowed_answers_without_citations": sum(
            r["actual_allow"] and not r.get("has_citations") for r in completed
        ),
        "median_total_ms": statistics.median(latencies) if latencies else None,
        "p95_total_ms": latencies[max(0, math.ceil(len(latencies) * 0.95) - 1)]
        if latencies
        else None,
        "semantic_quality": "pending_human_review",
    }
