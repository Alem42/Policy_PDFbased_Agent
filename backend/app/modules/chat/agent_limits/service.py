"""Public facade for agent tool-call limit configuration (admin page + policy read this)."""

from __future__ import annotations

from app.modules.chat.agent_limits.config import AgentToolLimitsConfig
from app.modules.chat.agent_limits.repository import agent_tool_limits_repository


def active_config() -> AgentToolLimitsConfig:
    return agent_tool_limits_repository.load()


def update_config(partial: dict) -> AgentToolLimitsConfig:
    """Merge a partial update over the current config and persist it."""
    current = active_config().model_dump()
    merged = {**current, **{k: v for k, v in partial.items() if v is not None}}
    config = AgentToolLimitsConfig(**merged)
    agent_tool_limits_repository.save(config)
    return config


def status() -> dict:
    """Config for the admin UI."""
    return {"settings": active_config().model_dump()}
