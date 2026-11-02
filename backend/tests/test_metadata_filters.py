from __future__ import annotations

import pytest

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


def test_infer_maps_only_explicit_api_fields_without_reading_metadata():
    class NoReads:
        def list_records(self, *a, **k):
            raise AssertionError("Question parsing must not scan document metadata")

    inferred = MetadataFilterService(NoReads()).infer(
        "What is the 2030 target in China?",
        {
            "country_or_region": "Australia",
            "published_year_from": 2023,
            "published_year_to": 2025,
            "language": "English",
            "tags": ["test", "test"],
        },
    )
    assert inferred.country_regions == ("Australia",)
    assert (inferred.year_from, inferred.year_to) == (2023, 2025)
    assert inferred.languages == ("English",)
    assert inferred.tags == ("test",)


@pytest.mark.parametrize(
    "question",
    [
        "What is the offshore wind target for 2030?",
        "Only use documents published after 2023 and before 2026.",
        "What is the latest policy?",
        "Do not use China documents; use Australia only.",
        "What does the document say about Canadarm?",
        "Compare Australia and China AI governance.",
        "2025年的政策有什么要求？",
        "使用25年而不是26年的文件。",
        "请用中文回答，比较澳大利亚、中国和新加坡。",
    ],
)
def test_question_words_never_become_hard_metadata_filters(question):
    inferred = MetadataFilterService(FakeRepository(ROWS)).infer(question)
    assert not inferred.active


def test_contradictory_explicit_year_bounds_are_rejected():
    with pytest.raises(ValueError, match="lower bound"):
        MetadataFilterService(FakeRepository(ROWS)).infer(
            "",
            {
                "published_year_from": 2026,
                "published_year_to": 2025,
            },
        )


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


def test_zero_match_keeps_explicit_scope_closed(monkeypatch) -> None:
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

    assert result.document_ids == ()
    assert result.fallback is False
    assert "scope was not expanded" in result.notice
