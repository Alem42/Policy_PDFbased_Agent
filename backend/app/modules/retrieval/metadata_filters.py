"""Apply explicit metadata filters. Never guess publication years or regions from question words."""

from __future__ import annotations

from dataclasses import dataclass

from app.modules.documents.repositories.metadata_filters import (
    MetadataFilterRepository,
    metadata_filter_repository,
)
from app.modules.documents.service import resolve_document_ids
from app.modules.retrieval.contracts import MetadataFilters, RetrievalScope


@dataclass(frozen=True)
class FilterApplication:
    document_ids: tuple[str, ...]
    applied: bool = False
    fallback: bool = False
    notice: str | None = None


class MetadataFilterService:
    """Map explicit API filters to exact metadata comparisons, with no silent relaxation."""

    def __init__(
        self,
        repository: MetadataFilterRepository = metadata_filter_repository,
    ) -> None:
        self.repository = repository

    def infer(
        self,
        question: str,
        explicit: dict | None = None,
        *,
        include_restricted: bool = False,
    ) -> MetadataFilters:
        # Natural-language dates/regions are semantic requirements, not
        # document publication metadata. Never infer hard filters from words.
        explicit = explicit or {}

        def values(key):
            value = explicit.get(key)
            return (str(value).strip(),) if value and str(value).strip() else ()

        lower = explicit.get("published_year_from")
        upper = explicit.get("published_year_to")
        if lower is not None and upper is not None and lower > upper:
            raise ValueError("Publication year lower bound exceeds upper bound.")
        return MetadataFilters(
            policy_areas=values("policy_area"),
            country_regions=values("country_or_region"),
            source_organisations=values("source_organisation"),
            languages=values("language"),
            tags=tuple(
                dict.fromkeys(str(t).strip() for t in explicit.get("tags") or [] if str(t).strip())
            ),
            year_from=lower,
            year_to=upper,
        )

    def apply(
        self,
        filters: MetadataFilters,
        *,
        scope: RetrievalScope,
        identifiers: list[str] | None = None,
        include_restricted: bool = False,
    ) -> FilterApplication:
        if scope == "selected":
            base_ids = resolve_document_ids(identifiers or [], include_restricted)
            rows = self.repository.list_records(
                base_ids,
                include_restricted=include_restricted,
            )
        else:
            rows = self.repository.list_records(include_restricted=include_restricted)
            base_ids = [row["id"] for row in rows]

        if not filters.active:
            return FilterApplication(tuple(base_ids))

        matched = [row["id"] for row in rows if self._matches(row, filters)]
        description = self.describe(filters)
        if matched:
            return FilterApplication(
                tuple(matched),
                applied=True,
                notice=f"Applied document metadata filters: {description}.",
            )

        return FilterApplication(
            (),
            applied=True,
            fallback=False,
            notice=f"No documents matched the explicit metadata filters ({description}); "
            "scope was not expanded.",
        )

    @staticmethod
    def _matches(row: dict, filters: MetadataFilters) -> bool:
        def same(left: str | None, right: str) -> bool:
            return bool(left) and str(left).casefold() == right.casefold()

        row_areas = {str(value).casefold() for value in row.get("policy_areas") or []}
        row_tags = {str(value).casefold() for value in row.get("keywords") or []}
        if filters.policy_areas and not any(
            value.casefold() in row_areas for value in filters.policy_areas
        ):
            return False
        if filters.country_regions and not any(
            same(row.get("country_region"), value) for value in filters.country_regions
        ):
            return False
        if filters.source_organisations and not any(
            same(row.get("source_organisation"), value) for value in filters.source_organisations
        ):
            return False
        if filters.languages and not any(
            same(row.get("language"), value) for value in filters.languages
        ):
            return False
        if filters.tags and not all(value.casefold() in row_tags for value in filters.tags):
            return False
        year = row.get("year")
        if filters.year_from is not None and (year is None or int(year) < filters.year_from):
            return False
        if filters.year_to is not None and (year is None or int(year) > filters.year_to):
            return False
        return True

    @staticmethod
    def describe(filters: MetadataFilters) -> str:
        parts: list[str] = []
        for label, values in (
            ("policy area", filters.policy_areas),
            ("region", filters.country_regions),
            ("organisation", filters.source_organisations),
            ("language", filters.languages),
            ("tag", filters.tags),
        ):
            if values:
                parts.append(f"{label}={', '.join(values)}")
        if filters.year_from is not None and filters.year_to == filters.year_from:
            parts.append(f"year={filters.year_from}")
        else:
            if filters.year_from is not None:
                parts.append(f"year>={filters.year_from}")
            if filters.year_to is not None:
                parts.append(f"year<={filters.year_to}")
        return "; ".join(parts) or "none"


metadata_filter_service = MetadataFilterService()
