"""Opt-in real-library checks. Writes reports without credentials or user chat history.

Usage: python -m scripts.verify_qwen_library prepare|configure|import|rescan|wait|verify|reembed|evaluate|report
Run from backend with the project's .venv Python. `prepare` applies migration 029.
"""
import argparse
import json
import math
import time
from pathlib import Path

import httpx
from psycopg import sql

from app.core.database import get_connection
from app.modules.auth.service import create_access_token
from app.modules.embedding.settings import vector_table_name

OUT = Path("eval-results/qwen-upgrade")
TABLE = vector_table_name("Qwen/Qwen3-Embedding-0.6B", 1024)


def write(name, data):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(data, ensure_ascii=False, default=str, indent=2), encoding="utf-8")


def snapshot():
    with get_connection() as conn:
        docs = conn.execute("SELECT d.id,d.original_filename,d.status,d.sha256,dm.keywords,"
                            "count(c.id) AS chunks FROM documents d "
                            "LEFT JOIN document_metadata dm ON dm.document_id=d.id "
                            "LEFT JOIN document_chunks c ON c.document_id=d.id "
                            "GROUP BY d.id,dm.keywords ORDER BY d.original_filename").fetchall()
        chunks = conn.execute("SELECT id,document_id,token_count,page_start,page_end FROM document_chunks ORDER BY id").fetchall()
        vectors = []
        if conn.execute("SELECT to_regclass(%s) AS t", (TABLE,)).fetchone()["t"]:
            vectors = conn.execute(sql.SQL("SELECT chunk_id,embedding_model,vector_dims(embedding) AS dimensions,"
                                           "xmin::text AS transaction_id FROM {} ORDER BY chunk_id").format(sql.Identifier(TABLE))).fetchall()
        tasks = conn.execute("SELECT id,document_id,task_type,status,attempts,last_error,created_at "
                             "FROM document_tasks ORDER BY created_at DESC LIMIT 100").fetchall()
    return json.loads(json.dumps({"documents": docs, "chunks": chunks, "vectors": vectors, "tasks": tasks}, default=str))


def client():
    with get_connection() as conn:
        admin = conn.execute("SELECT id,uid,username,role FROM app_users WHERE role='admin' ORDER BY created_at LIMIT 1").fetchone()
    if not admin:
        raise RuntimeError("An existing administrator is required.")
    return httpx.Client(base_url="http://127.0.0.1:8000/api/v1", timeout=180, trust_env=False,
                        headers={"Authorization": f"Bearer {create_access_token(admin)}"})


def request(method, path, **kwargs):
    with client() as api:
        response = api.request(method, path, **kwargs)
        if response.is_error:
            raise RuntimeError(f"HTTP {response.status_code}: {response.text[:1500]}")
        return response.json()


def wait():
    for _ in range(360):
        state = snapshot()
        active = [t for t in state["tasks"] if t["status"] in ("queued", "running")]
        print(json.dumps({"active_tasks": len(active), "ready": sum(d["status"] == "ready" for d in state["documents"]),
                          "documents": len(state["documents"]), "chunks": len(state["chunks"]), "qwen_vectors": len(state["vectors"])}), flush=True)
        if not active:
            write("after-processing.json", state)
            if any(d["status"] != "ready" for d in state["documents"]):
                raise RuntimeError("Processing ended with documents not ready; inspect after-processing.json.")
            return
        time.sleep(5)
    raise TimeoutError("Document processing did not finish within 30 minutes.")


