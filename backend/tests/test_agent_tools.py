"""Pure-logic pieces of the web-search agent: evidence gating, citation
dedup, and admin-only tool filtering. These don't hit the database."""

from __future__ import annotations

import json

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from app.modules.chat.rag.agent import tools as agent_tools
from app.modules.chat.rag.agent.graph import (
    ALL_TOOLS,
    NON_ADMIN_TOOLS,
    TOOL_CALL_LIMITS,
    _enforce_tier_order,
    _messages_for_current_turn,
    _question_requests_web_search,
    _question_requires_web_check,
    _tools_for,
    agent_node,
    record_tool_call_node,
    route_after_tools,
)
from app.modules.chat.rag.agent.prompts import get_agent_system_prompt
from app.modules.chat.rag.agent.state import AgentState, add_citations, add_web_pages_seen
from app.modules.chat.rag.agent.tools import (
    SUFFICIENT_EVIDENCE_REMINDER,
    _cosine_distance,
    _number_citations,
    _resolve_web_reference,
    _results_with_evidence_text,
    _score_web_results,
    import_web_page,
    search_web,
)
from app.modules.web_search.contracts import WebSearchResult


def test_cosine_distance_identical_vectors_is_zero() -> None:
    assert _cosine_distance([1.0, 0.0], [1.0, 0.0]) == pytest.approx(0.0)


def test_cosine_distance_orthogonal_vectors_is_one() -> None:
    assert _cosine_distance([1.0, 0.0], [0.0, 1.0]) == pytest.approx(1.0)


def test_cosine_distance_zero_vector_is_max_distance() -> None:
    assert _cosine_distance([0.0, 0.0], [1.0, 0.0]) == 1.0


def test_agent_tool_results_keep_full_text_without_expanding_citation_quote() -> None:
    numbered = [{"number": 1, "chunk_id": "chunk-1", "quote": "short quote"}]
    full_text = "start " + ("middle " * 100) + "deadline 15 March 2027"
    results = _results_with_evidence_text(
        numbered,
        [{"chunk_id": "chunk-1", "text": full_text}],
    )
    assert results[0]["text"] == full_text
    assert numbered[0]["quote"] == "short quote"


def test_score_web_results_empty_is_insufficient() -> None:
    sufficient, reason, candidates = _score_web_results("query", [])
    assert sufficient is False
    assert candidates == []
    assert reason


def test_score_web_results_close_result_passes_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.modules.chat.rag.agent.tools as tools_module

    # Same vector for query and the one result -> distance 0, well under threshold.
    monkeypatch.setattr(tools_module.web_evidence.embedding, "embed_query", lambda text: [1.0, 0.0])
    monkeypatch.setattr(
        tools_module.web_evidence.embedding,
        "embed_documents",
        lambda texts: [[1.0, 0.0] for _ in texts],
    )
    monkeypatch.setattr(tools_module.web_evidence, "max_vector_distance", lambda: 0.45)
    monkeypatch.setattr(tools_module.web_evidence, "reranker_enabled", lambda: False)

    results = [WebSearchResult(url="https://example.com", title="Example", content="relevant text")]
    sufficient, reason, candidates = _score_web_results("query", results)

    assert sufficient is True
    assert reason is None
    assert candidates[0]["passed"] is True


def test_score_web_results_far_result_fails_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.modules.chat.rag.agent.tools as tools_module

    # Orthogonal vectors -> distance 1.0, well over any sane threshold.
    monkeypatch.setattr(tools_module.web_evidence.embedding, "embed_query", lambda text: [1.0, 0.0])
    monkeypatch.setattr(
        tools_module.web_evidence.embedding,
        "embed_documents",
        lambda texts: [[0.0, 1.0] for _ in texts],
    )
    monkeypatch.setattr(tools_module.web_evidence, "max_vector_distance", lambda: 0.45)
    monkeypatch.setattr(tools_module.web_evidence, "reranker_enabled", lambda: False)

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


