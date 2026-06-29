from __future__ import annotations

import argparse
import math
import os
import runpy
from pathlib import Path

from fastembed.rerank.cross_encoder import TextCrossEncoder

from app.modules.documents.embeddings import embed_documents, embed_query

RERANKER_MODEL_NAME = os.getenv(
    "RERANKER_BENCHMARK_MODEL",
    "Xenova/ms-marco-MiniLM-L-6-v2",
)
CANDIDATE_LIMIT = 3
MIN_TOP1_ACCURACY = 0.75


def cosine_similarity(first: list[float], second: list[float]) -> float:
    dot_product = sum(
        first_value * second_value
        for first_value, second_value in zip(first, second, strict=True)
    )
    first_norm = math.sqrt(sum(value * value for value in first))
    second_norm = math.sqrt(sum(value * value for value in second))

    if first_norm == 0.0 or second_norm == 0.0:
        return 0.0

    return dot_product / (first_norm * second_norm)


def load_cases() -> list:
    namespace = runpy.run_path(str(Path("scripts/evaluate_embeddings.py")))
    return namespace["CASES"]


def evaluate() -> dict[str, float | bool]:
    cases = load_cases()

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

    print(f"Loading reranker: {RERANKER_MODEL_NAME}")
    reranker = TextCrossEncoder(model_name=RERANKER_MODEL_NAME)

    print(f"Embedding {len(corpus)} passages...")
    document_vectors = embed_documents(
        [record["text"] for record in corpus]
    )

    candidate_recall_count = 0
    reranker_top1_count = 0

    print()
    print("Embedding recall followed by cross-encoder reranking")
    print("-" * 100)

    for case in cases:
        query_vector = embed_query(case.query)

        dense_results = sorted(
            (
                (
                    cosine_similarity(query_vector, document_vector),
                    document_index,
                )
                for document_index, document_vector in enumerate(document_vectors)
            ),
            key=lambda result: result[0],
            reverse=True,
        )

        candidate_indexes = [
            document_index
            for _, document_index in dense_results[:CANDIDATE_LIMIT]
        ]

        relevant_in_candidates = any(
            corpus[index]["case_name"] == case.name
            and corpus[index]["kind"] == "relevant"
            for index in candidate_indexes
        )
        candidate_recall_count += int(relevant_in_candidates)

        candidate_texts = [
            corpus[index]["text"]
            for index in candidate_indexes
        ]

        reranker_scores = [
            float(score)
            for score in reranker.rerank(case.query, candidate_texts)
        ]

        reranked_results = sorted(
            zip(candidate_indexes, reranker_scores, strict=True),
            key=lambda result: result[1],
            reverse=True,
        )

        relevant_dense_rank = next(
            rank
            for rank, (_, document_index) in enumerate(
                dense_results,
                start=1,
            )
            if corpus[document_index]["case_name"] == case.name
            and corpus[document_index]["kind"] == "relevant"
        )

        relevant_reranked_rank = next(
            (
                rank
                for rank, (document_index, _) in enumerate(
                    reranked_results,
                    start=1,
                )
                if corpus[document_index]["case_name"] == case.name
                and corpus[document_index]["kind"] == "relevant"
            ),
            None,
        )

        reranker_won = relevant_reranked_rank == 1
        reranker_top1_count += int(reranker_won)

        print(
            f"{case.name:<34} "
            f"{'PASS' if reranker_won else 'FAIL'} "
            f"dense_rank={relevant_dense_rank} "
            f"reranked_rank={relevant_reranked_rank}"
        )

        for rank, (document_index, score) in enumerate(
            reranked_results,
            start=1,
        ):
            record = corpus[document_index]
            marker = (
                " <-- correct"
                if record["case_name"] == case.name
                and record["kind"] == "relevant"
                else ""
            )

            print(
                f"  {rank}. score={score:.4f} "
                f"{record['case_name']}/{record['kind']}{marker}"
            )

    case_count = len(cases)
    candidate_recall = candidate_recall_count / case_count
    reranker_top1_accuracy = reranker_top1_count / case_count

    passed = (
        candidate_recall == 1.0
        and reranker_top1_accuracy >= MIN_TOP1_ACCURACY
    )

    print("-" * 100)
    print(
        f"Embedding Recall@{CANDIDATE_LIMIT}: "
        f"{candidate_recall_count}/{case_count} = {candidate_recall:.1%}"
    )
    print(
        "Reranker Top-1 accuracy: "
        f"{reranker_top1_count}/{case_count} = "
        f"{reranker_top1_accuracy:.1%}"
    )
    print(f"Two-stage retrieval: {'PASS' if passed else 'FAIL'}")

    return {
        "candidate_recall": candidate_recall,
        "reranker_top1_accuracy": reranker_top1_accuracy,
        "passed": passed,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--enforce",
        action="store_true",
        help="Exit with status 1 when the two-stage pipeline fails.",
    )
    args = parser.parse_args()

    results = evaluate()

    if args.enforce and not results["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
