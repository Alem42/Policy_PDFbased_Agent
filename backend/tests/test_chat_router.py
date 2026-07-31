import json
from uuid import uuid4

import pytest
from fastapi import HTTPException
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

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


def test_cited_evidence_sources_drops_full_corpus_hit_on_an_already_selected_document() -> None:
    # Reproduces a real trace: search_internal_documents returned
    # evidence_sufficient=false but still surfaced candidates from "doc-1"
    # (tier "internal", not credited into evidence_sources since it wasn't
    # sufficient — see agent/tools.py). search_full_corpus then found a
    # DIFFERENT chunk of that SAME document (doc-1) that passed, plus a
    # genuinely new document (doc-2) that ended up uncited. The answer only
    # cites [1] (doc-1, tier full_corpus) and [2] (doc-2's citation number is
    # never referenced). Since doc-1 was already visible to the internal
    # search, this isn't "wider library" content even though the tool that
    # mechanically found citation [1] was search_full_corpus.
    citations = [
        {"number": 1, "tier": "full_corpus", "document_id": "doc-1", "title": "Selected doc, other chunk"},
        {"number": 2, "tier": "internal", "document_id": "doc-1", "title": "Selected doc, first chunk"},
        {"number": 3, "tier": "full_corpus", "document_id": "doc-2", "title": "Genuinely new doc"},
    ]
    result = chat_router._cited_evidence_sources(
        ["full_corpus"], citations, "The plan says X [1]."
    )
    assert result == []


def test_cited_evidence_sources_keeps_full_corpus_hit_on_a_genuinely_new_document() -> None:
    citations = [
        {"number": 1, "tier": "internal", "document_id": "doc-1"},
        {"number": 2, "tier": "full_corpus", "document_id": "doc-2"},
    ]
    result = chat_router._cited_evidence_sources(
        ["full_corpus"], citations, "The plan says X [2]."
    )
    assert result == ["full_corpus"]


def test_turn_token_usage_sums_only_this_turns_ai_messages() -> None:
    messages = [
        HumanMessage(content="prior question"),
        AIMessage(content="prior answer", usage_metadata={"input_tokens": 999, "output_tokens": 999, "total_tokens": 1998}),
        HumanMessage(content="current question"),
        AIMessage(
            content="",
            tool_calls=[{"name": "search_internal_documents", "args": {}, "id": "c1", "type": "tool_call"}],
            usage_metadata={"input_tokens": 100, "output_tokens": 20, "total_tokens": 120},
        ),
        ToolMessage(content="{}", tool_call_id="c1", name="search_internal_documents"),
        AIMessage(content="final answer", usage_metadata={"input_tokens": 150, "output_tokens": 40, "total_tokens": 190}),
    ]
    result = chat_router._turn_token_usage(messages)
    assert result == {"prompt_tokens": 250, "completion_tokens": 60, "total_tokens": 310}


def test_turn_token_usage_skips_messages_without_usage_metadata() -> None:
    # auto_finalize_node's synthetic AIMessage (see agent/graph.py) never
    # called an LLM, so it carries no usage_metadata at all.
    messages = [
        HumanMessage(content="q"),
        AIMessage(content="", tool_calls=[{"name": "x", "args": {}, "id": "c1", "type": "tool_call"}]),
        ToolMessage(content="{}", tool_call_id="c1", name="x"),
    ]
    assert chat_router._turn_token_usage(messages) == {}


def test_turn_token_usage_empty_when_no_ai_messages_have_usage() -> None:
    assert chat_router._turn_token_usage([HumanMessage(content="q")]) == {}


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
