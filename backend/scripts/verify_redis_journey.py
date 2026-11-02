"""Independent HTTP/Redis/PostgreSQL verification; never initialize an application DB.

Requires explicitly supplied loopback APIs and an initialized *_tests database.
Credentials come from REDIS_DEMO_USERNAME/REDIS_DEMO_PASSWORD or REDIS_DEMO_TOKEN.
Only test accounts/documents created by this run are cleaned up. Redis operations
are restricted to the explicitly supplied test prefix. No remote model quality is
claimed: a real PDF, extracted text and persisted embeddings are checked.

Example (API/DB/Redis processes are started by the operator):
  python scripts/verify_redis_journey.py --base-url http://127.0.0.1:8011 \
    --peer-url http://127.0.0.1:8012 --baseline-url http://127.0.0.1:8013 \
    --database-url postgresql://testuser@127.0.0.1:55432/redis_tests \
    --key-prefix policy:test:run42 --output tmp/redis-demo/journey.json
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
import os
import secrets
import statistics
import sys
import time
from datetime import UTC, datetime
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from uuid import uuid4

import fitz
import httpx
import psycopg
import redis.asyncio as redis
from psycopg import sql
from psycopg.rows import dict_row

BACKEND = Path(__file__).resolve().parents[1]


def api_url(value: str) -> str:
    parsed = urlsplit(value)
    if parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise ValueError("This verifier accepts loopback APIs only.")
    if parsed.username or parsed.password:
        raise ValueError("Do not put credentials in the API URL.")
    return value.rstrip("/") if parsed.path.rstrip("/").endswith("/api/v1") else value.rstrip("/") + "/api/v1"


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False, default=str).encode()).hexdigest()


def percentile(values: list[float], fraction: float) -> float:
    return sorted(values)[max(0, math.ceil(len(values) * fraction) - 1)]


def metric(snapshot: dict, key: str) -> int:
    """Accept a dotted exact path or a unique leaf counter name."""
    current: Any = snapshot
    try:
        for part in key.split("."):
            current = current[part]
        if isinstance(current, (float, int)):
            return int(current)
    except (KeyError, TypeError):
        pass
    found = []

    def visit(value):
        if isinstance(value, dict):
            for name, child in value.items():
                if name == key and isinstance(child, (float, int)):
                    found.append(int(child))
                visit(child)

    visit(snapshot)
    if len(found) != 1:
        raise AssertionError(f"Expected one numeric counter {key!r}; found {len(found)}.")
    return found[0]


def pdf_bytes(marker: str) -> bytes:
    doc = fitz.open()
    for number in range(2):
        page = doc.new_page()
        text = (
            "Riverbend Household Flood Resilience Policy\n\n"
            "This synthetic document verifies software behavior; it is not government guidance.\n\n"
            "Funding and eligibility\n"
            "The annual resilience grant budget is 637421 dollars. Households may claim up to "
            "1200 dollars for flood barriers. Applicants must provide residence evidence and receipts.\n\n"
            f"Unique verification reference: {marker}-section-{number + 1}.\n\n"
            "Applications close on 30 June. Residents may appeal decisions within 14 days. "
            "An accessibility officer assists people unable to use the online application form.\n\n"
            "Emergency warnings are sent every six hours. The audit team publishes expenditure "
            "reports every quarter. All test records should be removable without altering other policies.\n"
        )
        if page.insert_textbox(fitz.Rect(45, 45, 550, 790), text, fontsize=11) <= 0:
            raise AssertionError("PDF fixture text overflowed.")
    result = doc.tobytes()
    doc.close()
    return result


@dataclass
class Account:
    id: str
    token: str
    username: str


class Journey:
    def __init__(self, args):
        self.args = args
        self.base = api_url(args.base_url)
        self.peer = api_url(args.peer_url) if args.peer_url else self.base
        self.baseline = api_url(args.baseline_url) if args.baseline_url else None
        self.frontend = api_url(args.frontend_url) if args.frontend_url else None
        self.dsn = args.database_url.replace("postgresql+asyncpg://", "postgresql://", 1)
        parsed = urlsplit(self.dsn)
        if parsed.hostname not in {"localhost", "127.0.0.1", "::1"} or not parsed.path.endswith("_tests"):
            raise ValueError("Use an initialized, explicitly named loopback *_tests database.")
        redis_target = urlsplit(args.redis_url)
        if redis_target.hostname not in {"localhost", "127.0.0.1", "::1"}:
            raise ValueError("Use a loopback test Redis.")
        if not args.key_prefix or ":test" not in args.key_prefix:
            raise ValueError("Use an explicit Redis test prefix containing ':test'.")
        self.run_id = uuid4().hex[:12]
        self.output = Path(args.output).resolve()
        self.output.parent.mkdir(parents=True, exist_ok=True)
        self.http = httpx.AsyncClient(timeout=httpx.Timeout(45, connect=5), trust_env=False,
                                     limits=httpx.Limits(max_connections=80, max_keepalive_connections=30))
        self.redis = redis.Redis.from_url(args.redis_url, decode_responses=True,
                                         socket_connect_timeout=1, socket_timeout=1)
        self.primary: Account | None = None
        self.secondary: Account | None = None
        self.reader: Account | None = None
        self.created_users: list[str] = []
        self.created_invites: list[str] = []
        self.created_documents: list[str] = []
        self.taxonomy_restore: dict | None = None
        self.key_cleanup: set[str] = set()
        self.report: dict[str, Any] = {
            "run_id": self.run_id, "mode": args.mode,
            "started_at_utc": datetime.now(UTC).isoformat(),
            "environment": {"base_url": self.base, "peer_url": self.peer,
                            "baseline_url": self.baseline, "frontend_url": self.frontend,
                            "database_name": parsed.path[1:],
                            "redis_host": redis_target.hostname, "redis_port": redis_target.port or 6379},
            "checks": {}, "scope": [
                "Real HTTP authentication, Redis commands and PostgreSQL records.",
                "Synthetic PDF with real extraction and persisted model vectors.",
                "Catalogue/taxonomy timings are not LLM-generation performance.",
                "No original library records or application database are deleted or initialized.",
            ],
        }

    def save(self):
        self.output.write_text(json.dumps(self.report, ensure_ascii=False, indent=2, default=str) + "\n",
                               encoding="utf-8")

    def check(self, name: str, data: Any = True):
        self.report["checks"][name] = data
        self.save()
        print("PASS:", name, flush=True)

    def connection(self):
        return psycopg.connect(self.dsn, connect_timeout=3, row_factory=dict_row)

    def original_snapshot(self):
        with self.connection() as conn:
            result = {}
            for table in ("app_users", "documents"):
                rows = conn.execute(sql.SQL("SELECT row_to_json(t) AS row FROM {} t ORDER BY id")
                                    .format(sql.Identifier(table))).fetchall()
                result[table] = {"count": len(rows), "sha256": canonical_hash(rows)}
            return result

    async def request(self, method, path, *, account=None, base=None, expected=None, **kwargs):
        account = account or self.primary
        headers = dict(kwargs.pop("headers", {}))
        if account:
            headers["Authorization"] = "Bearer " + account.token
        response = await self.http.request(method, (base or self.base) + path, headers=headers, **kwargs)
        if expected is not None and response.status_code != expected:
            raise AssertionError(f"{method} {path}: expected {expected}, got {response.status_code}: "
                                 + response.text[:500])
        return response

    async def login(self):
        token = os.environ.get("REDIS_DEMO_TOKEN", "")
        username = self.args.username or os.environ.get("REDIS_DEMO_USERNAME", "")
        password = os.environ.get("REDIS_DEMO_PASSWORD", "")
        if not token:
            if not username or not password:
                raise ValueError("Set REDIS_DEMO_TOKEN or REDIS_DEMO_USERNAME/REDIS_DEMO_PASSWORD.")
            response = await self.request("POST", "/auth/login", expected=200,
                                          json={"username": username, "password": password})
            token = response.json()["token"]
        self.primary = Account("", token, username)
        response = await self.request("GET", "/auth/me", expected=200)
        user = response.json()
        if user["role"] != "admin":
            raise ValueError("The verification account must be an administrator in the disposable DB.")
        self.primary = Account(str(user["id"]), token, user["username"])
        for base in {self.base, self.peer, self.baseline} - {None}:
            await self.request("GET", "/auth/me", base=base, expected=200)
        self.check("authenticated_across_instances", {"instances": len({self.base, self.peer, self.baseline} - {None})})

    async def new_account(self, role="user"):
        username = f"redis_journey_{self.run_id}_{role}"
        password = secrets.token_urlsafe(24)
        body = {"username": username, "email": username + "@example.test", "password": password,
                "password_confirmation": password, "role": role}
        if role == "admin":
            invite = await self.request("POST", "/admin/invites", expected=201,
                                        json={"expires_in_days": 1})
            data = invite.json()
            if data.get("id"):
                self.created_invites.append(str(data["id"]))
            body["invite_code"] = data.get("code") or data.get("invite_code")
        response = await self.request("POST", "/auth/register", expected=201, json=body)
        value = response.json()
        account = Account(str(value["user"]["id"]), value["token"], username)
        self.created_users.append(account.id)
        return account

    async def status(self, base=None):
        response = await self.request("GET", "/admin/redis", base=base, expected=200)
        if any(word in response.text.lower() for word in ('"redis_url"', '"database_url"', '"password"')):
            raise AssertionError("Administrator Redis statistics must not expose connection credentials.")
        return response.json()

    def key(self, template, account=None):
        account = account or self.primary
        key = template.format(prefix=self.args.key_prefix, user_id=account.id)
        if not key.startswith(self.args.key_prefix + ":"):
            raise ValueError("Refusing to mutate Redis outside the explicit test prefix.")
        self.key_cleanup.add(key)
        return key

    async def taxonomy(self):
        first = await self.request("GET", "/taxonomy", expected=200)
        expected = first.json()
        second = await self.request("GET", "/taxonomy", base=self.peer, expected=200)
        if second.json() != expected or second.headers.get("x-cache", "").upper() != "HIT":
            raise AssertionError("The second API must return the same shared cached taxonomy with X-Cache: HIT.")
        self.check("shared_taxonomy_cache", {"first": first.headers.get("x-cache"),
                                            "peer": second.headers.get("x-cache"),
                                            "payload_sha256": canonical_hash(expected)})
        self.taxonomy_restore = expected
        changed = {"groups": [*expected["groups"], {
            "parent": "Redis verification " + self.run_id,
            "children": ["Synthetic temporary classification"],
            "source_ref": "software verification only",
        }]}
        try:
            written = await self.request("PUT", "/admin/taxonomy", expected=200, json=changed)
            peer_read = await self.request("GET", "/taxonomy", base=self.peer, expected=200)
            if peer_read.json() != written.json():
                raise AssertionError("Peer API served stale taxonomy after the administrator update.")
            self.check("administrator_update_invalidates_peer_cache")
        finally:
            await self.request("PUT", "/admin/taxonomy", expected=200, json=expected)
            self.taxonomy_restore = None
        restored = await self.request("GET", "/taxonomy", expected=200)
        if restored.json() != expected:
            raise AssertionError("The original test taxonomy was not restored.")
        return expected

    async def batch(self, base, payload_hash, requests, concurrency):
        semaphore = asyncio.Semaphore(concurrency)
        records = []

        async def one():
            async with semaphore:
                start = time.perf_counter()
                response = await self.request("GET", "/taxonomy", base=base)
                elapsed = (time.perf_counter() - start) * 1000
                valid = response.status_code == 200 and canonical_hash(response.json()) == payload_hash
                records.append((elapsed, response.status_code, valid, response.headers.get("x-cache", "unknown")))

        begin = time.perf_counter()
        before = await self.status(base)
        await asyncio.gather(*(one() for _ in range(requests)))
        after = await self.status(base)
        elapsed = time.perf_counter() - begin
        latencies = [r[0] for r in records]
        if not all(r[2] for r in records):
            raise AssertionError(f"Benchmark returned wrong content/errors: {Counter(r[1] for r in records)}")
        return {"requests": requests, "concurrency": concurrency, "all_contents_correct": True,
                "status_codes": dict(Counter(str(r[1]) for r in records)),
                "cache_statuses": dict(Counter(r[3] for r in records)),
                "p50_ms": round(statistics.median(latencies), 3),
                "p95_ms": round(percentile(latencies, .95), 3),
                "observed_requests_per_second": round(requests / elapsed, 2),
                "loader_calls": metric(after, self.args.loader_counter) - metric(before, self.args.loader_counter),
                "raw_latencies_ms": [round(v, 3) for v in latencies]}

    async def benchmark(self, expected):
        if not self.baseline:
            self.report["benchmark"] = {"status": "not_run", "reason": "No explicit cache-disabled baseline API."}
            return
        digest = canonical_hash(expected)
        for base in (self.baseline, self.base):
            for _ in range(5):
                await self.request("GET", "/taxonomy", base=base, expected=200)
        runs = []
        for index in range(self.args.rounds):
            order = [("baseline", self.baseline), ("cached", self.base)]
            if index % 2:
                order.reverse()
            for label, base in order:
                row = await self.batch(base, digest, self.args.requests, self.args.concurrency)
                runs.append({"round": index + 1, "variant": label, **row})
        summary = {}
        for label in ("baseline", "cached"):
            rows = [r for r in runs if r["variant"] == label]
            summary[label] = {"requests": sum(r["requests"] for r in rows),
                              "loader_calls": sum(r["loader_calls"] for r in rows),
                              "median_round_p50_ms": round(statistics.median(r["p50_ms"] for r in rows), 3),
                              "median_round_p95_ms": round(statistics.median(r["p95_ms"] for r in rows), 3)}
        baseline, cached = summary["baseline"], summary["cached"]
        if baseline["loader_calls"] < baseline["requests"] or cached["loader_calls"] != 0:
            raise AssertionError(f"Expected baseline loads for every request and zero warm cached loads: {summary}")
        summary["loader_call_reduction_percent"] = round(
            100 * (1 - cached["loader_calls"] / baseline["loader_calls"]), 2)
        for field in ("median_round_p50_ms", "median_round_p95_ms"):
            summary[field + "_change_percent"] = round(100 * (cached[field] / baseline[field] - 1), 2)
        self.report["benchmark"] = {"method": "Alternating AB/BA rounds, identical content/authenticated HTTP; "
                                             "not model latency", "summary": summary, "runs": runs}
        self.check("warm_cache_reduces_taxonomy_loader_calls", summary)

    async def rate_limits(self):
        await self.redis.ping()
        demo_key = self.key(self.args.demo_key_template)
        await self.redis.delete(demo_key)
        start = time.perf_counter()

        async def one(index):
            base = self.base if index % 2 == 0 else self.peer
            response = await self.request("POST", "/admin/redis/limited-ping", base=base)
            return response

        responses = await asyncio.gather(*(one(i) for i in range(40)))
        codes = Counter(r.status_code for r in responses)
        expected = {200: self.args.demo_limit, 429: 40 - self.args.demo_limit}
        if dict(codes) != expected:
            raise AssertionError(f"Shared demo quota mismatch: expected {expected}, actual {dict(codes)}")
        if any(int(r.headers.get("retry-after", "0")) <= 0 for r in responses if r.status_code == 429):
            raise AssertionError("429 must include a positive Retry-After.")
        ttl = await self.redis.pttl(demo_key)
        if ttl <= 0:
            raise AssertionError("The demo quota key must have a finite TTL.")
        second = await self.new_account("admin")
        self.secondary = second
        self.key(self.args.demo_key_template, second)
        independent = await self.request("POST", "/admin/redis/limited-ping", account=second,
                                         base=self.peer, expected=200)
        reader = await self.new_account("user")
        self.reader = reader
        await self.request("GET", "/admin/redis", account=reader, expected=403)
        await self.request("POST", "/admin/redis/limited-ping", account=reader, expected=403)
        anonymous = await self.http.get(self.base + "/admin/redis")
        if anonymous.status_code != 401:
            raise AssertionError("Redis diagnostics must require authentication.")
        self.check("two_instances_atomic_quota", {"requests": 40, "instances": len({self.base, self.peer}),
                                                 "status_codes": dict(codes), "ttl_ms": ttl,
                                                 "elapsed_ms": round((time.perf_counter() - start) * 1000, 2)})
        self.check("different_user_has_independent_quota", {"http_status": independent.status_code})
        self.check("redis_diagnostics_and_demo_require_admin")

    async def concurrent_readers(self, initial_task_status):
        accounts = [a for a in (self.primary, self.secondary, self.reader) if a is not None]
        rows = []

        async def browse(account, index):
            for number in range(20):
                path = "/taxonomy" if number % 2 == 0 else "/documents/search"
                start = time.perf_counter()
                response = await self.request("GET", path, account=account,
                                              base=self.base if index % 2 == 0 else self.peer)
                rows.append((response.status_code, (time.perf_counter() - start) * 1000))
                await asyncio.sleep(.03)

        await asyncio.gather(*(browse(account, index) for index, account in enumerate(accounts)))
        if not all(code == 200 for code, _ in rows):
            raise AssertionError(f"Readers failed during real PDF indexing: {Counter(code for code, _ in rows)}")
        self.check("authenticated_readers_during_real_pdf_indexing", {
            "accounts": len(accounts), "requests": len(rows), "all_200": True,
            "task_status_at_read_start": initial_task_status,
            "task_active_at_read_start": initial_task_status in ("queued", "running"),
            "p50_ms": round(statistics.median(ms for _, ms in rows), 3),
            "p95_ms": round(percentile([ms for _, ms in rows], .95), 3),
            "note": "Concurrent browsing alongside PDF workflow; actual task state at start recorded. Not LLM throughput.",
        })

    async def upload(self):
        marker = "REDISJOURNEY" + self.run_id.upper()
        data = pdf_bytes(marker)
        (self.output.parent / (marker + ".pdf")).write_bytes(data)
        key = "redis-journey-" + self.run_id
        files = {"file": (marker + ".pdf", data, "application/pdf")}
        started = time.perf_counter()
        first = await self.request("POST", "/admin/documents", expected=202,
                                    headers={"Idempotency-Key": key}, files=files)
        row = first.json()
        document_id, task_id = row["id"], row["task_id"]
        self.created_documents.append(document_id)
        second = await self.request("POST", "/admin/documents", base=self.peer, expected=202,
                                     headers={"Idempotency-Key": key}, files=files)
        replay = second.json()
        if replay["id"] != document_id or replay["task_id"] != task_id or not replay["replayed"]:
            raise AssertionError("Repeated upload did not replay the same document/task.")
        self.check("real_pdf_idempotent_upload", {"document_id": document_id, "task_id": task_id,
                                                 "file_bytes": len(data)})
        with self.connection() as conn:
            initial_task_status = conn.execute("SELECT status FROM document_tasks WHERE id=%s", (task_id,)).fetchone()["status"]
        readers = asyncio.create_task(self.concurrent_readers(initial_task_status))
        deadline = time.monotonic() + self.args.processing_timeout
        seen = []
        try:
            while time.monotonic() < deadline:
                response = await self.request("GET", f"/admin/documents/{document_id}/processing-status", expected=200)
                status = response.json()
                if not seen or seen[-1] != status["status"]:
                    seen.append(status["status"])
                    print("PDF processing:", status["status"], flush=True)
                task = status.get("task") or {}
                if task.get("status") == "failed":
                    raise AssertionError("Real PDF processing failed: " + str(task.get("last_error")))
                if task.get("status") == "succeeded":
                    break
                await asyncio.sleep(.5)
            else:
                raise TimeoutError("Real PDF indexing did not finish within the verification time budget.")
        finally:
            await readers
        chunks = (await self.request("GET", f"/documents/{document_id}/chunks", expected=200)).json()
        text = "\n".join(c["text"] for c in chunks)
        if marker not in text or "637421" not in text:
            raise AssertionError("Persisted chunk text does not contain the actual fixture facts.")
        file = await self.request("GET", f"/documents/{document_id}/file", base=self.peer, expected=200)
        if hashlib.sha256(file.content).digest() != hashlib.sha256(data).digest():
            raise AssertionError("Downloaded file differs from the uploaded PDF.")
        vectors = []
        with self.connection() as conn:
            tables = conn.execute("SELECT table_name FROM information_schema.columns "
                                  "WHERE table_schema='public' AND column_name='embedding'").fetchall()
            for table in tables:
                result = conn.execute(sql.SQL(
                    "SELECT count(*) AS count, min(vector_dims(e.embedding::vector)) AS dimensions "
                    "FROM {} e JOIN document_chunks c ON c.id=e.chunk_id "
                    "WHERE c.document_id=%s AND e.embedding_model=%s"
                ).format(sql.Identifier(table["table_name"])),
                    (document_id, task.get("result_json", {}).get("embedding_model"))).fetchone()
                if result["count"]:
                    vectors.append({"table": table["table_name"], **dict(result)})
            document = conn.execute("SELECT status, file_path FROM documents WHERE id=%s", (document_id,)).fetchone()
        if document["status"] != "ready" or sum(v["count"] for v in vectors) != len(chunks):
            raise AssertionError("Every persisted chunk must have one vector for the actual active model.")
        self.check("real_pdf_text_and_vectors_verified", {"pages": 2, "chunks": len(chunks),
                                                          "vectors": vectors, "states": seen,
                                                          "attempts": task.get("attempts"),
                                                          "elapsed_seconds": round(time.perf_counter() - started, 2),
                                                          "download_sha256_matches": True})
        return document_id

    def chat_counts(self):
        with self.connection() as conn:
            return {table: conn.execute(sql.SQL("SELECT count(*) AS n FROM {}").format(sql.Identifier(table)))
                    .fetchone()["n"] for table in ("chat_sessions", "chat_messages", "documents", "document_tasks")}

    async def rejected_chat_has_no_side_effects(self, document_id, expected_status=429):
        if expected_status == 429:
            key = self.key(self.args.chat_key_template)
            await self.redis.set(key, self.args.chat_limit, ex=60)
        before = self.chat_counts()
        results = {}
        for path, base in (("/chat", self.base), ("/chat/stream", self.peer)):
            response = await self.request("POST", path, base=base, expected=expected_status,
                                          json={"question": "What is the annual budget?", "document_ids": [document_id]})
            if "text/event-stream" in response.headers.get("content-type", ""):
                raise AssertionError("Admission refusal must occur before SSE starts.")
            if int(response.headers.get("retry-after", "0")) <= 0:
                raise AssertionError("Admission refusal must include a positive Retry-After.")
            results[path] = response.status_code
        after = self.chat_counts()
        if before != after:
            raise AssertionError(f"Rejected chat created persisted side effects: {before} -> {after}")
        name = ("chat_and_stream_share_quota_before_business" if expected_status == 429
                else "redis_outage_chat_and_stream_deny_before_business")
        self.check(name, {"statuses": results,
                                                                    "database_counts_unchanged": True,
                                                                    "note": "No answer-quality claim; admission denied before model execution."})

    async def rejected_upload_has_no_side_effects(self, expected_status=429):
        if expected_status == 429:
            key = self.key(self.args.upload_key_template)
            await self.redis.set(key, self.args.upload_limit, ex=60)
        before = self.chat_counts()
        data = pdf_bytes("REJECTED" + self.run_id.upper())
        response = await self.request("POST", "/admin/documents", expected=expected_status,
                                      headers={"Idempotency-Key": "denied-" + self.run_id},
                                      files={"file": ("denied-policy.pdf", data, "application/pdf")})
        if int(response.headers.get("retry-after", "0")) <= 0:
            raise AssertionError("Admission refusal must include a positive Retry-After.")
        after = self.chat_counts()
        if before != after:
            raise AssertionError("Rejected upload registered a document/task or changed chat counts.")
        name = ("upload_quota_denies_before_registration" if expected_status == 429
                else "redis_outage_upload_denies_before_registration")
        self.check(name, {"http_status": response.status_code,
                                                               "database_counts_unchanged": True,
                                                               "note": "Multipart reception may precede route admission; byte middleware remains necessary."})

    async def outage(self):
        response = await self.request("GET", "/taxonomy", expected=200)
        if response.headers.get("x-cache", "").upper() == "HIT":
            raise AssertionError("Outage mode requires Redis actually unavailable, not a cached HIT.")
        for base in {self.base, self.peer}:
            denied = await self.request("POST", "/admin/redis/limited-ping", base=base, expected=503)
            if int(denied.headers.get("retry-after", "0")) < 1:
                raise AssertionError("503 must give a positive Retry-After.")
        await self.request("GET", "/documents", expected=200)
        await self.rejected_chat_has_no_side_effects(str(uuid4()), expected_status=503)
        await self.rejected_upload_has_no_side_effects(expected_status=503)
        self.check("redis_outage_cache_falls_back_and_expensive_admission_fails_closed",
                   {"taxonomy_status": response.status_code, "cache_status": response.headers.get("x-cache"),
                    "limited_ping_status": 503, "catalogue_status": 200})
        if self.frontend:
            await self.frontend_outage()

    async def frontend_outage(self):
        account = self.primary
        username = self.args.username or os.environ.get("REDIS_DEMO_USERNAME", "")
        password = os.environ.get("REDIS_DEMO_PASSWORD", "")
        if username and password:
            login = await self.http.post(self.frontend + "/auth/login",
                                         json={"username": username, "password": password})
            if login.status_code != 200:
                raise AssertionError("Frontend proxy login failed.")
            account = Account(self.primary.id, login.json()["token"], username)
            auth_flow = "password login"
        else:
            await self.request("GET", "/auth/me", account=account, base=self.frontend, expected=200)
            auth_flow = "existing token validation"
        started = time.perf_counter()
        taxonomy = await self.request("GET", "/taxonomy", account=account, base=self.frontend, expected=200)
        elapsed = (time.perf_counter() - started) * 1000
        if taxonomy.headers.get("x-cache", "").upper() != "BYPASS":
            raise AssertionError("Frontend proxy did not bypass stopped Redis.")
        catalogue = await self.request("GET", "/documents", account=account,
                                       base=self.frontend, expected=200)
        self.check("frontend_proxy_auth_and_reads_during_redis_outage", {
            "origin": self.frontend, "authentication": auth_flow, "authentication_status": 200,
            "taxonomy_status": taxonomy.status_code, "taxonomy_cache": taxonomy.headers.get("x-cache"),
            "taxonomy_elapsed_ms": round(elapsed, 3), "catalogue_status": catalogue.status_code,
            "taxonomy_groups": len(taxonomy.json()["groups"]),
        })

    async def recovery(self):
        await self.redis.ping()
        one = await self.request("GET", "/taxonomy", expected=200)
        two = await self.request("GET", "/taxonomy", base=self.peer, expected=200)
        if two.headers.get("x-cache", "").upper() != "HIT" or one.json() != two.json():
            raise AssertionError("Cache did not recover after Redis restart.")
        state = await self.status()
        if state.get("status") != "healthy":
            raise AssertionError("Redis diagnostics did not recover to healthy.")
        self.check("redis_recovery_cache_operational", {
            "primary_cache": one.headers.get("x-cache"), "peer_cache": two.headers.get("x-cache"),
            "redis_status": state["status"],
        })
        key = self.key(self.args.demo_key_template)
        existed = bool(await self.redis.exists(key))
        if existed:
            # Explicitly start a fresh isolated test window; do not claim Redis
            # restart clears persistence or that this verifies natural expiry.
            await self.redis.delete(key)
        admitted = await self.request("POST", "/admin/redis/limited-ping", expected=200)
        peer_admitted = await self.request("POST", "/admin/redis/limited-ping", base=self.peer, expected=200)
        ttl = await self.redis.pttl(key)
        if ttl <= 0 or admitted.json().get("remaining") != self.args.demo_limit - 1:
            raise AssertionError("Recovered admission did not establish the expected fresh quota window.")
        if peer_admitted.json().get("remaining") != self.args.demo_limit - 2:
            raise AssertionError("Recovered peer admission did not share the quota window.")
        self.check("redis_recovery_new_demo_window", {
            "http_statuses": [admitted.status_code, peer_admitted.status_code],
            "remaining": [admitted.json()["remaining"], peer_admitted.json()["remaining"]],
            "ttl_ms": ttl, "preexisting_test_key_reset": existed,
            "note": "Verifies admission after restart; does not claim restart clears persisted counters or natural TTL expiry.",
        })
        if self.frontend:
            first = await self.request("GET", "/taxonomy", base=self.frontend, expected=200)
            second = await self.request("GET", "/taxonomy", base=self.frontend, expected=200)
            if second.headers.get("x-cache", "").upper() != "HIT" or first.json() != second.json():
                raise AssertionError("Frontend proxy cache did not recover.")
            self.check("frontend_proxy_cache_recovered", {
                "origin": self.frontend, "statuses": [first.status_code, second.status_code],
                "cache_statuses": [first.headers.get("x-cache"), second.headers.get("x-cache")],
                "same_payload": True,
            })

    async def cleanup(self):
        errors = []
        if self.taxonomy_restore:
            try:
                await self.request("PUT", "/admin/taxonomy", expected=200, json=self.taxonomy_restore)
            except Exception as exc:
                errors.append("taxonomy restore: " + str(exc))
        if not self.args.keep_fixtures:
            for document_id in self.created_documents:
                try:
                    await self.request("DELETE", f"/admin/documents/{document_id}", expected=204)
                except Exception as exc:
                    errors.append("fixture document cleanup: " + str(exc))
            try:
                with self.connection() as conn:
                    if self.created_invites:
                        conn.execute("DELETE FROM admin_invites WHERE id=ANY(%s::uuid[])", (self.created_invites,))
                    if self.created_users:
                        conn.execute("DELETE FROM app_users WHERE id=ANY(%s::uuid[])", (self.created_users,))
            except Exception as exc:
                errors.append("fixture account cleanup: " + str(exc))
        try:
            if self.key_cleanup:
                await self.redis.delete(*self.key_cleanup)
        except redis.RedisError:
            pass  # Redis is intentionally stopped in outage mode; all keys have TTL.
        await self.redis.aclose()
        await self.http.aclose()
        self.report["cleanup"] = {"kept_fixtures": self.args.keep_fixtures, "errors": errors}
        return errors

    async def run(self):
        snapshot = self.original_snapshot()
        error = None
        try:
            await self.login()
            if self.args.mode == "outage":
                await self.outage()
            elif self.args.mode == "recovery":
                await self.recovery()
            elif self.args.mode == "cache":
                await self.redis.ping()
                expected = await self.taxonomy()
                await self.benchmark(expected)
                reader = await self.new_account("user")
                await self.request("GET", "/admin/redis", account=reader, expected=403)
                anonymous = await self.http.get(self.base + "/admin/redis")
                if anonymous.status_code != 401:
                    raise AssertionError("Redis diagnostics must require authentication.")
                self.check("cache_diagnostics_require_admin")
            elif self.args.mode == "admission":
                await self.redis.ping()
                await self.rate_limits()
                await self.rejected_chat_has_no_side_effects(self.args.document_id or str(uuid4()))
                await self.rejected_upload_has_no_side_effects()
            else:
                await self.redis.ping()
                expected = await self.taxonomy()
                await self.benchmark(expected)
                await self.rate_limits()
                document_id = await self.upload()
                await self.rejected_chat_has_no_side_effects(document_id)
                await self.rejected_upload_has_no_side_effects()
            self.report["passed"] = True
        except Exception as exc:
            error = exc
            message = str(exc).replace(self.args.database_url, "[database-url]").replace(self.args.redis_url, "[redis-url]")
            self.report["passed"] = False
            self.report["failure"] = {"type": type(exc).__name__, "message": message}
        finally:
            errors = await self.cleanup()
            if not self.args.keep_fixtures:
                after = self.original_snapshot()
                self.report["original_records_unchanged"] = snapshot == after
                self.report["original_counts"] = {k: v["count"] for k, v in snapshot.items()}
                if snapshot != after:
                    errors.append("Original app_users/documents snapshot changed after cleanup.")
            if errors:
                self.report["passed"] = False
            self.report["finished_at_utc"] = datetime.now(UTC).isoformat()
            self.save()
        print(json.dumps({"run_id": self.run_id, "passed": self.report.get("passed"),
                          "checks": list(self.report["checks"]), "report": str(self.output),
                          "failure": self.report.get("failure"), "cleanup_errors": errors}, indent=2), flush=True)
        return 0 if self.report.get("passed") and error is None else 1


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--base-url", required=True)
    p.add_argument("--peer-url")
    p.add_argument("--baseline-url")
    p.add_argument("--frontend-url", help="Optional same-origin frontend proxy for outage verification.")
    p.add_argument("--database-url", default=os.environ.get("TEST_DATABASE_URL", ""))
    p.add_argument("--redis-url", default=os.environ.get("TEST_REDIS_URL", "redis://127.0.0.1:6379/0"))
    p.add_argument("--key-prefix", required=True)
    p.add_argument("--username")
    p.add_argument("--output", default="tmp/redis-demo/journey.json")
    p.add_argument("--mode", choices=("cache", "admission", "functional", "outage", "recovery"), default="functional")
    p.add_argument("--loader-counter", default="taxonomy_loader_calls")
    p.add_argument("--demo-key-template", default="{prefix}:rl:v1:demo:user:{user_id}")
    p.add_argument("--chat-key-template", default="{prefix}:rl:v1:chat:user:{user_id}")
    p.add_argument("--upload-key-template", default="{prefix}:rl:v1:upload:user:{user_id}")
    p.add_argument("--demo-limit", type=int, default=10)
    p.add_argument("--chat-limit", type=int, default=10)
    p.add_argument("--upload-limit", type=int, default=5)
    p.add_argument("--document-id", help="Optional existing verification document UUID for admission-only mode.")
    p.add_argument("--requests", type=int, default=200)
    p.add_argument("--concurrency", type=int, default=10)
    p.add_argument("--rounds", type=int, default=3)
    p.add_argument("--processing-timeout", type=float, default=180)
    p.add_argument("--keep-fixtures", action="store_true")
    return p


if __name__ == "__main__":
    args = parser().parse_args()
    if not 1 <= args.demo_limit < 40 or min(args.requests, args.concurrency, args.rounds) <= 0:
        raise SystemExit("Use positive benchmark sizes and a demo limit between 1 and 39.")
    raise SystemExit(asyncio.run(Journey(args).run()))
