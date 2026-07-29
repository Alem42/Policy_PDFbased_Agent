"""Export or import model providers and API endpoints as portable JSON.

API keys are intentionally excluded. Run from the backend directory:

    python scripts/model_catalog_transfer.py export --output model-catalog.json
    python scripts/model_catalog_transfer.py import --input model-catalog.json

Both commands use DATABASE_URL from the normal application environment.
Imports are idempotent upserts and do not delete rows already present online.
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from app.core.config import get_settings
from app.modules.catalog.repository import (
    invalidate_catalog_cache,
    invalidate_provider_cache,
    model_catalog_repository,
    model_provider_repository,
)

FORMAT_VERSION = 1


def build_export(providers: list[dict], endpoints: list[dict]) -> dict:
    return {
        "format": "model-catalog",
        "version": FORMAT_VERSION,
        "exported_at": datetime.now(UTC).isoformat(),
        "providers": providers,
        "endpoints": endpoints,
    }


def validate_import(payload: dict) -> tuple[list[dict], list[dict]]:
    if payload.get("format") != "model-catalog":
        raise ValueError("Input is not a model-catalog export.")
    if payload.get("version") != FORMAT_VERSION:
        raise ValueError(
            f"Unsupported model-catalog version: {payload.get('version')!r}."
        )
    providers = payload.get("providers")
    endpoints = payload.get("endpoints")
    if not isinstance(providers, list) or not isinstance(endpoints, list):
        raise ValueError("Export must contain provider and endpoint arrays.")

    for provider in providers:
        if not isinstance(provider, dict) or not provider.get("id") or not provider.get("label"):
            raise ValueError("Every provider requires id and label.")
    for endpoint in endpoints:
        required = ("provider", "capability", "model")
        if not isinstance(endpoint, dict) or any(not endpoint.get(field) for field in required):
            raise ValueError("Every endpoint requires provider, capability and model.")
    return providers, endpoints


def export_catalog(output_path: Path) -> tuple[int, int]:
    providers = model_provider_repository.list()
    endpoints = model_catalog_repository.list()
    payload = build_export(providers, endpoints)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return len(providers), len(endpoints)


def import_catalog(input_path: Path) -> tuple[int, int]:
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    providers, endpoints = validate_import(payload)

    # Providers must exist first because endpoint creation in the admin UI
    # validates against the registry. Repository upserts make reruns safe.
    for provider in providers:
        model_provider_repository.add(provider)
    for endpoint in endpoints:
        model_catalog_repository.add(endpoint)
    invalidate_provider_cache()
    invalidate_catalog_cache()
    return len(providers), len(endpoints)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Transfer model providers and endpoints without API keys."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    export_parser = subparsers.add_parser("export")
    export_parser.add_argument("--output", type=Path, required=True)
    import_parser = subparsers.add_parser("import")
    import_parser.add_argument("--input", type=Path, required=True)
    args = parser.parse_args()

    if not get_settings().database_enabled:
        parser.error("DATABASE_ENABLED must be true for catalog transfer.")

    if args.command == "export":
        providers, endpoints = export_catalog(args.output)
        print(
            f"Exported {providers} providers and {endpoints} endpoints to "
            f"{args.output.resolve()}."
        )
    else:
        providers, endpoints = import_catalog(args.input)
        print(f"Imported {providers} providers and {endpoints} endpoints.")


if __name__ == "__main__":
    main()
