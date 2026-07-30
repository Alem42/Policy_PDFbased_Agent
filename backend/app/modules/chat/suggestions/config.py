"""Suggestion configuration model + defaults (one JSON row, admin-tunable).

Mirrors the reranking/embedding config pattern. Every field maps to a control on
the Manage > Suggestions page.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class SuggestionConfig(BaseModel):
    """Admin-tunable follow-up-suggestion settings (one JSON row)."""

    enabled: bool = True
    # How many suggestions to actually show ("数量").
    max_suggestions: int = Field(default=3, ge=1, le=8)
    # How many candidates the LLM proposes; validation drops the off-document ones,
    # so this is > max_suggestions to leave headroom ("质量" via selection pressure).
    candidate_pool: int = Field(default=6, ge=1, le=16)
    # Stricter-than-answering distance cutoff for suggestions. None -> reuse the
    # evidence gate's live max_vector_distance(). Set below the gate for higher quality.
    validation_distance: float | None = Field(default=None, ge=0.0, le=2.0)
    # Apply the reranker's secondary evidence floor to candidates (when reranker is on).
    use_reranker_validation: bool = True
    # Chunks retrieved per candidate during validation (kept small for cost).
    validation_top_k: int = Field(default=5, ge=1, le=20)
    # A little diversity in candidate wording (0 = deterministic).
    temperature: float = Field(default=0.3, ge=0.0, le=1.5)
    # Keep each suggestion short and clickable.
    max_question_chars: int = Field(default=140, ge=20, le=400)
    # Soft personalization from a user's past suggestion clicks (off by default).
    # TODO(profile): richer profile — embed clicked questions, cluster into topic
    # centroids, and bias candidate ranking by similarity to the user's centroid.
    personalize: bool = False

    def effective_distance(self, gate_default: float) -> float:
        """Distance cutoff for validation — the override if set, else the gate default."""
        return self.validation_distance if self.validation_distance is not None else gate_default
