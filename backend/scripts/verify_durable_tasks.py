"""Real PDF/HTTP/process-crash verification against an initialized disposable local DB.

python scripts/verify_durable_tasks.py --database-url postgresql://user@127.0.0.1:55432/step2_e2e_tests
Creates its own API and worker subprocesses, and terminates only those processes.
Retains demo records/files and writes a JSON report under backend/tmp/durable-demo/.
No remote chat LLM is invoked: embeddings use the project's real local model.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import socket
import statistics
import subprocess
import sys
import threading
import time
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

import fitz
import httpx
import psycopg
from psycopg.rows import dict_row

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))


def child_api(port):
    import uvicorn
    server = uvicorn.Server(uvicorn.Config("app.main:app", host="127.0.0.1", port=port,
                                           log_level="warning"))
    # Select before the loop is created; psycopg's async checkpointer requires this on Windows.
    loop = asyncio.SelectorEventLoop if sys.platform == "win32" else asyncio.new_event_loop
    with asyncio.Runner(loop_factory=loop) as runner:
        runner.run(server.serve())


async def child_worker(concurrency, pause_file, marker):
    from app.core.database import database
    from app.modules.documents.processing_queue import DocumentProcessingQueue
    from app.modules.documents.service import pipeline
    from app.modules.embedding import service as embedding
    await database.connect()
    try:
        await asyncio.to_thread(embedding.embed_query, "Warm up the real local policy embedding model.")
        if pause_file:
            extract = pipeline.extract_document

            def pause_after_real_extraction(path, **kwargs):
                pages = extract(path, **kwargs)
                if Path(path).name == pause_file:
                    Path(marker).write_text(json.dumps({"pages": len(pages),
                        "characters": sum(len(p["text"]) for p in pages)}), encoding="utf-8")
                    threading.Event().wait()  # Intentional fault injection in this test helper only.
                return pages

            pipeline.extract_document = pause_after_real_extraction
        queue = DocumentProcessingQueue(max_concurrent=concurrency)
        await queue.start()
        try:
            await asyncio.Event().wait()
        finally:
            await queue.stop()
    finally:
        await database.disconnect()


def pdf_bytes(name, pages=4):
    document = fitz.open()
    for page_number in range(pages):
        page = document.new_page()
        text = (
            f"{name} - Demonstration policy, page {page_number + 1}\n\n"
            "This document was written for software testing; it is not an actual government policy.\n\n"
            "Riverbend Flood Resilience Plan\n"
            "The annual household resilience grant budget is 420000 dollars.\n"
            "Each eligible household may receive up to 1200 dollars for flood barriers.\n"
            "Applications close on 30 June. Applicants provide proof of residence and receipts.\n\n"
            "Emergency communication and accountability\n"
            "The council sends SMS flood warnings every six hours during a declared emergency.\n"
            "An accessibility officer supports residents who cannot use mobile alerts.\n"
            "The audit team publishes grant expenditure every quarter.\n\n"
            f"Scenario identifier: {name}. Section {page_number + 1} covers district {page_number + 10}.\n"
        )
        assert page.insert_textbox(fitz.Rect(45, 45, 550, 790), text, fontsize=11) > 0
    result = document.tobytes()
    document.close()
    return result


def wait_for(predicate, description, seconds=90):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(0.1)
    raise TimeoutError(f"Timed out: {description}")


def verify(args):
    url = args.database_url or os.environ.get("TEST_DATABASE_URL", "")
    parsed = urlparse(url.replace("postgresql+asyncpg://", "postgresql://", 1))
    if parsed.hostname not in {"127.0.0.1", "localhost"} or not parsed.path.endswith("_tests"):
        raise SystemExit("Use an initialized disposable loopback database whose name ends in _tests.")
    dsn = url.replace("postgresql+asyncpg://", "postgresql://", 1)
    run_id = uuid4().hex[:8]
    folder = BACKEND / "tmp" / "durable-demo" / run_id
    storage = folder / "documents"
    folder.mkdir(parents=True)
    settings = folder / "settings.json"
    settings.write_text("{}", encoding="utf-8")
    env = {**os.environ, "DATABASE_ENABLED": "true", "DATABASE_URL": dsn.replace(
        "postgresql://", "postgresql+asyncpg://", 1), "DATABASE_POOL_PRE_PING": "true",
        "APP_SECRET": uuid4().hex + uuid4().hex, "APP_DEBUG": "false",
        "DOCUMENT_TASK_WORKERS": "0", "DOCUMENT_TASK_POLL_SECONDS": "0.15",
        "DOCUMENT_TASK_LEASE_SECONDS": "6", "DOCUMENT_TASK_HEARTBEAT_SECONDS": "1",
        "DOCUMENT_TASK_RETRY_SECONDS": "0.5", "DOCUMENT_TASK_MAX_ATTEMPTS": "3",
        "RUNTIME_SETTINGS_PATH": str(settings), "DOCUMENT_STORAGE_DIR": str(storage)}
    os.environ.update(env)
    from app.modules.auth.repository import user_repository
    from app.modules.auth.service import hash_password
    from app.core.database import database
    username, password = f"durable_demo_{run_id}", "DurableDemo!2026"
    user_repository.create(username, f"{username}@example.test", hash_password(password), "admin")
    processes, handles = [], []
    base = f"http://127.0.0.1:{args.port}/api/v1"
    report = {"run_id": run_id, "storage": str(storage), "settings": str(settings),
              "username": username, "database_name": parsed.path.lstrip("/"), "checks": {}}
    checks = report["checks"]

    def start(label, arguments):
        log = (folder / f"{label}.log").open("w", encoding="utf-8")
        handles.append(log)
        process = subprocess.Popen([sys.executable, "-u", str(Path(__file__).resolve()), *arguments],
            cwd=BACKEND, env=env, stdout=log, stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
        processes.append(process)
        return process

    def stop(process):
        if process.poll() is None:
            process.terminate()  # Fault injection: only the child process created above.
            process.wait(timeout=10)

    def ready():
        try:
            return httpx.get(base + "/health", timeout=1).status_code == 200
        except httpx.HTTPError:
            return False

    def task(task_id):
        with psycopg.connect(dsn, row_factory=dict_row) as conn:
            return dict(conn.execute("SELECT * FROM document_tasks WHERE id=%s", (task_id,)).fetchone())

    def indexed(document_id):
        with psycopg.connect(dsn, row_factory=dict_row) as conn:
            return dict(conn.execute(
                "SELECT d.status, (SELECT count(*) FROM document_pages WHERE document_id=d.id) AS pages, "
                "(SELECT count(*) FROM document_chunks WHERE document_id=d.id) AS chunks, "
                "(SELECT string_agg(text, ' ') FROM document_chunks WHERE document_id=d.id) AS text "
                "FROM documents d WHERE d.id=%s", (document_id,)).fetchone())

    try:
        with socket.socket() as probe:
            if probe.connect_ex(("127.0.0.1", args.port)) == 0:
                raise RuntimeError("Chosen verification port is already occupied.")
        api = start("api-1", ["--child-api", "--port", str(args.port)])
        wait_for(ready, "API startup")
        client = httpx.Client(base_url=base, timeout=60)
        login = client.post("/auth/login", json={"username": username, "password": password})
        login.raise_for_status()
        client.headers["Authorization"] = "Bearer " + login.json()["token"]
        content = pdf_bytes("restart-policy")
        (folder / "restart-policy.pdf").write_bytes(content)
        arguments = {"files": {"file": ("restart-policy.pdf", content, "application/pdf")},
                     "headers": {"Idempotency-Key": "response-lost-retry"}}
        first = client.post("/admin/documents", **arguments)
        first.raise_for_status()
        document_id, task_id = first.json()["id"], first.json()["task_id"]
        assert task(task_id)["status"] == "queued"
        stop(api)
        api = start("api-2", ["--child-api", "--port", str(args.port)])
        wait_for(ready, "API restarted")
        replay = client.post("/admin/documents", **arguments)
        assert replay.status_code == 202 and replay.json()["id"] == document_id
        assert replay.json()["task_id"] == task_id and replay.json()["replayed"]
        checks["upload_request_survives_api_restart"] = {"document_id": document_id, "task_id": task_id}
        print("PASS: complete PDF, document, queued task and request key survive API restart", flush=True)

        marker = folder / "real-extraction-before-crash.json"
        paused = start("worker-crashed", ["--child-worker", "--concurrency", "1",
                       "--pause-file", "restart-policy.pdf", "--marker", str(marker)])
        wait_for(marker.exists, "real extraction before injected crash")
        initial_heartbeat = task(task_id)["heartbeat_at"]
        backup = start("worker-backup", ["--child-worker", "--concurrency", "1"])
        time.sleep(7)  # Longer than the six-second lease; heartbeats must prevent takeover.
        active = task(task_id)
        assert active["attempts"] == 1 and active["heartbeat_at"] > initial_heartbeat
        checks["heartbeat_prevents_takeover"] = True
        stop(paused)
        wait_for(lambda: task(task_id)["status"] == "succeeded", "lease expiry and recovery")
        result = indexed(document_id)
        assert result["status"] == "ready" and result["pages"] == 4 and result["chunks"] > 0
        assert "420000" in result["text"] and "six hours" in result["text"]
        assert task(task_id)["attempts"] == 2
        checks["forced_worker_death_recovered"] = {"attempts": 2, "pages": result["pages"],
                                                   "chunks": result["chunks"], "real_content_verified": True}
        print("PASS: killed worker after real PDF extraction; second worker reclaimed and indexed real content", flush=True)

        peer = start("worker-peer", ["--child-worker", "--concurrency", "2"])
        from concurrent.futures import ThreadPoolExecutor
        users = []
        for index in range(4):
            name = f"reader_{run_id}_{index}"
            response = client.post("/auth/register", json={"username": name,
                "email": f"{name}@example.test", "password": password,
                "password_confirmation": password, "role": "user"})
            response.raise_for_status()
            users.append(response.json()["token"])
        # A second independently authenticated administrator uploads to the same library.
        invite = client.post("/admin/invites", json={"expires_in_days": 1})
        invite.raise_for_status()
        name = f"uploader_{run_id}"
        invite_body = invite.json()
        invitation = invite_body.get("code") or invite_body.get("invite_code")
        response = client.post("/auth/register", json={"username": name,
            "email": f"{name}@example.test", "password": password,
            "password_confirmation": password, "role": "admin", "invite_code": invitation})
        response.raise_for_status()
        uploader_tokens = [client.headers["Authorization"][7:], response.json()["token"]]
        latencies, response_codes, upload_ids = [], [], []
        stop_monitor = threading.Event()
        peak = {"queued": 0, "running": 0}

        def monitor():
            while not stop_monitor.wait(0.1):
                values = client.get("/admin/document-tasks").json()["counts"]
                for state in peak:
                    peak[state] = max(peak[state], values.get(state, 0))

        def reader(token):
            with httpx.Client(base_url=base, headers={"Authorization": "Bearer " + token}, timeout=30) as user_client:
                for _ in range(15):
                    for path in ("/documents/search", "/chat/sessions"):
                        started = time.monotonic()
                        response = user_client.get(path)
                        latencies.append((time.monotonic() - started) * 1000)
                        response_codes.append(response.status_code)
                    time.sleep(0.03)

        def upload(index):
            pdf = pdf_bytes(f"concurrent-policy-{index}-{run_id}", pages=6)
            with httpx.Client(base_url=base, headers={"Authorization": "Bearer " + uploader_tokens[index % 2]}, timeout=30) as uploader:
                response = uploader.post("/admin/documents", headers={"Idempotency-Key": f"load-{index}"},
                    files={"file": (f"concurrent-policy-{index}.pdf", pdf, "application/pdf")})
                response.raise_for_status()
                upload_ids.append(response.json())

        monitor_thread = threading.Thread(target=monitor)
        monitor_thread.start()
        try:
            with ThreadPoolExecutor(8) as workers:
                futures = [workers.submit(reader, token) for token in users]
                futures += [workers.submit(upload, index) for index in range(8)]
                for future in futures:
                    future.result()
            wait_for(lambda: all(task(row["task_id"])["status"] == "succeeded" for row in upload_ids),
                     "concurrent real PDF tasks", seconds=180)
        finally:
            stop_monitor.set()
            monitor_thread.join(timeout=5)
        assert all(code == 200 for code in response_codes), response_codes
        assert peak["running"] <= 3 and peak["queued"] > 0
        assert all(task(row["task_id"])["attempts"] == 1 for row in upload_ids)
        checks["multi_user_upload_and_reads"] = {"reader_accounts": 4, "uploader_accounts": 2,
            "pdf_uploads": len(upload_ids), "read_requests": len(response_codes), "all_reads_200": True,
            "p50_read_ms": round(statistics.median(latencies), 2),
            "p95_read_ms": round(sorted(latencies)[int(len(latencies) * .95) - 1], 2), "peak": peak}
        print("PASS: two uploading administrators, four reading users, eight real PDFs and 120 reads", flush=True)
        stop(backup)
        stop(peer)

        response = client.post("/admin/documents", files={"file": (
            "storage-recovery.pdf", pdf_bytes("storage-recovery"), "application/pdf")})
        response.raise_for_status()
        repair = response.json()
        with psycopg.connect(dsn, row_factory=dict_row) as conn:
            path = BACKEND / conn.execute("SELECT file_path FROM documents WHERE id=%s", (repair["id"],)).fetchone()["file_path"]
        offline = path.with_suffix(".temporarily-offline")
        path.rename(offline)
        backup = start("worker-storage-recovery", ["--child-worker", "--concurrency", "1"])
        wait_for(lambda: task(repair["task_id"])["status"] == "failed", "bounded missing-file retries")
        assert task(repair["task_id"])["attempts"] == 3
        offline.rename(path)  # Restore byte-identical original, without changing document identity.
        response = client.post(f"/admin/document-tasks/{repair['task_id']}/retry")
        assert response.status_code == 202
        wait_for(lambda: task(repair["task_id"])["status"] == "succeeded", "manual retry after storage restore")
        assert indexed(repair["id"])["status"] == "ready"
        checks["retry_budget_and_manual_repair"] = {"failed_after_attempts": 3,
            "succeeded_on_attempt": task(repair["task_id"])["attempts"], "byte_identical_file_restored": True}
        print("PASS: temporarily missing real PDF failed after three attempts; restore and manual retry succeeded", flush=True)
        report["all_passed"] = True
        client.close()
    finally:
        for process in processes:
            stop(process)
        for handle in handles:
            handle.close()
        database.close_pool()
        (folder / "report.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
        print(f"Report: {folder / 'report.json'}", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url")
    parser.add_argument("--port", type=int, default=8011)
    parser.add_argument("--child-api", action="store_true")
    parser.add_argument("--child-worker", action="store_true")
    parser.add_argument("--concurrency", type=int, default=1)
    parser.add_argument("--pause-file", default="")
    parser.add_argument("--marker", default="")
    args = parser.parse_args()
    if args.child_api:
        child_api(args.port)
    elif args.child_worker:
        asyncio.run(child_worker(args.concurrency, args.pause_file, args.marker))
    else:
        verify(args)
