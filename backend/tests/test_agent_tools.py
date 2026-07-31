"""Pure-logic pieces of the web-search agent: evidence gating, citation
dedup, and admin-only tool filtering. These don't hit the database."""

from __future__ import annotations

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

import json

from app.modules.chat.rag.agent.graph import (
    ALL_TOOLS,
    NON_ADMIN_TOOLS,
    TOOL_CALL_LIMITS,
    _messages_for_current_turn,
    _should_auto_finalize,
    _tools_for,
    agent_node,
    auto_finalize_node,
    record_tool_call_node,
    route_after_tools,
)
from app.modules.chat.rag.agent.state import add_citations
from app.modules.chat.rag.agent.tools import _cosine_distance, _number_citations, _score_web_results
from app.modules.chat.rag.web_search.contracts import WebSearchResult


def test_cosine_distance_identical_vectors_is_zero() -> None:
    assert _cosine_distance([1.0, 0.0], [1.0, 0.0]) == pytest.approx(0.0)


def test_cosine_distance_orthogonal_vectors_is_one() -> None:
    assert _cosine_distance([1.0, 0.0], [0.0, 1.0]) == pytest.approx(1.0)


def test_cosine_distance_zero_vector_is_max_distance() -> None:
    assert _cosine_distance([0.0, 0.0], [1.0, 0.0]) == 1.0


def test_score_web_results_empty_is_insufficient() -> None:
    sufficient, reason, candidates = _score_web_results("query", [])
    assert sufficient is False
    assert candidates == []
    assert reason


def test_score_web_results_close_result_passes_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.modules.chat.rag.agent.tools as tools_module

    # Same vector for query and the one result -> distance 0, well under threshold.
    monkeypatch.setattr(tools_module, "embed_query", lambda text: [1.0, 0.0])
    monkeypatch.setattr(tools_module, "embed_documents", lambda texts: [[1.0, 0.0] for _ in texts])
    monkeypatch.setattr(tools_module, "max_vector_distance", lambda: 0.45)
    monkeypatch.setattr(tools_module, "reranker_enabled", lambda: False)

    results = [WebSearchResult(url="https://example.com", title="Example", content="relevant text")]
    sufficient, reason, candidates = _score_web_results("query", results)

    assert sufficient is True
    assert reason is None
    assert candidates[0]["passed"] is True


def test_score_web_results_far_result_fails_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.modules.chat.rag.agent.tools as tools_module

    # Orthogonal vectors -> distance 1.0, well over any sane threshold.
    monkeypatch.setattr(tools_module, "embed_query", lambda text: [1.0, 0.0])
    monkeypatch.setattr(tools_module, "embed_documents", lambda texts: [[0.0, 1.0] for _ in texts])
    monkeypatch.setattr(tools_module, "max_vector_distance", lambda: 0.45)
    monkeypatch.setattr(tools_module, "reranker_enabled", lambda: False)

    results = [
        WebSearchResult(url="https://example.com", title="Example", content="unrelated text")
    ]
    sufficient, reason, candidates = _score_web_results("query", results)

    assert sufficient is False
    assert candidates[0]["passed"] is False


def test_add_citations_deduplicates_by_identity() -> None:
    first = [{"document_id": "d1", "chunk_id": "c1", "title": "A"}]
    duplicate_and_new = [
        {"document_id": "d1", "chunk_id": "c1", "title": "A"},  # same identity, dropped
        {"document_id": "d2", "chunk_id": "c2", "title": "B"},
    ]
    merged = add_citations(first, duplicate_and_new)
    assert len(merged) == 2
    assert [c["chunk_id"] for c in merged] == ["c1", "c2"]


def test_add_citations_treats_distinct_web_urls_as_distinct() -> None:
    first = [{"source_url": "https://a.example.com", "title": "A"}]
    second = [{"source_url": "https://b.example.com", "title": "B"}]
    merged = add_citations(first, second)
    assert len(merged) == 2


def test_import_web_page_hidden_from_non_admin_tool_binding() -> None:
    non_admin_names = {t.name for t in NON_ADMIN_TOOLS}
    all_names = {t.name for t in ALL_TOOLS}
    assert "import_web_page" not in non_admin_names
    assert "import_web_page" in all_names
    # Every other tool remains available to non-admin sessions.
    assert all_names - non_admin_names == {"import_web_page"}


def test_document_analysis_mode_only_offers_internal_search() -> None:
    # Document Analysis mode has no full-corpus/web escalation tools; it can
    # only search the selected documents and hand off to the final writer.
    for is_admin in (True, False):
        names = {t.name for t in _tools_for(is_admin, "analysis")}
        assert names == {"search_internal_documents", "prepare_final_answer"}


def test_open_discussion_mode_offers_full_tool_set() -> None:
    admin_names = {t.name for t in _tools_for(True, "chat")}
    non_admin_names = {t.name for t in _tools_for(False, "chat")}
    assert admin_names == {
        "search_internal_documents",
        "search_full_corpus",
        "ask_user",
        "prepare_final_answer",
        "search_web",
        "import_web_page",
    }
    assert "import_web_page" not in non_admin_names
    assert admin_names - non_admin_names == {"import_web_page"}