def test_react_citations_reset_between_checkpointed_turns() -> None:
    builder = StateGraph(AgentState)
    builder.add_node("finish", lambda _state: {})
    builder.add_edge(START, "finish")
    builder.add_edge("finish", END)
    graph = builder.compile(checkpointer=MemorySaver())
    config = {"configurable": {"thread_id": "citation-reset-test"}}

    graph.invoke(
        {
            "messages": [HumanMessage(content="first question")],
            "citations": [{"number": 1, "source_url": "https://old.example"}],
        },
        config=config,
    )
    graph.invoke(
        {"messages": [HumanMessage(content="second question")], "citations": []},
        config=config,
    )

    assert graph.get_state(config).values["citations"] == []


@pytest.mark.asyncio
async def test_search_web_preserves_citations_from_earlier_tool_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_search(_query: str, *, limit: int) -> list[WebSearchResult]:
        assert limit == 5
        return []

    monkeypatch.setattr(agent_tools.web_search_service, "search", fake_search)
    monkeypatch.setattr(
        agent_tools,
        "_score_web_results",
        lambda _query, _results: (
            True,
            "enough evidence",
            [
                {
                    "title": "New web source",
                    "url": "https://new.example",
                    "text": "Relevant evidence",
                    "passed": True,
                }
            ],
        ),
    )
    existing = [
        {
            "number": 1,
            "document_id": "doc-1",
            "chunk_id": "chunk-1",
            "title": "Earlier document source",
        }
    ]

    command = await search_web.coroutine(
        query="compare with the web",
        decision_reason="The user requested a web comparison.",
        tool_call_id="call-web",
        citations=existing,
        evidence_sources=["internal"],
        turn_citation_keys=[["doc-1", "chunk-1", None]],
        web_pages_seen=[],
        messages=[HumanMessage(content="compare with the web")],
    )

    assert command.update["citations"] == [
        existing[0],
        {
            "title": "New web source",
            "source_url": "https://new.example",
            "quote": "Relevant evidence",
            "source_type": "web",
            "tier": "web",
            "number": 2,
        },
    ]


