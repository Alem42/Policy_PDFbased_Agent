"""Apply only additive evaluation migrations, never database/init.sql.

python -m scripts.migrate_evaluation [--check]
"""
import argparse
import hashlib
import json
from pathlib import Path

from app.core.database import get_connection

VERSIONS = ("029_add_evaluation.sql", "030_evidence_experiments.sql")
TABLES = (
    "evaluation_settings", "evaluation_runs", "evaluation_reviews",
    "evaluation_corpus_documents", "evaluation_indexes", "evaluation_index_chunks",
    "evaluation_trials", "evaluation_artifacts", "evidence_validation_settings",
)


def migrate(check=False):
    applied = []
    with get_connection() as conn:
        if not check:
            conn.execute("SELECT pg_advisory_xact_lock(hashtext('policy-evaluation-migrations'))")
            conn.execute("CREATE TABLE IF NOT EXISTS app_schema_migrations (version text PRIMARY KEY,"
                         "sha256 text NOT NULL, applied_at timestamptz NOT NULL DEFAULT now())")
            for version in VERSIONS:
                source = (Path(__file__).resolve().parents[1] / "database/migrations" / version).read_bytes()
                digest = hashlib.sha256(source).hexdigest()
                old = conn.execute("SELECT sha256 FROM app_schema_migrations WHERE version=%s", (version,)).fetchone()
                if old and old['sha256'] != digest:
                    raise RuntimeError(f"Previously applied migration changed: {version}")
                if not old:
                    conn.execute(source.decode('utf-8'))
                    conn.execute("INSERT INTO app_schema_migrations(version,sha256) VALUES (%s,%s)", (version,digest))
                    applied.append(version)
        tables = {name: bool(conn.execute("SELECT to_regclass(%s) AS t", (name,)).fetchone()['t']) for name in TABLES}
    result = {"applied": applied, "tables": tables, "complete": all(tables.values())}
    print(json.dumps(result, indent=2))
    if not result['complete']:
        raise RuntimeError("Evaluation schema is incomplete; run without --check.")


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    migrate(parser.parse_args().check)