def test_search_and_confirmation_tools_require_display_reason() -> None:
    tools_by_name = {tool.name: tool for tool in ALL_TOOLS}
    for name in (
        "search_internal_documents",
        "search_full_corpus",
        "ask_user",
        "search_web",
    ):
        schema = tools_by_name[name].args_schema.model_json_schema()
        assert "decision_reason" in schema["required"]


def test_exhausted_tool_is_removed_from_next_agent_turn() -> None:
    names = {
        tool.name
        for tool in _tools_for(
            False,
            "chat",
            {"search_full_corpus": TOOL_CALL_LIMITS["search_full_corpus"]},
        )
    }
    assert "search_full_corpus" not in names
    assert "ask_user" in names
    assert "prepare_final_answer" in names


def test_record_tool_call_increments_only_selected_action() -> None:
    message = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "search_full_corpus",
                "args": {
                    "query": "Russia policy",
                    "decision_reason": "The selected files did not cover Russia.",
                },
                "id": "call-1",
                "type": "tool_call",
            }
        ],
    )
    update = record_tool_call_node(
        {"messages": [message], "tool_call_counts": {"search_internal_documents": 1}}
    )
    assert update["tool_call_counts"] == {
        "search_internal_documents": 1,
        "search_full_corpus": 1,
    }
    assert update["last_tool_call"] == {
        "tool": "search_full_corpus",
        "query": "Russia policy",
        "decision_reason": "The selected files did not cover Russia.",
        "question": None,
        "url": None,
        "title": None,
        "reflection_on_previous_result": None,
    }


def test_current_turn_messages_hide_prior_tool_budget_observations() -> None:
    prior_user = HumanMessage(content="Find Russian AI policy")
    prior_tool_call = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "search_web",
                "args": {"query": "Russia AI policy"},
                "id": "old-call",
                "type": "tool_call",
            }
        ],
    )
    prior_budget_observation = ToolMessage(
        content='{"error":"budget exhausted"}',
        tool_call_id="old-call",
        name="search_web",
    )
    prior_answer = AIMessage(content="Here is the Russian policy summary.")
    current_user = HumanMessage(content="Find UK space policy")
    current_tool_call = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "search_internal_documents",
                "args": {"query": "UK space policy"},
                "id": "new-call",
                "type": "tool_call",
            }
        ],
    )
    current_observation = ToolMessage(
        content='{"evidence_sufficient":false}',
        tool_call_id="new-call",
        name="search_internal_documents",
    )

    visible = _messages_for_current_turn(
        [
            prior_user,
            prior_tool_call,
            prior_budget_observation,
            prior_answer,
            current_user,
            current_tool_call,
            current_observation,
        ]
    )

    assert visible == [
        prior_user,
        prior_answer,
        current_user,
        current_tool_call,
        current_observation,
    ]


async def test_agent_retries_when_provider_selects_exhausted_tool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.modules.chat.rag.agent.graph as graph_module

    responses = [
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "search_full_corpus",
                    "args": {"query": "Russia policy"},
                    "id": "call-exhausted",
                    "type": "tool_call",
                }
            ],
        ),
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "ask_user",
                    "args": {"question": "Search the web?", "options": ["Yes", "No"]},
                    "id": "call-ask",
                    "type": "tool_call",
                }
            ],
        ),
    ]
    invocations: list[list] = []

    class FakeClient:
        def bind_tools(self, tools, **kwargs):
            assert "search_full_corpus" not in {tool.name for tool in tools}
            assert kwargs["tool_choice"] == "required"
            return self

        async def ainvoke(self, messages):
            invocations.append(messages)
            return responses.pop(0)

    monkeypatch.setattr(
        graph_module,
        "resolve_generation_target",
        lambda model: ("fake", "model", {}),
    )
    monkeypatch.setattr(graph_module, "create_chat_client", lambda provider, model: FakeClient())
    monkeypatch.setattr(graph_module, "get_agent_system_prompt", lambda *args, **kwargs: "prompt")

    result = await agent_node(
        {
            "messages": [HumanMessage(content="Tell me about Russian policy")],
            "answer_mode": "chat",
            "is_admin": False,
            "tool_call_counts": {
                "search_internal_documents": 1,
                "search_full_corpus": TOOL_CALL_LIMITS["search_full_corpus"],
            },
        }
    )

    assert result["messages"][0].tool_calls[0]["name"] == "ask_user"
    assert len(invocations) == 2
    assert isinstance(invocations[1][-1], ToolMessage)
    assert "no longer available" in invocations[1][-1].content


def test_prepare_final_answer_routes_to_streaming_generation() -> None:
    state = {
        "answer_mode": "chat",
        "messages": [
            ToolMessage(
                content='{"ready": true}',
                tool_call_id="call-1",
                name="prepare_final_answer",
            )
        ]
    }
    assert route_after_tools(state) == "final_generation"


def test_other_tool_results_return_to_agent_loop() -> None:
    state = {
        "messages": [
            ToolMessage(
                content='{"evidence_sufficient": false}',
                tool_call_id="call-1",
                name="search_full_corpus",
            )
        ]
    }
    assert route_after_tools(state) == "agent"


