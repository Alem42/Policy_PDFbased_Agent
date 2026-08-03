from __future__ import annotations

import pytest

from app.modules.retrieval import service as retrieval_module
from app.modules.retrieval.contracts import MetadataFilters, RetrievalRequest
from app.modules.retrieval.metadata_filters import FilterApplication
from app.modules.retrieval.service import RetrievalService


def test_selected_retrieval_returns_context_citations_and_evidence(monkeypatch) -> None:
    pages = [{"file": "policy.md", "page": 1, "text": "fallback " * 40}]
    chunks = [
        {
            "document_id": "doc-1",
            "doc_title": "Policy",
            "file": "policy.md",
            "chunk_id": "chunk-1",
            "page_start": 1,
            "text": "The implementation deadline is 1 July 2027. " * 8,
            "distance": 0.1,
            "reranker_score": 2.0,
        },
        {
            "document_id": "doc-1",
            "doc_title": "Policy",
            "file": "policy.md",
            "chunk_id": "chunk-2",
            "page_start": 2,
            "text": "Unrelated appendix " * 20,
            "distance": 0.9,
        },
    ]
    monkeypatch.setattr(retrieval_module, "read_documents", lambda *args, **kwargs: pages)
    monkeypatch.setattr(
        retrieval_module,
        "retrieve_relevant_chunks",
        lambda *args, **kwargs: chunks,
    )
    monkeypatch.setattr(retrieval_module, "documents_have_embeddings", lambda _: True)
    result = RetrievalService().retrieve(
        RetrievalRequest(
            question="When is the implementation deadline?",
            identifiers=("doc-1",),
        )
    )

    assert [chunk["chunk_id"] for chunk in result.chunks] == ["chunk-1"]
    assert result.citations[0]["title"] == "Policy"
    assert result.citations[0]["chunk_id"] == "chunk-1"
    assert "1 July 2027" in result.context
    assert result.evidence.sufficient is True


def test_full_corpus_retrieval_uses_same_evidence_result(monkeypatch) -> None:
    monkeypatch.setattr(
        retrieval_module,
        "search_full_corpus",
        lambda *args, **kwargs: [],
    )
    result = RetrievalService().retrieve(
        RetrievalRequest(question="Unknown topic", scope="full_corpus")
    )
    assert result.pages == []
    assert result.chunks == []
    assert result.evidence.sufficient is False


def test_metadata_filter_fallback_uses_original_scope_and_exposes_notice(monkeypatch) -> None:
    captured = {}
    notice = "No current documents matched; older sources may be outdated."
    monkeypatch.setattr(
        retrieval_module.metadata_filter_service,
        "apply",
        lambda *args, **kwargs: FilterApplication(
            ("doc-old",), applied=True, fallback=True, notice=notice
        ),
    )
    monkeypatch.setattr(retrieval_module, "read_documents", lambda *args, **kwargs: [])

    def retrieve(_question, identifiers, **_kwargs):
        captured["identifiers"] = identifiers
        return []

    monkeypatch.setattr(retrieval_module, "retrieve_relevant_chunks", retrieve)
    monkeypatch.setattr(retrieval_module, "documents_have_embeddings", lambda _: True)

    result = RetrievalService().retrieve(
        RetrievalRequest(
            question="What is the latest policy?",
            identifiers=("doc-old",),
            metadata_filters=MetadataFilters(
                year_from=2022,
                freshness_requested=True,
            ),
        )
    )

    assert captured["identifiers"] == ["doc-old"]
    assert result.filter_applied is True
    assert result.filter_fallback is True
    assert result.filter_notice == notice


def test_metadata_subset_with_weak_evidence_retries_original_scope(monkeypatch) -> None:
    monkeypatch.setattr(
        retrieval_module.metadata_filter_service,
        "apply",
        lambda *args, **kwargs: FilterApplication(
            ("doc-filtered",), applied=True, fallback=False, notice="Applied year<=2025."
        ),
    )
    seen_identifiers = []
    monkeypatch.setattr(retrieval_module, "read_documents", lambda *args, **kwargs: [])

    def retrieve(_question, identifiers, **_kwargs):
        seen_identifiers.append(list(identifiers))
        if identifiers == ["doc-filtered"]:
            return []
        return [
            {
                "document_id": "doc-original",
                "doc_title": "Original scope",
                "file": "original.pdf",
                "chunk_id": "chunk-1",
                "page_start": 1,
                "text": "Australia's AI safety standard contains voluntary guardrails. " * 10,
                "distance": 0.1,
                "reranker_score": 2.0,
            }
        ]

    monkeypatch.setattr(retrieval_module, "retrieve_relevant_chunks", retrieve)
    monkeypatch.setattr(retrieval_module, "documents_have_embeddings", lambda _: True)

    result = RetrievalService().retrieve(
        RetrievalRequest(
            question="What is Australia's AI safety standard?",
            identifiers=("doc-filtered", "doc-original"),
            metadata_filters=MetadataFilters(year_to=2025),
        )
    )

    assert seen_identifiers == [
        ["doc-filtered"],
        ["doc-filtered", "doc-original"],
    ]
    assert result.evidence.sufficient is True
    assert result.filter_fallback is True
    assert "expanded to the original document scope" in result.filter_notice