@pytest.mark.asyncio
async def test_search_web_tags_results_with_the_current_turn_index(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_search(_query: str, *, limit: int) -> list[WebSearchResult]:
        return []

    monkeypatch.setattr(agent_tools.web_search_service, "search", fake_search)
    monkeypatch.setattr(
        agent_tools,
        "_score_web_results",
        lambda _query, _results: (
            True,
            "enough evidence",
            [
                {
                    "title": "Second-turn source",
                    "url": "https://second-turn.example",
                    "text": "Relevant evidence",
                    "passed": True,
                }
            ],
        ),
    )

    # Two prior HumanMessages (turn 1's question, turn 2's question) plus the
    # current one being answered -> this call belongs to turn 3.
    command = await search_web.coroutine(
        query="q3",
        decision_reason="why",
        tool_call_id="call-web",
        citations=[],
        evidence_sources=[],
        turn_citation_keys=[],
        web_pages_seen=[{"title": "Turn 1 source", "source_url": "https://t1.example", "passed": True, "turn_index": 1}],
        messages=[
            HumanMessage(content="turn 1"),
            HumanMessage(content="turn 2"),
            HumanMessage(content="turn 3"),
        ],
    )

    assert command.update["web_pages_seen"] == [
        {"title": "Turn 1 source", "source_url": "https://t1.example", "passed": True, "turn_index": 1},
        {
            "title": "Second-turn source",
            "source_url": "https://second-turn.example",
            "passed": True,
            "turn_index": 3,
        },
    ]


def test_add_web_pages_seen_deduplicates_by_url_and_caps_length() -> None:
    existing = [{"source_url": "https://a.example", "title": "A", "turn_index": 1}]
    new = [
        {"source_url": "https://a.example", "title": "A (refetched)", "turn_index": 2},  # dup, dropped
        {"source_url": "https://b.example", "title": "B", "turn_index": 2},
    ]
    merged = add_web_pages_seen(existing, new)
    assert [item["source_url"] for item in merged] == ["https://a.example", "https://b.example"]

    overflow = [{"source_url": f"https://{i}.example", "title": str(i)} for i in range(60)]
    capped = add_web_pages_seen([], overflow)
    assert len(capped) == 50
    # Oldest entries are dropped first, so the tail is preserved.
    assert capped[-1]["source_url"] == "https://59.example"


def test_resolve_web_reference_ordinal_within_turn_scope() -> None:
    pool = [
        {"source_url": "https://t1-a.example", "title": "Turn 1 A", "turn_index": 1},
        {"source_url": "https://t1-b.example", "title": "Turn 1 B", "turn_index": 1},
        {"source_url": "https://t2-a.example", "title": "Turn 2 A", "turn_index": 2},
    ]
    resolved, candidates = _resolve_web_reference(pool, turn_hint=1, reference_hint="second")
    assert resolved == ("https://t1-b.example", "Turn 1 B")
    assert candidates == pool[:2]


def test_resolve_web_reference_last_without_turn_hint_uses_whole_session() -> None:
    pool = [
        {"source_url": "https://old.example", "title": "Old", "turn_index": 1},
        {"source_url": "https://new.example", "title": "New", "turn_index": 3},
    ]
    resolved, _candidates = _resolve_web_reference(pool, turn_hint=None, reference_hint="last")
    assert resolved == ("https://new.example", "New")


def test_resolve_web_reference_title_fragment_match() -> None:
    pool = [
        {"source_url": "https://gdpr.example", "title": "GDPR Enforcement Review", "turn_index": 1},
        {"source_url": "https://other.example", "title": "Unrelated", "turn_index": 1},
    ]
    resolved, _candidates = _resolve_web_reference(pool, turn_hint=None, reference_hint="GDPR")
    assert resolved == ("https://gdpr.example", "GDPR Enforcement Review")


def test_resolve_web_reference_exact_match_wins_over_a_longer_title_containing_it() -> None:
    # Regression: a real webpage's title routinely turns up verbatim inside
    # a DIFFERENT candidate's longer title (a write-up quoting it). A plain
    # substring scan finds both and calls it ambiguous even when the answer
    # named one of them exactly — this is what actually happened importing
    # "America's AI Action Plan" (whitehouse.gov) alongside a White & Case
    # law-firm article whose title embeds that same phrase.
    pool = [
        {
            "source_url": "https://whitehouse.gov/plan.pdf",
            "title": "America's AI Action Plan",
            "turn_index": 1,
        },
        {
            "source_url": "https://whitecase.com/insight",
            "title": (
                'White House unveils comprehensive AI strategy: "Winning the race: '
                'America\'s AI action plan" | White & Case LLP'
            ),
            "turn_index": 1,
        },
    ]
    resolved, candidates = _resolve_web_reference(pool, None, "America's AI Action Plan")
    assert resolved == ("https://whitehouse.gov/plan.pdf", "America's AI Action Plan")
    assert candidates == [pool[0]]


def test_resolve_web_reference_ambiguous_returns_no_match_and_full_pool() -> None:
    pool = [
        {"source_url": "https://a.example", "title": "A", "turn_index": 1},
        {"source_url": "https://b.example", "title": "B", "turn_index": 1},
    ]
    resolved, candidates = _resolve_web_reference(pool, turn_hint=None, reference_hint=None)
    assert resolved is None
    assert candidates == pool


def test_resolve_web_reference_empty_pool_returns_no_match() -> None:
    resolved, candidates = _resolve_web_reference([], turn_hint=None, reference_hint="last")
    assert resolved is None
    assert candidates == []


@pytest.mark.asyncio
async def test_import_web_page_reports_error_when_no_pages_seen_this_session() -> None:
    # Nothing to disambiguate between (empty pool) -> a plain error, no
    # interrupt. Raising from the monkeypatched interrupt makes it loud if
    # this regresses into calling it anyway.
    def _fail_if_called(_payload):
        raise AssertionError("should not interrupt with nothing to disambiguate")

    import app.modules.chat.rag.agent.tools as tools_module

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(tools_module, "interrupt", _fail_if_called)
        command = await import_web_page.coroutine(
            tool_call_id="call-import",
            is_admin=True,
            user_id="user-1",
            citations=[],
            web_pages_seen=[],
        )

    payload = json.loads(command.update["messages"][0].content)
    assert payload["imported"] is False
    assert "candidates" not in payload


@pytest.mark.asyncio
async def test_import_web_page_asks_the_user_itself_using_real_candidates_when_ambiguous(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # This is the fix for the bug where the model composed its own (possibly
    # inaccurate) candidate list and called ask_user with it before ever
    # calling import_web_page: the tool now disambiguates itself, using the
    # real titles from web_pages_seen, regardless of what the model does.
    seen_prompts: list[dict] = []
    answers = iter(["B", True])  # first interrupt (choice), then confirm_import

    def fake_interrupt(payload):
        seen_prompts.append(payload)
        return next(answers)

    monkeypatch.setattr(agent_tools, "interrupt", fake_interrupt)

    class FakeResult:
        document = {"id": "doc-b"}
        title = "B"
        source_url = "https://b.example"
        was_duplicate = False

    async def fake_import_page(request):
        assert request.url == "https://b.example"
        assert request.title == "B"
        return FakeResult()

    monkeypatch.setattr(agent_tools.web_import_service, "import_page", fake_import_page)

    command = await import_web_page.coroutine(
        tool_call_id="call-import",
        is_admin=True,
        user_id="user-1",
        citations=[],
        web_pages_seen=[
            {"source_url": "https://a.example", "title": "A", "passed": True, "turn_index": 1},
            {"source_url": "https://b.example", "title": "B", "passed": True, "turn_index": 1},
        ],
    )

    assert seen_prompts[0]["type"] == "ask_user"
    assert seen_prompts[0]["mode"] == "choice"
    assert set(seen_prompts[0]["options"]) == {"A", "B"}
    payload = json.loads(command.update["messages"][0].content)
    assert payload["imported"] is True
    assert payload["document_id"] == "doc-b"


@pytest.mark.asyncio
async def test_import_web_page_reports_error_when_disambiguation_answer_does_not_match(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(agent_tools, "interrupt", lambda _payload: "something unrelated")

    command = await import_web_page.coroutine(
        tool_call_id="call-import",
        is_admin=True,
        user_id="user-1",
        citations=[],
        web_pages_seen=[
            {"source_url": "https://a.example", "title": "A", "passed": True, "turn_index": 1},
            {"source_url": "https://b.example", "title": "B", "passed": True, "turn_index": 1},
        ],
    )

    payload = json.loads(command.update["messages"][0].content)
    assert payload["imported"] is False
    assert "something unrelated" in payload["error"]
    assert {c["source_url"] for c in payload["candidates"]} == {
        "https://a.example",
        "https://b.example",
    }


@pytest.mark.asyncio
async def test_import_web_page_resolves_reference_hint_without_explicit_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(agent_tools, "interrupt", lambda _payload: True)

    class FakeResult:
        document = {"id": "doc-imported"}
        title = "Turn 1 B"
        source_url = "https://t1-b.example"
        was_duplicate = False

    async def fake_import_page(request):
        assert request.url == "https://t1-b.example"
        assert request.title == "Turn 1 B"
        return FakeResult()

    monkeypatch.setattr(agent_tools.web_import_service, "import_page", fake_import_page)

    command = await import_web_page.coroutine(
        tool_call_id="call-import",
        is_admin=True,
        user_id="user-1",
        citations=[],
        web_pages_seen=[
            {"source_url": "https://t1-a.example", "title": "Turn 1 A", "passed": True, "turn_index": 1},
            {"source_url": "https://t1-b.example", "title": "Turn 1 B", "passed": True, "turn_index": 1},
        ],
        turn_hint=1,
        reference_hint="second",
    )

    payload = json.loads(command.update["messages"][0].content)
    assert payload["imported"] is True
    assert payload["document_id"] == "doc-imported"


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


def test_sufficient_evidence_reminder_preserves_pending_web_check() -> None:
    reminder = SUFFICIENT_EVIDENCE_REMINDER.lower()

    assert "web comparison or freshness check" in reminder
    assert "if" in reminder
    assert "otherwise" in reminder


def test_agent_prompt_uses_configured_tool_limits() -> None:
    limits = {
        **TOOL_CALL_LIMITS,
        "search_internal_documents": 2,
        "search_full_corpus": 7,
    }

    prompt = get_agent_system_prompt(
        "researcher",
        "chat",
        is_admin=False,
        tool_limits=limits,
    )
    normalized_prompt = " ".join(prompt.split())

    assert "- search_internal_documents: 2" in prompt
    assert "- search_full_corpus: 7" in prompt
    assert "up to 2 calls are available" in normalized_prompt
    assert "Up to 7 calls for materially different" in normalized_prompt
    assert "at most five" not in prompt.lower()


def test_tools_for_uses_the_same_supplied_limits_snapshot() -> None:
    limits = {**TOOL_CALL_LIMITS, "search_internal_documents": 2}

    names = {
        tool.name
        for tool in _tools_for(
            False,
            "chat",
            {"search_internal_documents": 2},
            limits=limits,
        )
    }

    assert "search_internal_documents" not in names


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
        "tokens_used": None,
    }


def test_record_tool_call_captures_tokens_used_from_usage_metadata() -> None:
    message = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "search_internal_documents",
                "args": {"query": "q", "decision_reason": "why"},
                "id": "call-1",
                "type": "tool_call",
            }
        ],
        usage_metadata={"input_tokens": 200, "output_tokens": 30, "total_tokens": 230},
    )
    update = record_tool_call_node({"messages": [message], "tool_call_counts": {}})
    assert update["last_tool_call"]["tokens_used"] == 230


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


