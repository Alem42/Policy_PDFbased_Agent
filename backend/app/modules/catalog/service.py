"""Public model-catalog API.

The catalog answers "which providers/models exist for a capability, and at what
base URL", so the embedding/reranker pages can offer a pick-a-model dropdown
(keys are entered centrally on the LLM & API keys page, never here).
"""

from __future__ import annotations

from app.modules.catalog.data import CAPABILITIES
from app.modules.catalog.repository import catalog_entries, model_catalog_repository


def get_catalog(capability: str | None = None) -> dict:
    return {"capabilities": CAPABILITIES, "entries": catalog_entries(capability)}


def find_entry(provider: str, model: str, capability: str | None = None) -> dict | None:
    for entry in catalog_entries(capability):
        if entry["provider"] == provider and entry["model"] == model:
            return entry
    return None


def resolve_base_url(provider: str, model: str, capability: str | None = None) -> str | None:
    entry = find_entry(provider, model, capability)
    return entry["base_url"] if entry else None


def add_entry(payload: dict) -> dict:
    required = ("provider", "capability", "model")
    if any(not str(payload.get(field, "")).strip() for field in required):
        raise ValueError("provider, capability and model are required.")
    entry = {
        "provider": payload["provider"].strip(),
        "provider_label": (payload.get("provider_label") or payload["provider"]).strip(),
        "capability": payload["capability"].strip(),
        "model": payload["model"].strip(),
        "base_url": (payload.get("base_url") or "").strip(),
        "endpoint": (payload.get("endpoint") or "").strip(),
        "dimensions": payload.get("dimensions"),
        "openai_compatible": bool(payload.get("openai_compatible", True)),
        "notes": payload.get("notes"),
    }
    model_catalog_repository.add(entry)
    return entry
