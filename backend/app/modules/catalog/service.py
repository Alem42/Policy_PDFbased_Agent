"""Public model-catalog API.

The catalog answers "which providers/models exist for a capability, and at what
base URL", so the embedding/reranker pages can offer a pick-a-model dropdown
(keys are entered centrally on the LLM & API keys page, never here).
"""

from __future__ import annotations

import re

from app.modules.catalog.data import CAPABILITIES
from app.modules.catalog.repository import (
    catalog_entries,
    invalidate_catalog_cache,
    model_catalog_repository,
)

_ASCII_WORD = re.compile(r"[A-Za-z]")
_HAN_CHARACTER = re.compile(r"[\u3400-\u9fff]")
_ENGLISH_TRANSLATIONS = {
    "智谱": "Zhipu",
    "可选维度 256/512/1024/2048": "Optional dimensions: 256/512/1024/2048",
    "固定 1024 维": "Fixed at 1024 dimensions",
    "文本重排序": "Text reranking",
    "对话补全": "Chat completions",
    "对话补全（异步）": "Async chat completions",
    "图像生成": "Image generation",
    "图像生成（异步）": "Async image generation",
    "文本分词器": "Text tokenizer",
    "文本转语音": "Text to speech",
    "语音转文本": "Speech to text",
    "音色复刻": "Voice cloning",
    "音色列表": "Voice list",
    "删除音色": "Delete voice",
    "文档解析": "Document parsing",
    "查询异步结果": "Async result lookup",
    "视频生成（异步）": "Async video generation",
}


def _is_chinese_only(value: str | None) -> bool:
    return bool(value and _HAN_CHARACTER.search(value) and not _ASCII_WORD.search(value))


def _humanize(value: str) -> str:
    return value.replace("_", " ").replace("-", " ").strip().title()


def _english_display(value: str | None, *, fallback: str) -> str | None:
    if not value or not _is_chinese_only(value):
        return value
    return _ENGLISH_TRANSLATIONS.get(value, fallback)


def _present_entry(entry: dict) -> dict:
    """Add English UI labels without changing persisted lookup identifiers."""
    capability = _humanize(entry["capability"])
    endpoint = entry.get("endpoint") or ""
    provider_fallback = _humanize(entry["provider"]) or "Provider"
    model_fallback = f"{capability} endpoint"
    if endpoint:
        model_fallback = f"{model_fallback} ({endpoint})"
    return {
        **entry,
        "provider_label_display": _english_display(
            entry.get("provider_label"),
            fallback=provider_fallback,
        ),
        "model_display": _english_display(entry.get("model"), fallback=model_fallback),
        "notes_display": _english_display(
            entry.get("notes"),
            fallback=f"{capability} capability",
        ),
    }


def get_catalog(capability: str | None = None) -> dict:
    return {
        "capabilities": CAPABILITIES,
        "entries": [_present_entry(entry) for entry in catalog_entries(capability)],
    }


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
    invalidate_catalog_cache()
    return entry
