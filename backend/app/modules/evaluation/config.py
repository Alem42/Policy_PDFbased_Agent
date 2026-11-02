from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class EvaluationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    model: str = Field(default="deepseek/deepseek-v4-flash", min_length=1, max_length=160)
    top_k: int = Field(default=6, ge=1, le=12)
    case_ids: list[str] = Field(default_factory=list, max_length=256)
    suite: Literal["legacy", "extended"] = "extended"
    kind: Literal[
        "baseline",
        "chunk_sweep",
        "parameter_sweep",
        "retrieval_lab",
        "validated",
        "audit",
        "judge_controls",
    ] = "baseline"
    judge_model: str = Field(default="deepseek/deepseek-v4-flash", min_length=1, max_length=160)
    judge_enabled: bool = False
    max_cases: int = Field(default=20, ge=1, le=120)
    token_budget: int = Field(default=100_000, ge=1_000, le=5_000_000)
    max_api_calls: int = Field(default=40, ge=1, le=1000)
    max_input_tokens: int = Field(default=20_000, ge=1_000, le=500_000)
    allow_full_source_audit: bool = False
    parent_run_id: UUID | None = None
    reuse_run_id: UUID | None = None


class Review(BaseModel):
    model_config = ConfigDict(extra="forbid")
    score: int = Field(ge=1, le=5)
    comment: str = Field(default="", max_length=4000)
