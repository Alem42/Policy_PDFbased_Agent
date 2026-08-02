"""Infer and apply only explicit, structured document metadata filters."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime

from app.modules.documents.repositories.metadata_filters import (
    MetadataFilterRepository,
    metadata_filter_repository,
)
from app.modules.documents.service import resolve_document_ids
from app.modules.retrieval.contracts import MetadataFilters, RetrievalScope

_YEAR = re.compile(r"\b(?:19|20)\d{2}\b")
_FRESHNESS_TERMS = (
    "latest",
    "most recent",
    "current policy",
    "currently valid",
    "up to date",
    "up-to-date",
    "最新",
    "近期",
    "当前政策",
    "现行",
    "时效性",
)
_LANGUAGE_PATTERNS = {
    "English": (r"\bin english\b", r"\benglish[- ]language\b", "英文", "英语"),
    "Chinese": (r"\bin chinese\b", r"\bchinese[- ]language\b", "中文", "汉语"),
    "French": (r"\bin french\b", r"\bfrench[- ]language\b", "法文", "法语"),
    "Spanish": (r"\bin spanish\b", r"\bspanish[- ]language\b", "西班牙语"),
}


@dataclass(frozen=True)
class FilterApplication:
    document_ids: tuple[str, ...]
    applied: bool = False
    fallback: bool = False
    notice: str | None = None


def _unique(values: list[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        clean = value.strip()
        key = clean.casefold()
        if clean and key not in seen:
            seen.add(key)
            result.append(clean)
    return tuple(result)


def _contains_label(question: str, label: str) -> bool:
    clean = label.strip()
    if len(clean) < 4:
        return False
    return clean.casefold() in question.casefold()


class MetadataFilterService:
    """Translate explicit user constraints into exact metadata comparisons."""

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
        explicit = explicit or {}
        rows = self.repository.list_records(include_restricted=include_restricted)
        policy_labels = _unique(
            [label for row in rows for label in row.get("policy_areas", [])]
        )
        regions = _unique(
            [str(row["country_region"]) for row in rows if row.get("country_region")]
        )
        organisations = _unique(
            [
                str(row["source_organisation"])
                for row in rows
                if row.get("source_organisation")
            ]
        )

        policy_areas = [str(explicit["policy_area"])] if explicit.get("policy_area") else []
        policy_areas.extend(label for label in policy_labels if _contains_label(question, label))
        country_regions = (
            [str(explicit["country_or_region"])]
            if explicit.get("country_or_region")
            else []
        )
        country_regions.extend(label for label in regions if _contains_label(question, label))
        source_organisations = (
            [str(explicit["source_organisation"])]
            if explicit.get("source_organisation")
            else []
        )
        source_organisations.extend(
            label for label in organisations if _contains_label(question, label)
        )

        languages = [str(explicit["language"])] if explicit.get("language") else []
        lowered = question.casefold()
        for language, patterns in _LANGUAGE_PATTERNS.items():
            if any(re.search(pattern, lowered) for pattern in patterns):
                languages.append(language)

        tags = [str(tag) for tag in explicit.get("tags") or []]
        tags.extend(
            match.strip()
            for match in re.findall(r"(?:\btag|标签)\s*[:：]\s*([\w -]+)", question, re.I)
        )

        years = [int(value) for value in _YEAR.findall(question)]
        year_from = explicit.get("published_year_from")
        year_to = explicit.get("published_year_to")
        if years and year_from is None and year_to is None:
            year_from, year_to = min(years), max(years)

        freshness_requested = any(term in lowered for term in _FRESHNESS_TERMS)
        if freshness_requested and year_from is None:
            year_from = datetime.now(UTC).year - 5

        return MetadataFilters(
            policy_areas=_unique(policy_areas),
            country_regions=_unique(country_regions),
            source_organisations=_unique(source_organisations),
            languages=_unique(languages),
            tags=_unique(tags),
            year_from=year_from,
            year_to=year_to,
            freshness_requested=freshness_requested,
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

        if filters.freshness_requested:
            notice = (
                f"No documents matched the requested current/recent filter ({description}). "
                "The search was expanded to the original document scope; older sources may no "
                "longer reflect current policy."
            )
        else:
            notice = (
                f"No documents matched the requested metadata filters ({description}). "
                "The search was expanded to the original document scope, so the returned "
                "sources may not satisfy every requested constraint."
            )
        return FilterApplication(
            tuple(base_ids),
            applied=True,
            fallback=True,
            notice=notice,
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
            same(row.get("source_organisation"), value)
            for value in filters.source_organisations
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
