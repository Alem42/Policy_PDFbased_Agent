"""Deterministic versions for prompts and behavior-affecting configuration."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any

# This version is intentionally explicit. Change it whenever prompt behavior
# changes so evaluations can compare runs without storing prompt text in events.
PROMPT_VERSION = "chat-prompts-v1"

_SECRET_FRAGMENTS = ("api_key", "apikey", "authorization", "password", "secret", "token")


def stable_configuration_version(configuration: Mapping[str, Any]) -> str:
    """Return a stable, secret-free fingerprint of runtime behavior settings."""

    safe_configuration = _without_secrets(configuration)
    encoded = json.dumps(
        safe_configuration,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()[:16]}"


def _without_secrets(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _without_secrets(item)
            for key, item in value.items()
            if not _looks_secret(str(key))
        }
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_without_secrets(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return repr(value)


def _looks_secret(key: str) -> bool:
    normalized = key.lower().replace("-", "_")
    return any(fragment in normalized for fragment in _SECRET_FRAGMENTS)