async def test_agent_retries_when_provider_omits_required_tool(monkeypatch) -> None:
    import app.modules.chat.rag.agent.graph as graph_module

    responses = [
        AIMessage(content="I will answer directly."),
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "search_internal_documents",
                    "args": {"query": "AI safety", "decision_reason": "Find selected evidence."},
                    "id": "call-valid",
                    "type": "tool_call",
                }
            ],
        ),
    ]

    class FakeClient:
        def bind_tools(self, tools, **kwargs):
            return self

        async def ainvoke(self, messages):
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
            "messages": [HumanMessage(content="Tell me about AI safety")],
            "answer_mode": "chat",
            "is_admin": False,
        }
    )

    assert result["messages"][0].tool_calls[0]["name"] == "search_internal_documents"


async def test_agent_uses_safe_fallback_after_repeated_missing_tool_calls(monkeypatch) -> None:
    import app.modules.chat.rag.agent.graph as graph_module

    class FakeClient:
        def bind_tools(self, tools, **kwargs):
            return self

        async def ainvoke(self, messages):
            return AIMessage(content="A prose response that violates the tool protocol.")

    monkeypatch.setattr(
        graph_module,
        "resolve_generation_target",
        lambda model: ("fake", "model", {}),
    )
    monkeypatch.setattr(graph_module, "create_chat_client", lambda provider, model: FakeClient())
    monkeypatch.setattr(graph_module, "get_agent_system_prompt", lambda *args, **kwargs: "prompt")

    result = await agent_node(
        {
            "messages": [HumanMessage(content="Tell me about AI safety")],
            "answer_mode": "chat",
            "is_admin": False,
        }
    )

    call = result["messages"][0].tool_calls[0]
    assert call["name"] == "search_internal_documents"
    assert call["args"]["query"] == "Tell me about AI safety"


