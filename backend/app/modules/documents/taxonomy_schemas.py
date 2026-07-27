from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class TaxonomyGroup(BaseModel):
    """One parent category and its leaf subcategories."""

    parent: str = Field(min_length=1)
    children: list[str] = Field(min_length=1)  # at least one leaf per parent
    source_ref: str | None = None

    @field_validator("parent")
    @classmethod
    def _strip_parent(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Parent label must not be blank.")
        return cleaned

    @field_validator("children")
    @classmethod
    def _clean_children(cls, values: list[str]) -> list[str]:
        # Drop blanks and dedupe while preserving order.
        seen: list[str] = []
        for item in values:
            cleaned = item.strip()
            if cleaned and cleaned not in seen:
                seen.append(cleaned)
        if not seen:
            raise ValueError("Each parent needs at least one subcategory.")
        return seen


class TaxonomyResponse(BaseModel):
    groups: list[TaxonomyGroup]


class TaxonomyUpdate(BaseModel):
    groups: list[TaxonomyGroup] = Field(min_length=1)
