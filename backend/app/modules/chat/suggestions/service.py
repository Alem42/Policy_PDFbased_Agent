"""Public facade for suggestion configuration (admin page + generator read this)."""

from __future__ import annotations

from app.modules.chat.suggestions.config import SuggestionConfig
from app.modules.chat.suggestions.repository import suggestion_settings_repository


def active_config() -> SuggestionConfig:
    return suggestion_settings_repository.load()


def update_config(partial: dict) -> SuggestionConfig:
    """Merge a partial update over the current config and persist it."""
    current = active_config().model_dump()
    merged = {**current, **{k: v for k, v in partial.items() if v is not None}}
    config = SuggestionConfig(**merged)
    suggestion_settings_repository.save(config)
    return config


def status() -> dict:
    """Config for the admin UI."""
    config = active_config()
    return {"settings": config.model_dump(), "status": {"enabled": config.enabled}}