async def test_agent_rebuilds_provider_message_when_multiple_tools_are_returned(
    monkeypatch,
) -> None:
    import app.modules.chat.rag.agent.graph as graph_module

    calls = [
        {
            "name": "search_internal_documents",
            "args": {"query": "AI safety", "decision_reason": "Use selected files."},
            "id": "call-1",
            "type": "tool_call",
        },
        {
            "name": "search_full_corpus",
            "args": {"query": "AI safety", "decision_reason": "Use the library."},
            "id": "call-2",
            "type": "tool_call",
        },
    ]

    class FakeClient:
        def bind_tools(self, tools, **kwargs):
            return self

        async def ainvoke(self, messages):
            return AIMessage(
                content="",
                additional_kwargs={"tool_calls": [{"id": "raw-1"}, {"id": "raw-2"}]},
                tool_calls=calls,
            )

    monkeypatch.setattr(
        graph_module,
        "resolve_generation_target",
        lambda model: ("fake", "model", {}),
    )
    monkeypatch.setattr(graph_module, "create_chat_client", lambda provider, model: FakeClient())
    monkeypatch.setattr(graph_module, "get_agent_system_prompt", lambda *args, **kwargs: "prompt")

    result = await agent_node(
        {
            "messages": [HumanMessage(content="Tell me about AI safety")],
            "answer_mode": "chat",
            "is_admin": False,
        }
    )

    message = result["messages"][0]
    assert [call["id"] for call in message.tool_calls] == ["call-1"]
    assert "tool_calls" not in message.additional_kwargs


