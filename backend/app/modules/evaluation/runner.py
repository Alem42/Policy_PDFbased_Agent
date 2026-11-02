from __future__ import annotations

import asyncio
import os
import time

from psycopg import sql

from app.core.config import get_settings
from app.core.database import get_connection
from app.modules.chat.rag.generation import generate_answer_streaming
from app.modules.chat.rag.graph.workflow import run_retrieval
from app.modules.chat.rag.prompts import get_insufficient_evidence_message
from app.modules.embedding import service as embedding
from app.modules.evaluation import corpus
from app.modules.evaluation.metrics import citation_metrics, evidence_metrics
from app.modules.evidence_validation import service as evidence_validation
from app.modules.reranking import service as reranking


def snapshot(source_ids: list[str]) -> dict:
    identifiers = corpus.mapping()
    if any(s not in identifiers for s in source_ids):
        raise ValueError("Import the evaluation corpus before running these cases.")
    scope = {s: identifiers[s] for s in sorted(set(source_ids))}
    config, rerank = embedding.active_config(), reranking.active_config()
    table = embedding.active_vector_table()
    with get_connection() as conn:
        if not conn.execute("SELECT to_regclass(%s) AS t", (table,)).fetchone()["t"]:
            raise ValueError(
                "Active model has no vector table. Re-embed or rescan the library first."
            )
        if conn.execute(
            "SELECT 1 FROM document_tasks WHERE document_id=ANY(%s::uuid[]) "
            "AND status IN ('queued','running') LIMIT 1",
            (list(scope.values()),),
        ).fetchone():
            raise ValueError("Wait for document processing to finish before evaluating.")
        rows = conn.execute(
            sql.SQL(
                "SELECT d.id,d.status,count(c.id) AS chunks,count(v.chunk_id) AS vectors,"
                "md5(COALESCE(string_agg(c.id::text,',' ORDER BY c.id),'')) AS chunk_fingerprint "
                "FROM documents d LEFT JOIN document_chunks c ON c.document_id=d.id "
                "LEFT JOIN {} v ON v.chunk_id=c.id WHERE d.id=ANY(%s::uuid[]) "
                "GROUP BY d.id ORDER BY d.id"
            ).format(sql.Identifier(table)),
            (list(scope.values()),),
        ).fetchall()
    if len(rows) != len(set(scope.values())) or any(
        r["status"] != "ready" or not r["chunks"] or r["chunks"] != r["vectors"] for r in rows
    ):
        raise ValueError(
            "Every selected document must be ready with one active-model vector per chunk."
        )
    return {
        "mapping": scope,
        "documents": [{**dict(r), "id": str(r["id"])} for r in rows],
        "embedding": {
            k: getattr(config, k)
            for k in (
                "provider",
                "local_model",
                "api_provider",
                "api_model",
                "dimensions",
                "symmetric",
                "chunk_token_budget",
                "chunk_overlap_tokens",
                "context_header_strategy",
                "token_counting",
                "distance_metric",
            )
        },
        "distance_threshold": config.resolved_evidence_distance_threshold(),
        "reranking": {
            "enabled": rerank.enabled,
            "provider": rerank.provider,
            "model": rerank.active_model_id(),
            "min_score": rerank.resolved_min_score(),
        },
        "max_context_characters": get_settings().max_context_characters,
        "evidence_validation": evidence_validation.config().model_dump(),
        "validation_prompt_version": evidence_validation.PROMPT_VERSION,
        "bm25_enabled": os.getenv("RETRIEVAL_BM25_ENABLED", "true"),
        "bm25_k1": os.getenv("RETRIEVAL_BM25_K1", "1.5"),
        "bm25_b": os.getenv("RETRIEVAL_BM25_B", "0.75"),
        "rrf_k": os.getenv("RETRIEVAL_RRF_K", "60"),
        "named_instrument_veto_enabled": os.getenv(
            "RETRIEVAL_NAMED_INSTRUMENT_LLM_VETO_ENABLED", "true"
        ),
    }


async def run_case(case, config, frozen) -> dict:
    started = time.perf_counter()
    allowed_ids = [frozen["mapping"][s] for s in case["source_ids"]]
    state = await asyncio.to_thread(
        run_retrieval,
        case["question"],
        document_ids=allowed_ids,
        top_k=config["top_k"],
        include_restricted=True,
        model=config["model"],
        answer_mode="analysis",
    )
    retrieved_at = time.perf_counter()
    allowed = bool(state["evidence_sufficient"])
    pre_generation_allow = allowed
    generation_reports = []
    ttft = None
    if allowed:
        parts = []
        async with asyncio.timeout(180):
            async for part in generate_answer_streaming(
                case["question"],
                state["context"],
                model=config["model"],
                citations=state["citations"],
                answer_mode="analysis",
                validation_callback=generation_reports.append,
            ):
                if ttft is None:
                    ttft = round((time.perf_counter() - started) * 1000, 2)
                parts.append(part)
        answer = "".join(parts)
        if generation_reports and not generation_reports[-1]["allowed"]:
            allowed = False
        if not answer.strip():
            raise ValueError("Generation returned no answer text.")
    else:
        answer = get_insufficient_evidence_message(
            question=case["question"],
            reason=state.get("evidence_reason") or "Insufficient evidence.",
            mode="researcher",
        )
    finished = time.perf_counter()
    gold = (
        (
            [{"alternatives": r["alternatives"]} for r in case["requirements"]]
            if case.get("requirements")
            else case.get("evidence", [])
        )
        if case["expected_allow"]
        else []
    )
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id,document_id,page_start,text FROM document_chunks WHERE id=ANY(%s::uuid[])",
            ([str(c["chunk_id"]) for c in state["citations"] if c.get("chunk_id")],),
        ).fetchall()
    result = {
        "case_id": case["id"],
        "status": "completed",
        "question": case["question"],
        "expected_allow": case["expected_allow"],
        "actual_allow": allowed,
        "pre_generation_allow": pre_generation_allow,
        "validation_report": state.get("validation_report", {}),
        "generation_validation": generation_reports[-1] if generation_reports else {},
        "gate_correct": allowed == case["expected_allow"],
        "evidence_reason": state.get("evidence_reason"),
        "answer": answer,
        "citations": state["citations"],
        "chunks": state["chunks"],
        "raw_chunks": state["raw_chunks"],
        "context_truncated": state["truncated"],
        "used_vector_retrieval": state["used_vector_retrieval"],
        "retrieval_ms": round((retrieved_at - started) * 1000, 2),
        "generation_ms": round((finished - retrieved_at) * 1000, 2),
        "total_ms": round((finished - started) * 1000, 2),
        "ttft_ms": ttft,
        "token_usage": generation_reports[-1].get("generation_usage")
        if generation_reports
        else None,
        "semantic_score": None,
        **evidence_metrics(gold, state["chunks"], frozen["mapping"]),
        **citation_metrics(answer, state["citations"], rows, allowed_ids),
    }
    return result