def main(action):
    if action == "prepare":
        state = snapshot()
        before = OUT / "before.json"
        if not before.exists():
            write("before.json", state)
        with get_connection() as conn:
            conn.execute(Path("database/migrations/029_add_evaluation.sql").read_text(encoding="utf-8"))
        print(json.dumps({"migration": "029", "documents_before": len(state["documents"]), "chunks_before": len(state["chunks"])}))
    elif action == "configure":
        emb = {"provider": "local", "local_model": "Qwen/Qwen3-Embedding-0.6B", "dimensions": 1024,
               "chunk_token_budget": 512, "chunk_overlap_tokens": 64, "batch_size": 8,
               "token_counting": "model", "symmetric": False, "evidence_distance_threshold": 0.45, "local_idle_seconds": 120}
        rerank = {"enabled": True, "provider": "local", "local_model": "Qwen/Qwen3-Reranker-0.6B",
                  "min_score": 0.5, "local_idle_seconds": 120}
        request("PUT", "/admin/embedding", json=emb)
        request("PUT", "/admin/reranking", json=rerank)
        # Live route probes populate the same GPU worker that ingestion will reuse.
        results = {"embedding_probe": request("POST", "/admin/embedding/test", json=emb),
                   "reranker_probe": request("POST", "/admin/reranking/test", json=rerank)}
        assert results["embedding_probe"]["dimension"] == 1024
        write("model-probes.json", results)
        print(json.dumps(results))
    elif action == "import":
        result = request("POST", "/admin/evaluation/corpus")
        write("corpus-import.json", result)
        print(json.dumps(result))
    elif action == "rescan":
        print(json.dumps(request("POST", "/admin/documents/rescan")))
    elif action == "wait":
        wait()
    elif action == "verify":
        state, before = snapshot(), json.loads((OUT / "before.json").read_text(encoding="utf-8"))
        old_ids = {c["id"] for c in before["chunks"]}
        new_ids = {c["id"] for c in state["chunks"]}
        original_docs = {d["id"]: d["sha256"] for d in before["documents"]}
        check = {"documents": len(state["documents"]), "ready": all(d["status"] == "ready" for d in state["documents"]),
                 "original_files_preserved": all(any(d["id"] == k and d["sha256"] == v for d in state["documents"]) for k,v in original_docs.items()),
                 "old_chunk_ids_remaining": len(old_ids & new_ids), "chunks": len(new_ids), "vectors": len(state["vectors"]),
                 "vector_coverage_complete": new_ids == {v["chunk_id"] for v in state["vectors"]},
                 "correct_model_and_dimension": all(v["embedding_model"] == "Qwen/Qwen3-Embedding-0.6B" and v["dimensions"] == 1024 for v in state["vectors"]),
                 "test_tag_count": sum("test-corpus" in (d["keywords"] or []) for d in state["documents"])}
        write("database-verification.json", check)
        write("after-rescan.json", state)
        print(json.dumps(check, indent=2))
        assert check["ready"] and check["original_files_preserved"] and check["old_chunk_ids_remaining"] == 0
        assert check["chunks"] > 0 and check["vector_coverage_complete"] and check["correct_model_and_dimension"] and check["test_tag_count"] == 12
    elif action == "reembed":
        before = snapshot()
        write("before-reembed.json", before)
        print(json.dumps(request("POST", "/admin/documents/reembed")), flush=True)
        wait()
        after = snapshot()
        old = {v["chunk_id"]: v["transaction_id"] for v in before["vectors"]}
        changed = sum(old.get(v["chunk_id"]) != v["transaction_id"] for v in after["vectors"])
        check = {"chunk_ids_unchanged": {c["id"] for c in before["chunks"]} == {c["id"] for c in after["chunks"]},
                 "vector_rows_replaced": changed, "vector_count": len(after["vectors"])}
        write("reembed-verification.json", check)
        print(json.dumps(check))
        assert check["chunk_ids_unchanged"] and changed == len(after["vectors"]) > 0
    elif action == "verify-vectors":
        from app.modules.embedding import service as embedding
        from app.modules.local_models.runtime import local_model_runtime

        with get_connection() as conn:
            rows = conn.execute(sql.SQL(
                "SELECT DISTINCT ON (c.document_id) c.id,c.document_id,c.text,c.metadata_json,"
                "v.embedding::text AS vector FROM document_chunks c JOIN {} v ON v.chunk_id=c.id "
                "ORDER BY c.document_id,c.chunk_index"
            ).format(sql.Identifier(TABLE))).fetchall()
        texts = [f"{r['metadata_json']['context_header']}\n\n{r['text']}"
                 if (r['metadata_json'] or {}).get('context_header') else r['text'] for r in rows]
        try:
            actual = embedding.embed_documents(texts)
            checks = []
            for row, vector in zip(rows, actual, strict=True):
                stored = json.loads(row["vector"])
                norm = lambda v: math.sqrt(sum(x*x for x in v))
                cosine = sum(x*y for x,y in zip(stored, vector, strict=True))/(norm(stored)*norm(vector))
                checks.append({"document_id": str(row["document_id"]), "chunk_id": str(row["id"]),
                               "cosine_to_fresh_qwen_embedding": cosine, "stored_norm": norm(stored)})
            write("vector-recomputation.json", {"samples": checks, "tolerance": "cosine >= 0.999 (BF16 batching)"})
            print(json.dumps({"documents_sampled": len(checks), "min_cosine": min(c["cosine_to_fresh_qwen_embedding"] for c in checks)}))
            assert checks and all(c["cosine_to_fresh_qwen_embedding"] >= .999 for c in checks)
        finally:
            local_model_runtime.unload()
    elif action == "evaluate":
        result = request("POST", "/admin/evaluation/runs", json={"model": "deepseek/deepseek-v4-flash", "top_k": 6, "case_ids": []})
        write("run.json", result)
        print(json.dumps(result))
    elif action == "report":
        identifier = json.loads((OUT / "run.json").read_text(encoding="utf-8"))["id"]
        result = request("GET", f"/admin/evaluation/runs/{identifier}")
        write("evaluation-results.json", result)
        print(json.dumps({"id": identifier, "status": result["status"], "metrics": result["metrics"], "error": result["error"]}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["prepare", "configure", "import", "rescan", "wait", "verify", "reembed", "verify-vectors", "evaluate", "report"])
    main(parser.parse_args().action)