def test_prepare_final_answer_routes_to_streaming_generation() -> None:
    state = {
        "answer_mode": "chat",
        "messages": [
            ToolMessage(
                content='{"ready": true}',
                tool_call_id="call-1",
                name="prepare_final_answer",
            )
        ],
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


def test_analysis_mode_search_returns_to_agent_for_prepare_step() -> None:
    state = {
        "answer_mode": "analysis",
        "messages": [
            ToolMessage(
                content='{"evidence_sufficient": false, "reason": "No relevant passages."}',
                tool_call_id="call-1",
                name="search_internal_documents",
            )
        ],
    }

    assert route_after_tools(state) == "agent"


def test_analysis_prepare_with_no_evidence_routes_to_deterministic_refusal() -> None:
    state = {
        "answer_mode": "analysis",
        "evidence_sources": [],
        "messages": [
            ToolMessage(
                content='{"ready": true}',
                tool_call_id="call-2",
                name="prepare_final_answer",
            )
        ],
    }

    assert route_after_tools(state) == "insufficient_evidence"


async def test_analysis_after_search_only_offers_prepare_final_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.modules.chat.rag.agent.graph as graph_module

    class FakeClient:
        def bind_tools(self, tools, **kwargs):
            assert {tool.name for tool in tools} == {"prepare_final_answer"}
            return self

        async def ainvoke(self, messages):
            return AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "prepare_final_answer",
                        "args": {
                            "answer_plan": "Explain that selected evidence was insufficient.",
                            "citation_numbers": [],
                        },
                        "id": "call-prepare",
                        "type": "tool_call",
                    }
                ],
            )

    monkeypatch.setattr(
        graph_module,
        "resolve_generation_target",
        lambda model: ("fake", "model", {}),
    )
    monkeypatch.setattr(graph_module, "create_chat_client", lambda provider, model: FakeClient())
    monkeypatch.setattr(graph_module, "active_limits", lambda: dict(TOOL_CALL_LIMITS))
    monkeypatch.setattr(graph_module, "get_agent_system_prompt", lambda *args, **kwargs: "prompt")

    result = await agent_node(
        {
            "messages": [
                HumanMessage(content="What do the selected documents say?"),
                ToolMessage(
                    content='{"evidence_sufficient": false}',
                    tool_call_id="call-search",
                    name="search_internal_documents",
                ),
            ],
            "answer_mode": "analysis",
            "is_admin": False,
        }
    )

    assert result["messages"][0].tool_calls[0]["name"] == "prepare_final_answer"


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("Compare policy A with policy B.", False),
        ("Compare the selected documents against the web.", True),
        ("What is the latest version of this policy?", True),
        ("\u8fd9\u9879\u653f\u7b56\u7684\u6700\u65b0\u7248\u672c\u662f\u4ec0\u4e48\uff1f", True),
        ("Use the latest selected document, but do not search the web.", False),
        ("\u53ea\u4f7f\u7528\u6587\u6863\uff0c\u4e0d\u8981\u4e0a\u7f51\u6838\u5b9e\u3002", False),
    ],
)
def test_web_check_trigger_matches_prompt_policy(question: str, expected: bool) -> None:
    state = {"messages": [HumanMessage(content=question)]}

    assert _question_requires_web_check(state) is expected


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("What does the policy say about privacy?", False),
        ("Please search the web for the newest AI act.", True),
        ("帮我上网搜一下新加坡的AI政策。", True),
        ("Search online, but actually no web search please.", False),
    ],
)
def test_explicit_web_request_detection(question: str, expected: bool) -> None:
    state = {"messages": [HumanMessage(content=question)]}

    assert _question_requests_web_search(state) is expected


