import json
from uuid import uuid4

from app.core.database import get_connection


def encode(value):
    return json.dumps(value, ensure_ascii=False, default=str)


def create(config, snapshot, cases, actor):
    identifier = str(uuid4())
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO evaluation_runs (id,config,snapshot,cases,requested_by) "
            "VALUES (%s,%s::jsonb,%s::jsonb,%s::jsonb,%s)",
            (identifier, encode(config), encode(snapshot), encode(cases), actor),
        )
    return identifier


def get(identifier):
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM evaluation_runs WHERE id=%s", (identifier,)).fetchone()
        if not row:
            raise LookupError("Evaluation run not found.")
        row["reviews"] = conn.execute(
            "SELECT case_id,score,comment,updated_at FROM evaluation_reviews WHERE run_id=%s",
            (identifier,),
        ).fetchall()
    return dict(row)


def completed_case_ids(identifier):
    """Include saved outputs from every continuation batch, without copying them."""
    with get_connection() as conn:
        rows = conn.execute(
            "WITH RECURSIVE family AS ("
            "SELECT id,results FROM evaluation_runs WHERE id=%s "
            "UNION ALL SELECT r.id,r.results FROM evaluation_runs r "
            "JOIN family f ON r.config->>'reuse_run_id'=f.id::text) "
            "SELECT DISTINCT item.key AS case_id FROM family "
            "CROSS JOIN LATERAL jsonb_each(results) item "
            "WHERE item.value->>'status'='completed'",
            (identifier,),
        ).fetchall()
    return {r["case_id"] for r in rows}


def recent():
    with get_connection() as conn:
        return conn.execute(
            "SELECT id,status,config,metrics,error,created_at,finished_at, "
            "(SELECT count(*) FROM jsonb_object_keys(results)) AS completed FROM evaluation_runs "
            "ORDER BY created_at DESC LIMIT 25"
        ).fetchall()


def claim():
    token = str(uuid4())
    with get_connection() as conn:
        return conn.execute(
            "UPDATE evaluation_runs SET status='running',lease_token=%s,"
            "lease_expires_at=now()+interval '90 seconds',started_at=COALESCE(started_at,now()) "
            "WHERE id=(SELECT id FROM evaluation_runs WHERE status='queued' OR "
            "(status='running' AND lease_expires_at<now()) ORDER BY created_at "
            "FOR UPDATE SKIP LOCKED LIMIT 1) RETURNING *",
            (token,),
        ).fetchone()


def heartbeat(run):
    with get_connection() as conn:
        return bool(
            conn.execute(
                "UPDATE evaluation_runs SET lease_expires_at=now()+interval '90 seconds' "
                "WHERE id=%s AND lease_token=%s AND status='running' RETURNING id",
                (run["id"], run["lease_token"]),
            ).fetchone()
        )


def record(run, result, metrics):
    with get_connection() as conn:
        row = conn.execute(
            "UPDATE evaluation_runs SET results=results || %s::jsonb,metrics=%s::jsonb "
            "WHERE id=%s AND lease_token=%s AND status='running' RETURNING id",
            (encode({result["case_id"]: result}), encode(metrics), run["id"], run["lease_token"]),
        ).fetchone()
        if not row:
            raise RuntimeError("Evaluation lease lost or run cancelled.")


def finish(run, status="completed", error=None):
    with get_connection() as conn:
        conn.execute(
            "UPDATE evaluation_runs SET status=%s,error=%s,finished_at=now(),"
            "lease_expires_at=NULL WHERE id=%s AND lease_token=%s AND status='running'",
            (status, error, run["id"], run["lease_token"]),
        )


def release(run):
    with get_connection() as conn:
        conn.execute(
            "UPDATE evaluation_runs SET lease_expires_at=now() WHERE id=%s AND lease_token=%s",
            (run["id"], run["lease_token"]),
        )


def cancel(identifier):
    get(identifier)
    with get_connection() as conn:
        conn.execute(
            "UPDATE evaluation_runs SET status='cancelled',finished_at=now(),"
            "lease_token=NULL,lease_expires_at=NULL WHERE id=%s AND status IN ('queued','running')",
            (identifier,),
        )


def review(identifier, case_id, payload, actor):
    run = get(identifier)
    if case_id not in run["results"] or run["results"][case_id].get("status") != "completed":
        raise ValueError("Only completed case outputs can be reviewed.")
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO evaluation_reviews (run_id,case_id,score,comment,reviewer) "
            "VALUES (%s,%s,%s,%s,%s) ON CONFLICT (run_id,case_id) DO UPDATE "
            "SET score=EXCLUDED.score,comment=EXCLUDED.comment,"
            "reviewer=EXCLUDED.reviewer,updated_at=now()",
            (identifier, case_id, payload.score, payload.comment, actor),
        )
