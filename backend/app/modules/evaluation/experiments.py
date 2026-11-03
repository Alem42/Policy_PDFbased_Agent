"""Controlled retrieval ablations using production chunker, models, BM25 and RRF.

Only experiment-owned tables are written. No user document chunk is replaced.
"""

from __future__ import annotations

import hashlib
import json
import statistics
import time
from pathlib import Path

import numpy as np

from app.core.config import get_settings
from app.core.database import get_connection
from app.modules.documents.chunker import DocumentChunker
from app.modules.documents.repositories.content import document_content_repository
from app.modules.embedding import service as embedding
from app.modules.evaluation import corpus
from app.modules.evaluation import lab_repository as lab
from app.modules.evaluation.metrics import normalized
from app.modules.evaluation.repository import encode
from app.modules.local_models.runtime import EMBEDDING_MODEL
from app.modules.reranking import service as reranking
from app.modules.retrieval.coverage import allocate
from app.modules.retrieval.evidence import relevance_at_thresholds
from app.modules.retrieval.keyword_search import Bm25Index, rrf_merge

BUDGETS = (256, 384, 512, 768)
OVERLAP_RATIOS = (0, 0.125, 0.25)


def extended_cases():
    return json.loads((corpus.DATA / "cases-v2.json").read_text(encoding="utf8"))["cases"]


def sources():
    mapping = corpus.mapping()
    return {
        entry["id"]: document_content_repository.get_pages(
            mapping[entry["id"]], include_restricted=True
        )
        for entry in corpus.manifest()["documents"]
    }


def source_fingerprint(pages):
    return {key: hashlib.sha256(encode(value).encode()).hexdigest() for key, value in pages.items()}


def model_revision():
    path = (
        get_settings().model_cache_path
        / "huggingface"
        / f"models--{EMBEDDING_MODEL.replace('/', '--')}"
        / "refs/main"
    )
    return path.read_text(encoding="utf8").strip()


def build_index(pages, budget, overlap):
    if embedding.active_model_id() != EMBEDDING_MODEL or embedding.active_dimension() != 1024:
        raise ValueError("Chunk experiments require active Qwen3-Embedding-0.6B / 1024d.")
    config = {
        "budget": budget,
        "overlap": overlap,
        "header_strategy": "none",
        "embedding_model": EMBEDDING_MODEL,
        "model_revision": model_revision(),
        "tokenizer": "Qwen exact",
        "chunker": "production-paragraph-v3-exact-budget",
        "chunker_source_sha256": hashlib.sha256(
            (Path(__file__).parents[1] / "documents" / "chunker.py").read_bytes()
        ).hexdigest(),
    }
    fingerprint = source_fingerprint(pages)
    identifier = hashlib.sha256(encode([config, fingerprint]).encode()).hexdigest()[:32]
    with get_connection() as conn:
        old = conn.execute("SELECT * FROM evaluation_indexes WHERE id=%s", (identifier,)).fetchone()
    if old and old["status"] == "ready":
        return identifier, old["stats"]
    started = time.perf_counter()
    rows = []
    chunker = DocumentChunker(token_counter=embedding.count_tokens)
    for source_id, doc_pages in pages.items():
        for chunk in chunker.chunk(doc_pages, max_tokens=budget, overlap=overlap):
            rows.append(
                {
                    **chunk,
                    "source_id": source_id,
                    "chunk_key": f"{source_id}:{chunk['chunk_index']}",
                }
            )
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO evaluation_indexes(id,config,source_snapshot,status) "
            "VALUES (%s,%s::jsonb,%s::jsonb,'building') "
            "ON CONFLICT(id) DO UPDATE SET status='building',error=NULL",
            (identifier, encode(config), encode(fingerprint)),
        )
    try:
        vectors = embedding.embed_documents([r["text"] for r in rows])
        stats = {
            **config,
            "chunks": len(rows),
            "build_ms": round((time.perf_counter() - started) * 1000, 2),
            "total_chunk_tokens": sum(r["token_count"] for r in rows),
            "mean_chunk_tokens": statistics.mean(r["token_count"] for r in rows),
            "max_chunk_tokens": max(r["token_count"] for r in rows),
        }
        with get_connection() as conn:
            conn.execute("DELETE FROM evaluation_index_chunks WHERE index_id=%s", (identifier,))
            with conn.cursor() as cursor:
                cursor.executemany(
                    "INSERT INTO "
                    "evaluation_index_chunks(index_id,chunk_key,source_id,page_start,page_end,text,token_count,embedding)"
                    " "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s::vector)",
                    [
                        (
                            identifier,
                            r["chunk_key"],
                            r["source_id"],
                            r["page_start"],
                            r["page_end"],
                            r["text"],
                            r["token_count"],
                            embedding.vector_literal(v),
                        )
                        for r, v in zip(rows, vectors, strict=True)
                    ],
                )
            conn.execute(
                "UPDATE evaluation_indexes SET "
                "status='ready',stats=%s::jsonb,finished_at=now() WHERE id=%s",
                (encode(stats), identifier),
            )
        return identifier, stats
    except Exception as exc:
        with get_connection() as conn:
            conn.execute(
                "UPDATE evaluation_indexes SET status='failed',error=%s WHERE id=%s",
                (str(exc), identifier),
            )
        raise


