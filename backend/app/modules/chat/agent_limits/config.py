"""Agent tool-call budget configuration model + defaults (one JSON row, admin-tunable).

Mirrors the suggestions/reranking config pattern. Every field is a per-tool call
budget enforced by chat.rag.agent.policy.tools_for -- once a tool hits its budget
for the turn, the ReAct loop stops offering it to the LLM.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class AgentToolLimitsConfig(BaseModel):
    """Admin-tunable per-tool call budgets for the ReAct agent (one JSON row)."""

    search_internal_documents: int = Field(default=5, ge=1, le=50)
    search_full_corpus: int = Field(default=1, ge=1, le=50)
    ask_user: int = Field(default=20, ge=1, le=50)
    search_web: int = Field(default=4, ge=1, le=50)
    import_web_page: int = Field(default=1, ge=1, le=50)
    prepare_final_answer: int = Field(default=1, ge=1, le=50)

    def as_limits(self) -> dict[str, int]:
        return self.model_dump()
