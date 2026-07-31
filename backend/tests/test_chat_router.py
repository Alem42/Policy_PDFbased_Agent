import json
from uuid import uuid4

import pytest
from fastapi import HTTPException
from langchain_core.messages import ToolMessage

from app.modules.chat import router as chat_router
from app.modules.chat.schemas import ChatRequest


def test_tool_result_event_exposes_compact_trace_summary() -> None:
    message = ToolMessage(
        content=json.dumps(
            {
                "evidence_sufficient": False,
                "reason": "The excerpts do not mention UK space policy.",
                "results": [
                    {"title": "Space Strategy", "number": 1},
                    {"title": "Space Strategy", "number": 2},
                    {"title": "Defence Space", "number": 3},
                ],
            }
        ),
        tool_call_id="call-1",
        name="search_full_corpus",
    )

    assert chat_router._tool_result_event(message) == {
        "type": "tool_result",
        "tool": "search_full_corpus",
        "evidence_sufficient": False,
        "evidence_reason": "The excerpts do not mention UK space policy.",
        "result_count": 3,
        "source_titles": ["Space Strategy", "Defence Space"],
        "answer_plan": None,
        "citation_numbers": None,
    }


def test_cited_evidence_sources_only_reports_tiers_the_answer_cites() -> None:
    # Reproduces a real trace: search_internal_documents (tier "internal")
    # was sufficient, but the model still escalated to search_full_corpus
    # (tier "full_corpus") "to check a sub-topic" before writing an answer
    # that, in the end, only cited [1] from the internal tier. evidence_sources
    # already credits both tiers (see agent/tools.py) — the badge should not.
    citations = [
        {"number": 1, "tier": "internal", "title": "Selected doc"},
        {"number": 2, "tier": "full_corpus", "title": "Wider-library doc"},
    ]
    result = chat_router._cited_evidence_sources(
        ["internal", "full_corpus"], citations, "The plan does X [1]."
    )
    assert result == ["internal"]


def test_cited_evidence_sources_reports_every_tier_actually_cited() -> None:
    citations = [
        {"number": 1, "tier": "internal"},
        {"number": 2, "tier": "web"},
    ]
    result = chat_router._cited_evidence_sources(
        ["internal", "web"], citations, "Documents say X [1]. The web confirms Y [2]."
    )
    assert result == ["internal", "web"]


def test_cited_evidence_sources_empty_when_answer_has_no_citation_markers() -> None:
    citations = [{"number": 1, "tier": "internal"}]
    assert chat_router._cited_evidence_sources(["internal"], citations, "No markers here.") == []


@pytest.mark.asyncio
async def test_chat_rejects_session_not_owned(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_session_belongs_to_user(session_id: str, user_id: str) -> bool:
        return False

    def fail_get_history_for_llm(*_: object) -> list[dict]:
        raise AssertionError("History should not be read for another user's session.")

    monkeypatch.setattr(
        chat_router.chat_history_repository,
        "session_belongs_to_user",
        fake_session_belongs_to_user,
    )
    monkeypatch.setattr(
        chat_router.chat_history_repository,
        "get_history_for_llm",
        fail_get_history_for_llm,
    )

    payload = ChatRequest(
        question="What does this policy say?",
        document_ids=[uuid4()],
        session_id=uuid4(),
    )

    with pytest.raises(HTTPException) as exc_info:
        await chat_router.chat(
            payload,
            {"id": str(uuid4()), "role": "user"},
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Session not found."