def load_index(identifier):
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT chunk_key AS chunk_id,source_id AS "
            "document_id,page_start,page_end,text,token_count,embedding::text "
            "AS vector "
            "FROM evaluation_index_chunks WHERE index_id=%s ORDER BY chunk_key",
            (identifier,),
        ).fetchall()
    matrix = np.asarray([json.loads(r.pop("vector")) for r in rows], dtype=np.float32)
    return [dict(r) for r in rows], matrix


def gold_matches(case, row):
    result = []
    for requirement in case.get("requirements", []):
        if any(
            a["source_id"] == str(row["document_id"])
            and row["page_start"] <= a["page"] <= row["page_end"]
            and normalized(a["quote"]) in normalized(row["text"])
            for a in requirement["alternatives"]
        ):
            result.append(requirement["id"])
    return result


def rank(case, query_vector, rows, matrix):
    started = time.perf_counter()
    slots = [i for i, r in enumerate(rows) if r["document_id"] in case["source_ids"]]
    scoped = [rows[i] for i in slots]
    similarities = matrix[slots] @ np.asarray(query_vector, dtype=np.float32)
    distances = {r["chunk_id"]: float(1 - s) for r, s in zip(scoped, similarities, strict=True)}
    dense = [
        {**r, "distance": distances[r["chunk_id"]]}
        for r in sorted(scoped, key=lambda r: distances[r["chunk_id"]])[:36]
    ]
    sparse = [
        {**r, "bm25_score": score, "distance": distances[r["chunk_id"]]}
        for r, score in Bm25Index(scoped).search(case["question"], 36)
    ]
    candidates = rrf_merge(dense, sparse, limit=36, k=60)
    ranked = reranking.rerank(case["question"], candidates, limit=36)
    if any("reranker_score" not in r for r in ranked):
        raise ValueError("Experiment requires real reranker scores, no silent fallback.")
    lightweight = [
        {k: r[k] for k in ("chunk_id", "document_id", "distance", "reranker_score", "token_count")}
        | {"gold_matches": gold_matches(case, r)}
        for r in ranked
    ]
    return {
        "case_id": case["id"],
        "ranked": lightweight,
        "retrieval_ms": round((time.perf_counter() - started) * 1000, 2),
    }


def score_trial(case, trial, k, quota=True, distance=1.0, floor=0.0):
    selected = allocate(trial["ranked"], k, per_document=quota)
    selected = [
        r for r in selected if relevance_at_thresholds(case["question"], r, distance, floor)
    ]
    required = {r["id"] for r in case.get("requirements", [])}
    found = {g for row in selected for g in row["gold_matches"]}
    ranks = [i for i, row in enumerate(selected, 1) if row["gold_matches"]]
    return {
        "recall": len(found & required) / len(required) if required else None,
        "complete": bool(required) and required <= found,
        "proxy_allow": bool(selected),
        "context_tokens": sum(r["token_count"] for r in selected),
        "mrr": 1 / min(ranks) if ranks else 0,
        "selected_ids": [r["chunk_id"] for r in selected],
    }


def summary(cases, trials, k=6, quota=True, distance=1.0, floor=0.0, split="calibration"):
    paired = [
        (c, score_trial(c, trials[c["id"]], k, quota, distance, floor))
        for c in cases
        if c["split"] == split
    ]
    positives = [s for c, s in paired if c["expected_allow"]]
    negatives = [s for c, s in paired if not c["expected_allow"]]
    return {
        "n": len(paired),
        "positive_count": len(positives),
        "negative_count": len(negatives),
        "complete_evidence_rate": statistics.mean(s["complete"] for s in positives)
        if positives
        else None,
        "mean_evidence_recall": statistics.mean(s["recall"] for s in positives)
        if positives
        else None,
        "mean_mrr": statistics.mean(s["mrr"] for s in positives) if positives else None,
        "proxy_false_allow_rate": statistics.mean(s["proxy_allow"] for s in negatives)
        if negatives
        else None,
        "mean_context_tokens": statistics.mean(s["context_tokens"] for _, s in paired)
        if paired
        else 0,
    }


