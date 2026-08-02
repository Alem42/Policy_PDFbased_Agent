from __future__ import annotations

from app.modules.retrieval.contracts import MetadataFilters
from app.modules.retrieval.metadata_filters import MetadataFilterService


class FakeRepository:
    def __init__(self, rows: list[dict]) -> None:
        self.rows = rows

    def list_records(self, document_ids=None, *, include_restricted=False):
        if document_ids is None:
            return list(self.rows)
        allowed = set(document_ids)
        return [row for row in self.rows if row["id"] in allowed]


ROWS = [
    {
        "id": "doc-old",
        "policy_areas": ["Climate Adaptation"],
        "country_region": "Australia",
        "source_organisation": "NSW Government",
        "language": "English",
        "keywords": ["heat", "resilience"],
        "year": 2018,
    },
    {
        "id": "doc-new",
        "policy_areas": ["Public Health"],
        "country_region": "Canada",
        "source_organisation": "Health Canada",
        "language": "French",
        "keywords": ["health"],
        "year": 2025,
    },
]


def test_infer_uses_only_explicit_metadata_labels_and_years() -> None:
    service = MetadataFilterService(FakeRepository(ROWS))

    inferred = service.infer(
        "Use Australia Climate Adaptation documents published in 2018 in English."
    )

    assert inferred.policy_areas == ("Climate Adaptation",)
    assert inferred.country_regions == ("Australia",)
    assert inferred.languages == ("English",)
    assert inferred.year_from == 2018
    assert inferred.year_to == 2018


def test_infer_ignores_vague_partial_policy_area() -> None:
    service = MetadataFilterService(FakeRepository(ROWS))

    inferred = service.infer("What climate issues are discussed?")

    assert inferred.policy_areas == ()


def test_explicit_before_filter_wins_over_year_in_question_subject() -> None:
    service = MetadataFilterService(FakeRepository(ROWS))

    inferred = service.infer(
        "I want updates after 2026; filter the files which published before 2026."
    )

    assert inferred.year_from is None
    assert inferred.year_to == 2025


def test_after_year_is_an_exclusive_lower_bound() -> None:
    service = MetadataFilterService(FakeRepository(ROWS))

    inferred = service.infer("Only use documents published after 2023.")

    assert inferred.year_from == 2024
    assert inferred.year_to is None


def test_apply_exact_filters_restricts_selected_documents(monkeypatch) -> None:
    service = MetadataFilterService(FakeRepository(ROWS))
    monkeypatch.setattr(
        "app.modules.retrieval.metadata_filters.resolve_document_ids",
        lambda identifiers, _include=False: list(identifiers),
    )

    result = service.apply(
        MetadataFilters(
            policy_areas=("Public Health",),
            country_regions=("Canada",),
            languages=("French",),
            year_from=2024,
        ),
        scope="selected",
        identifiers=["doc-old", "doc-new"],
    )

    assert result.document_ids == ("doc-new",)
    assert result.applied is True
    assert result.fallback is False


def test_zero_match_falls_back_and_warns_about_staleness(monkeypatch) -> None:
    service = MetadataFilterService(FakeRepository(ROWS[:1]))
    monkeypatch.setattr(
        "app.modules.retrieval.metadata_filters.resolve_document_ids",
        lambda identifiers, _include=False: list(identifiers),
    )

    result = service.apply(
        MetadataFilters(year_from=2022, freshness_requested=True),
        scope="selected",
        identifiers=["doc-old"],
    )

    assert result.document_ids == ("doc-old",)
    assert result.fallback is True
    assert "older sources may no longer reflect current policy" in result.notice