def test_number_citations_assigns_sequential_numbers_to_new_citations() -> None:
    numbered, new = _number_citations(
        [],
        [
            {"document_id": "d1", "chunk_id": "c1", "title": "A"},
            {"document_id": "d2", "chunk_id": "c2", "title": "B"},
        ],
    )
    assert [c["number"] for c in numbered] == [1, 2]
    assert new == numbered


def _auto_finalize_state(
    question: str,
    payload: dict,
    *,
    answer_mode: str = "chat",
    search_calls_this_turn: int = 1,
    citations: list[dict] | None = None,
) -> dict:
    return {
        "answer_mode": answer_mode,
        "tool_call_counts": {"search_internal_documents": search_calls_this_turn},
        "citations": citations or [],
        "messages": [
            HumanMessage(content=question),
            ToolMessage(
                content=json.dumps(payload, ensure_ascii=False),
                tool_call_id="call-1",
                name="search_internal_documents",
            ),
        ],
    }


def test_should_auto_finalize_true_when_evidence_sufficient() -> None:
    # No entity/coverage check of its own (see graph.py block comment above
    # _should_auto_finalize) — trusts evidence_sufficient at face value until
    # assess_evidence_sufficiency() becomes keyword/entity-aware itself.
    state = _auto_finalize_state(
        "德国的人工智能战略对高风险系统有什么具体规定？",
        {
            "evidence_sufficient": True,
            "results": [
                {
                    "number": 1,
                    "title": "EU AI Act Overview",
                    "quote": "The EU AI Act classifies certain AI systems as high-risk.",
                }
            ],
        },
    )
    assert _should_auto_finalize(state) is True


def test_should_auto_finalize_false_for_comparison_request() -> None:
    # A user request to cross-check against the web is an intentional
    # exception in AGENT_STRATEGY_PROMPT — the backstop must not pre-empt it.
    state = _auto_finalize_state(
        "这份文件的说法现在还准确吗，能否上网核实一下？",
        {"evidence_sufficient": True, "results": [{"number": 1, "title": "Doc", "quote": "On topic."}]},
    )
    assert _should_auto_finalize(state) is False


def test_should_auto_finalize_false_when_not_first_search_this_turn() -> None:
    state = _auto_finalize_state(
        "生成式人工智能对就业市场有什么影响？",
        {"evidence_sufficient": True, "results": [{"number": 1, "title": "Doc", "quote": "On topic."}]},
        search_calls_this_turn=2,
    )
    assert _should_auto_finalize(state) is False


def test_should_auto_finalize_false_when_evidence_insufficient() -> None:
    state = _auto_finalize_state(
        "德国的AI政策是什么？",
        {"evidence_sufficient": False, "results": []},
    )
    assert _should_auto_finalize(state) is False


def test_should_auto_finalize_false_in_document_analysis_mode() -> None:
    # Analysis mode has no escalation tools anyway (see
    # test_document_analysis_mode_only_offers_internal_search) — the
    # backstop is scoped to Open Discussion mode only.
    state = _auto_finalize_state(
        "生成式人工智能对就业市场有什么影响？",
        {"evidence_sufficient": True, "results": [{"number": 1, "title": "Doc", "quote": "On topic."}]},
        answer_mode="analysis",
    )
    assert _should_auto_finalize(state) is False


def test_route_after_tools_returns_auto_finalize_when_eligible() -> None:
    state = _auto_finalize_state(
        "生成式人工智能对就业市场有什么影响？",
        {"evidence_sufficient": True, "results": [{"number": 1, "title": "Doc", "quote": "On topic."}]},
    )
    assert route_after_tools(state) == "auto_finalize"


def test_auto_finalize_node_synthesizes_prepare_final_answer_pair() -> None:
    state = {
        "citations": [{"number": 1, "title": "Doc"}, {"number": 2, "title": "Doc 2"}],
        "messages": [HumanMessage(content="q"), ToolMessage(content="{}", tool_call_id="c1", name="x")],
    }
    update = auto_finalize_node(state)
    ai_message, tool_message = update["messages"]
    assert ai_message.tool_calls[0]["name"] == "prepare_final_answer"
    assert ai_message.tool_calls[0]["args"]["citation_numbers"] == [1, 2]
    assert tool_message.name == "prepare_final_answer"
    assert json.loads(tool_message.content)["ready"] is True


def test_number_citations_reuses_number_for_duplicate_across_tool_calls() -> None:
    # Simulates the real failure this fixes: a second tool call (e.g.
    # search_web) sees a source already cited by an earlier call and must
    # reuse its number rather than the model guessing a fresh one.
    existing = [{"document_id": "d1", "chunk_id": "c1", "title": "A", "number": 1}]
    numbered, new = _number_citations(
        existing,
        [
            {"document_id": "d1", "chunk_id": "c1", "title": "A"},  # duplicate
            {"source_url": "https://example.com", "title": "Web result"},  # new
        ],
    )
    assert numbered[0]["number"] == 1
    assert numbered[1]["number"] == 2
    assert len(new) == 1
    assert new[0]["source_url"] == "https://example.com"
