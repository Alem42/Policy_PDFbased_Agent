"""Small, user-facing configuration for grounded follow-up suggestions."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

# These are implementation safety controls, not product choices. Keeping them
# here makes the suggestion pipeline predictable while the admin UI stays clear.
SUGGESTION_CANDIDATE_HEADROOM = 2
SUGGESTION_VALIDATION_TOP_K = 5
SUGGESTION_TEMPERATURE = 0.3
SUGGESTION_MAX_QUESTION_CHARS = 140


class SuggestionConfig(BaseModel):
    """The two choices an administrator actually needs to make.

    Old settings rows may still contain the previously exposed tuning fields.
    They are intentionally ignored so an upgrade does not break configuration
    loading; the next save rewrites the row using this compact schema.
    """

    model_config = ConfigDict(extra="ignore")

    enabled: bool = True
    max_suggestions: int = Field(default=3, ge=1, le=8)

    @property
    def candidate_pool(self) -> int:
        """Generate two spare candidates for evidence validation to filter."""
        return min(16, self.max_suggestions + SUGGESTION_CANDIDATE_HEADROOM)

    @property
    def validation_distance(self) -> None:
        """Always reuse the live Embedding Evidence Gate threshold."""
        return None

    @property
    def use_reranker_validation(self) -> bool:
        """Reuse the reranker evidence floor whenever reranking is enabled."""
        return True

    @property
    def validation_top_k(self) -> int:
        return SUGGESTION_VALIDATION_TOP_K

    @property
    def temperature(self) -> float:
        return SUGGESTION_TEMPERATURE

    @property
    def max_question_chars(self) -> int:
        return SUGGESTION_MAX_QUESTION_CHARS

    @property
    def personalize(self) -> bool:
        """Personalisation is not yet a supported product feature."""
        return False
