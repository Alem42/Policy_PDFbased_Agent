from pydantic import BaseModel, ConfigDict, Field


class EvidenceValidationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = False
    model: str = "deepseek/deepseek-v4-flash"
    per_document_quota: bool = True
    decompose: bool = True
    max_requirements: int = Field(default=6, ge=1, le=8)
    max_claims: int = Field(default=48, ge=8, le=64)
    candidate_pool_size: int = Field(default=36, ge=20, le=96)
    default_top_k: int = Field(default=6, ge=1, le=20)
    timeout_seconds: int = Field(default=90, ge=10, le=180)
