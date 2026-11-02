"""Read recorded usage without sending any model requests or printing credentials."""
import json
from collections import defaultdict
from pathlib import Path

from app.core.database import get_connection


def main():
    totals = defaultdict(lambda: {"calls": 0, "input_tokens": 0, "output_tokens": 0, "total_tokens": 0})
    seen = set()

    def add(identifier, model, usage):
        if identifier in seen:
            return
        seen.add(identifier)
        row = totals[model]
        row["calls"] += 1
        for key in ("input_tokens", "output_tokens", "total_tokens"):
            row[key] += (usage or {}).get(key, 0)

    def walk(value):
        if isinstance(value, dict):
            if value.get("call_id") and value.get("model") and value.get("usage"):
                add(value["call_id"], value["model"], value["usage"])
            for item in value.values():
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    with get_connection() as conn:
        runs = conn.execute("SELECT id,status,config,results FROM evaluation_runs").fetchall()
        for run in runs:
            walk(run["results"])
            for case_id, result in run["results"].items():
                if result.get("token_usage"):
                    add(f"generation:{run['id']}:{case_id}", run["config"]["model"], result["token_usage"])
        for artifact in conn.execute("SELECT payload FROM evaluation_artifacts").fetchall():
            walk(artifact["payload"])
    result = {
        "recorded_usage_by_model": dict(totals),
        "active_runs": sum(r["status"] in ("queued", "running") for r in runs),
        "notes": "Recorded lower bound only: old unprotected generation, failed calls and cancelled in-flight requests may lack telemetry. Cached plan call IDs are deduplicated. No invoice/price estimate.",
    }
    path = Path("eval-results/experiment-v2/recorded-api-usage.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf8")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
