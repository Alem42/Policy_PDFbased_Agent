from app.modules.chat.rag.evidence import (
    REASON_LOW_RELEVANCE,
    REASON_NO_TEXT,
    assess_evidence_sufficiency,
)
from app.modules.chat.rag.graph.nodes import route_after_evidence_check
from app.modules.chat.rag.prompts import (
    get_insufficient_evidence_message,
    get_system_prompt,
)


def test_researcher_prompt_is_structured() -> None:
    prompt = get_system_prompt("researcher")
    assert "## Relevant Cases" in prompt
    assert "## Key Lessons" in prompt
    assert "## Risks" in prompt


def test_student_prompt_is_beginner_friendly() -> None:
    prompt = get_system_prompt("student")
    assert "beginner-friendly" in prompt.lower() or "friendly policy tutor" in prompt.lower()
    assert "## Relevant Cases" not in prompt


def test_insufficient_evidence_messages_differ_by_mode() -> None:
    researcher = get_insufficient_evidence_message(
        "What changed?",
        REASON_LOW_RELEVANCE,
        "researcher",
    )
    student = get_insufficient_evidence_message(
        "What changed?",
        REASON_LOW_RELEVANCE,
        "student",
    )
    assert "Insufficient Evidence" in researcher
    assert "could not find enough information" in student


def test_assess_evidence_rejects_empty_context() -> None:
    sufficient, reason = assess_evidence_sufficiency(
        question="test",
        chunks=[],
        pages=[],
        context="",
        used_vector_retrieval=False,
    )
    assert sufficient is False
    assert reason == REASON_NO_TEXT


def test_assess_evidence_rejects_low_similarity_chunks() -> None:
    sufficient, reason = assess_evidence_sufficiency(
        question="housing policy reform",
        chunks=[{"distance": 0.95, "text": "unrelated"}],
        pages=[],
        context="x" * 300,
        used_vector_retrieval=True,
    )
    assert sufficient is False
    assert reason == REASON_LOW_RELEVANCE


def test_assess_evidence_accepts_strong_chunks() -> None:
    sufficient, reason = assess_evidence_sufficiency(
        question="housing policy reform",
        chunks=[{"distance": 0.2, "text": "housing reform details"}],
        pages=[],
        context="x" * 300,
        used_vector_retrieval=True,
    )
    assert sufficient is True
    assert reason is None


def test_route_after_evidence_check() -> None:
    assert route_after_evidence_check({"evidence_sufficient": True}) == "generate_answer"
    assert route_after_evidence_check({"evidence_sufficient": False}) == "insufficient_evidence"
