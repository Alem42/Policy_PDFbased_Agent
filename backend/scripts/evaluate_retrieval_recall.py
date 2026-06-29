from __future__ import annotations

import runpy
from math import sqrt
from pathlib import Path

from app.modules.documents.embeddings import embed_documents, embed_query

namespace = runpy.run_path(str(Path("scripts/evaluate_embeddings.py")))
cases = namespace["CASES"]


def cosine_similarity(first: list[float], second: list[float]) -> float:
    dot_product = sum(a * b for a, b in zip(first, second, strict=True))
    first_norm = sqrt(sum(value * value for value in first))
    second_norm = sqrt(sum(value * value for value in second))

    if first_norm == 0 or second_norm == 0:
        return 0.0

    return dot_product / (first_norm * second_norm)


corpus: list[dict[str, str]] = []

for case in cases:
    corpus.append(
        {
            "case_name": case.name,
            "kind": "relevant",
            "text": case.relevant,
        }
    )
    corpus.append(
        {
            "case_name": case.name,
            "kind": "distractor",
            "text": case.lexical_distractor,
        }
    )

document_vectors = embed_documents([record["text"] for record in corpus])

recall_at_1 = 0
recall_at_3 = 0
recall_at_5 = 0
reciprocal_ranks: list[float] = []

print(f"Corpus size: {len(corpus)} passages")
print("-" * 100)

for case in cases:
    query_vector = embed_query(case.query)

    ranked: list[tuple[float, int]] = []

    for index, document_vector in enumerate(document_vectors):
        score = cosine_similarity(query_vector, document_vector)
        ranked.append((score, index))

    ranked.sort(key=lambda item: item[0], reverse=True)

    relevant_rank = next(
        rank
        for rank, (_, index) in enumerate(ranked, start=1)
        if corpus[index]["case_name"] == case.name
        and corpus[index]["kind"] == "relevant"
    )

    recall_at_1 += int(relevant_rank <= 1)
    recall_at_3 += int(relevant_rank <= 3)
    recall_at_5 += int(relevant_rank <= 5)
    reciprocal_ranks.append(1 / relevant_rank)

    print(f"{case.name}: relevant rank={relevant_rank}")

    for displayed_rank, (score, index) in enumerate(ranked[:3], start=1):
        record = corpus[index]
        marker = " <-- correct" if (
            record["case_name"] == case.name
            and record["kind"] == "relevant"
        ) else ""

        print(
            f"  {displayed_rank}. score={score:.4f} "
            f"{record['case_name']}/{record['kind']}{marker}"
        )

print("-" * 100)

case_count = len(cases)
mean_reciprocal_rank = sum(reciprocal_ranks) / case_count

print(f"Recall@1: {recall_at_1}/{case_count} = {recall_at_1 / case_count:.1%}")
print(f"Recall@3: {recall_at_3}/{case_count} = {recall_at_3 / case_count:.1%}")
print(f"Recall@5: {recall_at_5}/{case_count} = {recall_at_5 / case_count:.1%}")
print(f"MRR: {mean_reciprocal_rank:.4f}")
