from app.core.database import get_connection
from app.modules.evaluation.repository import encode


def _owned(conn, run):
    if not conn.execute(
        "SELECT id FROM evaluation_runs WHERE id=%s AND lease_token=%s AND "
        "status='running' FOR UPDATE",
        (run["id"], run["lease_token"]),
    ).fetchone():
        raise RuntimeError("Experiment cancelled or lease lost.")


def progress(run, metrics):
    with get_connection() as conn:
        _owned(conn, run)
        conn.execute(
            "UPDATE evaluation_runs SET metrics=%s::jsonb WHERE id=%s", (encode(metrics), run["id"])
        )


def artifact(run, name, payload):
    with get_connection() as conn:
        _owned(conn, run)
        conn.execute(
            "INSERT INTO evaluation_artifacts(run_id,name,payload) VALUES (%s,%s,%s::jsonb) "
            "ON CONFLICT(run_id,name) DO UPDATE SET payload=EXCLUDED.payload,updated_at=now()",
            (run["id"], name, encode(payload)),
        )


def artifacts(identifier):
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT name,payload FROM evaluation_artifacts WHERE run_id=%s", (identifier,)
        ).fetchall()
    return {r["name"]: r["payload"] for r in rows}


def trial(run, variant, case_id, result):
    with get_connection() as conn:
        _owned(conn, run)
        conn.execute(
            "INSERT INTO evaluation_trials(run_id,variant_id,case_id,result) "
            "VALUES (%s,%s,%s,%s::jsonb) "
            "ON CONFLICT(run_id,variant_id,case_id) DO UPDATE SET "
            "result=EXCLUDED.result,updated_at=now()",
            (run["id"], variant, case_id, encode(result)),
        )


def trials(identifier, variant=None):
    with get_connection() as conn:
        return [
            r["result"]
            for r in conn.execute(
                "SELECT result FROM evaluation_trials WHERE run_id=%s AND (%s::text"
                " IS NULL OR variant_id=%s) ORDER BY variant_id,case_id",
                (identifier, variant, variant),
            ).fetchall()
        ]