def _chat_tools(counts: dict[str, int]) -> set[str]:
    state = {
        "answer_mode": "chat",
        "tool_call_counts": counts,
        "messages": [HumanMessage(content="What is the EU AI Act about?")],
    }
    available = _enforce_tier_order(_tools_for(False, "chat", counts), state)
    return {tool.name for tool in available}


def test_tier_order_hides_escalation_tiers_before_internal_search_ran() -> None:
    names = _chat_tools({})
    assert "search_internal_documents" in names
    assert "search_full_corpus" not in names
    assert "search_web" not in names


def test_tier_order_offers_escalation_after_internal_search_ran() -> None:
    names = _chat_tools({"search_internal_documents": 1})
    assert "search_full_corpus" in names
    assert "search_web" in names


def test_tier_order_allows_web_immediately_on_explicit_user_request() -> None:
    state = {
        "answer_mode": "chat",
        "tool_call_counts": {},
        "messages": [HumanMessage(content="Please search the web for this.")],
    }
    available = _enforce_tier_order(_tools_for(False, "chat", {}), state)
    names = {tool.name for tool in available}
    assert "search_web" in names
    assert "search_full_corpus" not in names


def test_tier_order_does_not_gate_analysis_mode() -> None:
    state = {
        "answer_mode": "analysis",
        "tool_call_counts": {},
        "messages": [HumanMessage(content="Summarise the document.")],
    }
    available = _enforce_tier_order(_tools_for(False, "analysis", {}), state)
    assert {tool.name for tool in available} == {
        "search_internal_documents",
        "prepare_final_answer",
    }


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


def _post_search_state(question: str, payload: dict, *, answer_mode: str = "chat") -> dict:
    return {
        "answer_mode": answer_mode,
        "tool_call_counts": {"search_internal_documents": 1},
        "citations": [],
        "messages": [
            HumanMessage(content=question),
            ToolMessage(
                content=json.dumps(payload, ensure_ascii=False),
                tool_call_id="call-1",
                name="search_internal_documents",
            ),
        ],
    }


def test_route_after_tools_returns_to_agent_even_when_evidence_sufficient() -> None:
    # There is no auto-finalize shortcut: a sufficient search result still
    # hands the turn back to the model, which must explicitly call
    # prepare_final_answer before anything streams to the user.
    state = _post_search_state(
        "生成式人工智能对就业市场有什么影响？",
        {
            "evidence_sufficient": True,
            "results": [{"number": 1, "title": "Doc", "quote": "On topic."}],
        },
    )
    assert route_after_tools(state) == "agent"


def test_route_after_tools_finalizes_only_after_prepare_final_answer() -> None:
    state = {
        "answer_mode": "chat",
        "messages": [
            HumanMessage(content="q"),
            ToolMessage(
                content=json.dumps({"ready": True}),
                tool_call_id="call-2",
                name="prepare_final_answer",
            ),
        ],
    }
    assert route_after_tools(state) == "final_generation"


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
