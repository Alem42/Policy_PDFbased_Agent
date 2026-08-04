"""Persistence for agent tool-call limits (one JSON row in agent_tool_limit_settings)."""

from __future__ import annotations

from app.core.settings_store import SingleRowSettings
from app.modules.chat.agent_limits.config import AgentToolLimitsConfig


class AgentToolLimitsRepository:
    def __init__(self) -> None:
        self._store = SingleRowSettings("agent_tool_limit_settings")

    def load(self) -> AgentToolLimitsConfig:
        # SingleRowSettings falls back to {} if the table/row is missing, so
        # defaults apply cleanly before the migration is applied.
        return AgentToolLimitsConfig(**self._store.load())

    def save(self, config: AgentToolLimitsConfig) -> None:
        self._store.save(config.model_dump_json())


agent_tool_limits_repository = AgentToolLimitsRepository()