def test_multi_region_comparison_supplements_each_requested_region(monkeypatch) -> None:
    filters = MetadataFilters(country_regions=("Australia", "China"))
    monkeypatch.setattr(
        retrieval_module.metadata_filter_service,
        "apply",
        lambda *args, **kwargs: FilterApplication(
            ("doc-au", "doc-cn"), applied=True, fallback=False
        ),
    )
    monkeypatch.setattr(
        retrieval_module.metadata_filter_service.repository,
        "list_records",
        lambda *args, **kwargs: [
            {"id": "doc-au", "country_region": "Australia"},
            {"id": "doc-cn", "country_region": "China"},
        ],
    )
    monkeypatch.setattr(retrieval_module, "read_documents", lambda *args, **kwargs: [])
    monkeypatch.setattr(retrieval_module, "documents_have_embeddings", lambda _: True)

    def retrieve(question, identifiers, **_kwargs):
        document_id = identifiers[0]
        country = "Australia" if document_id == "doc-au" else "China"
        return [
            {
                "document_id": document_id,
                "doc_title": f"{country} AI policy",
                "file": f"{document_id}.pdf",
                "chunk_id": f"chunk-{document_id}",
                "page_start": 1,
                "text": f"{country} assigns accountable officials for AI governance. " * 12,
                "distance": 0.1,
                "reranker_score": 2.0,
            }
        ]

    monkeypatch.setattr(retrieval_module, "retrieve_relevant_chunks", retrieve)

    result = RetrievalService().retrieve(
        RetrievalRequest(
            question="Compare Australia and China AI governance accountability.",
            identifiers=("doc-au", "doc-cn"),
            metadata_filters=filters,
        )
    )

    assert {citation["document_id"] for citation in result.citations} == {
        "doc-au",
        "doc-cn",
    }
    assert result.evidence.sufficient is True


def test_fallback_document_from_wrong_region_cannot_pass_evidence_gate(monkeypatch) -> None:
    monkeypatch.setattr(
        retrieval_module.metadata_filter_service,
        "apply",
        lambda *args, **kwargs: FilterApplication(
            ("doc-za",), applied=True, fallback=True, notice="Expanded scope."
        ),
    )
    monkeypatch.setattr(
        retrieval_module.metadata_filter_service.repository,
        "list_records",
        lambda *args, **kwargs: [
            {"id": "doc-za", "country_region": "South Africa"},
        ],
    )
    monkeypatch.setattr(retrieval_module, "read_documents", lambda *args, **kwargs: [])
    monkeypatch.setattr(retrieval_module, "documents_have_embeddings", lambda _: True)
    monkeypatch.setattr(
        retrieval_module,
        "retrieve_relevant_chunks",
        lambda *args, **kwargs: [
            {
                "document_id": "doc-za",
                "doc_title": "South Africa notice",
                "file": "notice.pdf",
                "chunk_id": "chunk-za",
                "page_start": 1,
                "text": "South Africa withdrew its draft national AI policy. " * 12,
                "distance": 0.1,
                "reranker_score": 2.0,
            }
        ],
    )
    monkeypatch.setattr(
        retrieval_module,
        "assess_evidence_sufficiency",
        lambda **kwargs: (True, None),
    )

    result = RetrievalService().retrieve(
        RetrievalRequest(
            question="What does Australia's AI policy require?",
            identifiers=("doc-za",),
            metadata_filters=MetadataFilters(country_regions=("Australia",)),
        )
    )

    assert result.evidence.sufficient is False
    assert "Missing: Australia" in result.evidence.reason


def test_indexed_irrelevant_results_do_not_fall_back_to_misleading_page_citations(
    monkeypatch,
) -> None:
    pages = [{"file": "policy.md", "page": 1, "text": "Council heat policy " * 30}]
    chunks = [
        {
            "document_id": "doc-1",
            "file": "policy.md",
            "chunk_id": "chunk-1",
            "page_start": 1,
            "text": pages[0]["text"],
            "distance": 0.9,
            "reranker_score": 1.0,
        }
    ]
    monkeypatch.setattr(retrieval_module, "read_documents", lambda *args, **kwargs: pages)
    monkeypatch.setattr(
        retrieval_module,
        "retrieve_relevant_chunks",
        lambda *args, **kwargs: chunks,
    )
    monkeypatch.setattr(retrieval_module, "documents_have_embeddings", lambda _: True)

    result = RetrievalService().retrieve(
        RetrievalRequest(
            question="commercial lunar mining licence fee",
            identifiers=("doc-1",),
        )
    )
    assert result.evidence.sufficient is False
    assert result.context == ""
    assert result.citations == []


@pytest.mark.parametrize(
    "retrieval_request, message",
    [
        (RetrievalRequest(question=" ", identifiers=("doc",)), "must not be blank"),
        (RetrievalRequest(question="q", identifiers=("doc",), top_k=0), "greater than zero"),
        (RetrievalRequest(question="q"), "at least one document"),
    ],
)
def test_retrieval_rejects_invalid_requests(
    retrieval_request: RetrievalRequest,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        RetrievalService().retrieve(retrieval_request)