def chunk_sweep(run):
    pages = sources()
    cases = run["cases"]
    vectors = embedding.embed_queries([c["question"] for c in cases])
    board = []
    for budget in BUDGETS:
        for ratio in OVERLAP_RATIOS:
            overlap = int(budget * ratio)
            variant = f"b{budget}-o{overlap}"
            lab.progress(
                run,
                {
                    "stage": "chunk_sweep",
                    "variant": variant,
                    "variants_completed": len(board),
                    "variants_total": 12,
                },
            )
            identifier, stats = build_index(pages, budget, overlap)
            rows, matrix = load_index(identifier)
            stored = {t["case_id"]: t for t in lab.trials(run["id"], variant)}
            for number, (case, vector) in enumerate(zip(cases, vectors, strict=True), 1):
                if case["id"] not in stored:
                    output = rank(case, vector, rows, matrix)
                    lab.trial(run, variant, case["id"], output)
                    stored[case["id"]] = output
                if number % 10 == 0:
                    lab.progress(
                        run,
                        {
                            "stage": "chunk_sweep",
                            "variant": variant,
                            "cases_completed": number,
                            "case_count": len(cases),
                            "variants_completed": len(board),
                            "variants_total": 12,
                        },
                    )
            entry = {
                "variant": variant,
                "index_id": identifier,
                "stats": stats,
                "calibration": summary(cases, stored),
                "validation": summary(cases, stored, split="validation"),
                "diagnostic": summary(cases, stored, split="diagnostic"),
            }
            board.append(entry)
            lab.artifact(run, "chunk_leaderboard", board)
    # Only calibration labels select the winner. Validation is displayed, not optimized.
    best = max(
        board,
        key=lambda e: (
            e["calibration"]["complete_evidence_rate"],
            e["calibration"]["mean_evidence_recall"],
            -e["calibration"]["mean_context_tokens"],
            -e["stats"]["chunks"],
        ),
    )
    lab.artifact(run, "selected_index", best)
    lab.progress(
        run,
        {
            "stage": "chunk_sweep_completed",
            "variants_completed": 12,
            "case_count": len(cases),
            "selected": best["variant"],
        },
    )
    return best


def parameter_sweep(run, parent):
    cases = run["cases"]
    chosen = parent["selected_index"]
    variant = chosen["variant"]
    trials = {t["case_id"]: t for t in lab.trials(parent["id"], variant)}
    board = []
    for k in (4, 6, 8, 12):
        for quota in (False, True):
            for distance in (0.30, 0.35, 0.40, 0.45, 0.50, 0.60):
                for floor in (0.2, 0.5, 0.8, 0.95):
                    params = {
                        "top_k": k,
                        "per_document_quota": quota,
                        "distance": distance,
                        "floor": floor,
                    }
                    metrics = summary(cases, trials, k, quota, distance, floor)
                    board.append(
                        {
                            "parameters": params,
                            "calibration": metrics,
                            "validation": summary(
                                cases, trials, k, quota, distance, floor, split="validation"
                            ),
                            "diagnostic": summary(
                                cases, trials, k, quota, distance, floor, split="diagnostic"
                            ),
                        }
                    )
    # A score gate alone is not answerability. Retain evidence coverage,
    # then minimize weak passes and context cost.
    best = max(
        board,
        key=lambda e: (
            e["calibration"]["complete_evidence_rate"],
            e["calibration"]["mean_evidence_recall"],
            -e["calibration"]["proxy_false_allow_rate"],
            -e["calibration"]["mean_context_tokens"],
            e["parameters"]["per_document_quota"],
        ),
    )
    lab.artifact(run, "parameter_grid", board)
    lab.artifact(run, "selected_parameters", best)
    lab.artifact(run, "selected_index", chosen)
    lab.progress(
        run,
        {
            "stage": "parameter_sweep_completed",
            "configurations": len(board),
            "selected": best["parameters"],
        },
    )
    return best
