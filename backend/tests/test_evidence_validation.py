from types import SimpleNamespace

import pytest

from app.modules.evidence_validation import service as guard
from app.modules.evidence_validation.config import EvidenceValidationConfig

CFG = EvidenceValidationConfig(enabled=True)
TEXT = "The target is 43% below 2005 levels by 2030. Guardian consent is required."
CHUNKS = [{"document_id": "d1", "text": TEXT}]


def fake(monkeypatch, schema, payload):
    monkeypatch.setattr(guard, "json_call", lambda *a, **k: (schema(**payload), {}))


def support(citation=1, quote=TEXT):
    return {"citation": citation, "quote": quote}


def claim(identifier="C1", **overrides):
    return {"id": identifier, "supported": True, "supports": [support()], **overrides}


def test_all_required_facts_must_have_current_literal_support(monkeypatch):
    plan = {"requirements": [{"id": "R1"}, {"id": "R2"}]}
    payload = {
        "requirements": [
            {"id": "R1", "supported": True, "answer_fact": "43%", "supports": [support()]},
            {"id": "R2", "supported": False, "reason": "Missing comparator"},
        ]
    }
    fake(monkeypatch, guard.Answerability, payload)
    assert not guard.answerability("Compare both", plan, CHUNKS, CFG)["allowed"]
    payload["requirements"][1] = {**payload["requirements"][0], "id": "R2"}
    fake(monkeypatch, guard.Answerability, payload)
    assert guard.answerability("Compare both", plan, CHUNKS, CFG)["allowed"]


@pytest.mark.parametrize("items", [[], ["R1"], ["R1", "R1"], ["R1", "R3"]])
def test_answerability_rejects_missing_duplicate_or_unknown_requirements(monkeypatch, items):
    if not items:
        monkeypatch.setattr(guard, "json_call", lambda *a, **k: (_ for _ in ()).throw(ValueError()))
    else:
        fake(
            monkeypatch,
            guard.Answerability,
            {
                "requirements": [
                    {"id": i, "supported": True, "answer_fact": "43%", "supports": [support()]}
                    for i in items
                ]
            },
        )
    assert not guard.answerability(
        "both", {"requirements": [{"id": "R1"}, {"id": "R2"}]}, CHUNKS, CFG
    )["allowed"]


@pytest.mark.parametrize(
    "bad", [support(2), support(quote="A fabricated source quote"), support(quote="short")]
)
def test_literal_quotes_and_citation_bounds_are_deterministic(monkeypatch, bad):
    fake(monkeypatch, guard.Claims, {"coverage_complete": True, "claims": [claim(supports=[bad])]})
    assert not guard.validate_answer("target", "The target is 43%. [1]", CHUNKS, CFG)["allowed"]


def test_rejects_incorrect_number_even_when_model_approves(monkeypatch):
    fake(monkeypatch, guard.Claims, {"coverage_complete": True, "claims": [claim()]})
    assert not guard.validate_answer("target", "The target is 83%. [1]", CHUNKS, CFG)["allowed"]
    assert guard.validate_answer("target", "The target is 43%. [1]", CHUNKS, CFG)["allowed"]


@pytest.mark.parametrize("answer", ["The target is 43%.", "The target is 43%. [2]"])
def test_missing_and_out_of_bounds_answer_markers_block_before_model(monkeypatch, answer):
    monkeypatch.setattr(guard, "json_call", lambda *a, **k: pytest.fail("Should not call a model"))
    assert not guard.validate_answer("target", answer, CHUNKS, CFG)["allowed"]


@pytest.mark.parametrize("prefix", ["**", "### "])
def test_bold_and_heading_assertions_cannot_escape_coverage(monkeypatch, prefix):
    fake(monkeypatch, guard.Claims, {"coverage_complete": True, "claims": [claim()]})
    answer = "The target is 43%. [1]\n" + prefix + "Guardian consent is unnecessary. [1]"
    if prefix == "**":
        answer += "**"
    report = guard.validate_answer("target and consent", answer, CHUNKS, CFG)
    assert not report["allowed"]  # C2 was omitted by the model


def test_support_must_match_citation_on_its_own_answer_unit(monkeypatch):
    fake(monkeypatch, guard.Claims, {"coverage_complete": True, "claims": [claim(), claim("C2")]})
    report = guard.validate_answer(
        "target and consent",
        "The target is 43%. [1]\nGuardian consent is required. [2]",
        CHUNKS + [{"document_id": "d2", "text": "Unrelated appendix."}],
        CFG,
    )
    assert not report["allowed"]


@pytest.mark.parametrize("function", ["answerability", "validate_answer", "check_cited_answer"])
def test_fail_closed_on_validator_or_provenance_outage(monkeypatch, function):
    def broken(*a, **k):
        raise TimeoutError("Simulated outage")

    monkeypatch.setattr(guard, "json_call", broken)
    monkeypatch.setattr(guard, "chunks_for_citations", broken)
    if function == "answerability":
        result = guard.answerability("target", {"requirements": [{"id": "R1"}]}, CHUNKS, CFG)
    elif function == "validate_answer":
        result = guard.validate_answer("target", "43%. [1]", CHUNKS, CFG)
    else:
        result = guard.check_cited_answer("target", "43%. [1]", [], CFG)
    assert not result["allowed"] and "closed" in result["reason"]


async def test_stream_never_emits_unchecked_draft(monkeypatch):
    from app.modules.chat.rag import generation

    state = {"checked": False}

    class Client:
        async def astream(self, messages, **kwargs):
            yield SimpleNamespace(content="An unsupported ")
            yield SimpleNamespace(content="claim. [1]")

    def validate(*a, **k):
        state["checked"] = True
        assert a[1] == "An unsupported claim. [1]"
        return {"allowed": False}

    monkeypatch.setattr(guard, "config", lambda: CFG)
    monkeypatch.setattr(guard, "check_cited_answer", validate)
    monkeypatch.setattr(generation, "resolve_generation_target", lambda _: ("test", "model", {}))
    monkeypatch.setattr(generation, "create_chat_client", lambda *a, **k: Client())
    received = []
    async for text in generation.generate_answer_streaming("target", TEXT):
        assert state["checked"]
        received.append(text)
    assert received == [guard.REFUSAL]


def test_candidate_quota_and_subquestion_reservations_are_independent_of_gold():
    from app.modules.retrieval.coverage import allocate

    rows = [{"chunk_id": str(i), "document_id": "a" if i < 3 else "b"} for i in range(5)]
    chosen = allocate(rows, 3, groups=[[rows[2]]], per_document=True)
    assert [r["chunk_id"] for r in chosen] == ["2", "0", "3"]
    assert (
        len({r["chunk_id"] for r in allocate(rows, 9, groups=[rows, rows], per_document=True)}) == 5
    )


async def test_react_sse_suppresses_message_draft_until_validated_node_update(monkeypatch):
    from app.modules.chat.application import streaming

    class Graph:
        async def astream(self, *a, **k):
            yield (
                "messages",
                (
                    SimpleNamespace(content="Secret invalid draft"),
                    {"langgraph_node": "final_generation"},
                ),
            )
            yield (
                "updates",
                {"final_generation": {"messages": [SimpleNamespace(content=guard.REFUSAL)]}},
            )

    async def empty(*a, **k):
        return []

    monkeypatch.setattr(guard, "config", lambda: CFG)
    monkeypatch.setattr(streaming.react_orchestrator, "graph", lambda: Graph())
    monkeypatch.setattr(streaming.chat_turn_service, "message_steps", empty)
    monkeypatch.setattr(streaming.chat_turn_service, "fail", empty)
    stream = streaming.stream_agent_events(
        {},
        config={},
        session_id="s",
        response_mode="researcher",
        answer_mode="analysis",
        assistant_message_id="m",
    )
    event = await anext(stream)
    assert "Secret invalid draft" not in event and "blocked this answer" in event
    await stream.aclose()


def test_default_chat_top_k_uses_selected_setting_and_allows_explicit_override(monkeypatch):
    from app.modules.chat.schemas import ChatRequest

    monkeypatch.setattr(
        guard, "config", lambda: EvidenceValidationConfig(enabled=True, default_top_k=4)
    )
    assert ChatRequest(question="target").top_k == 4
    assert ChatRequest(question="target", top_k=8).top_k == 8
    monkeypatch.setattr(guard, "config", lambda: EvidenceValidationConfig(enabled=False))
    assert ChatRequest(question="target").top_k == 6


def test_equivalent_authoritative_source_satisfies_gold_requirement():
    from app.modules.evaluation.metrics import evidence_metrics
    from app.modules.evaluation.validated import requirement_recall

    alternatives = [
        {"source_id": "primary", "page": 1, "quote": "Govern Identify Protect"},
        {"source_id": "secondary", "page": 13, "quote": "Govern Identify Protect"},
    ]
    mapping = {"secondary": "d2"}
    chunks = [
        {
            "document_id": "d2",
            "page_start": 13,
            "page_end": 13,
            "text": "The functions are Govern Identify Protect and others.",
        }
    ]
    assert (
        requirement_recall({"requirements": [{"alternatives": alternatives}]}, chunks, mapping) == 1
    )
    assert (
        evidence_metrics([{"alternatives": alternatives}], chunks, mapping)["evidence_recall_at_k"]
        == 1
    )
    assert evidence_metrics([], chunks, mapping)["evidence_recall_at_k"] is None


def test_uncited_introduction_is_audited_with_the_following_cited_fact(monkeypatch):
    captured = {}

    def call(model, system, payload, schema, **kwargs):
        captured.update(payload)
        return guard.Claims(coverage_complete=True, claims=[claim()]), {}

    monkeypatch.setattr(guard, "json_call", call)
    result = guard.validate_answer(
        "target", "The target is:\n43% below 2005 levels by 2030. [1]", CHUNKS, CFG
    )
    assert result["allowed"]
    assert len(captured["units"]) == 1
    assert "The target is:" in captured["units"]["C1"]["text"]
    assert captured["units"]["C1"]["allowed_citations"] == [1]


def test_question_contract_cannot_silently_truncate_mandatory_facts(monkeypatch):
    fake(
        monkeypatch,
        guard.Plan,
        {
            "coverage_complete": False,
            "requirements": [{"id": "R1", "question": "One of many required facts"}],
        },
    )
    guard._plan.cache_clear()
    with pytest.raises(ValueError, match="Invalid|excessive"):
        guard.plan_question("Answer more mandatory facts than the budget permits", CFG)
    guard._plan.cache_clear()


def test_claim_protocol_schema_rejects_renamed_ids_and_nonliteral_quotes():
    schema = guard.claim_schema({"C1": "The target is 43%. [1]"}, guard.sources_from_chunks(CHUNKS))
    with pytest.raises(ValueError):
        schema.model_validate({"coverage_complete": True, "claims": [claim("C1a")]})
    with pytest.raises(ValueError):
        schema.model_validate(
            {
                "coverage_complete": True,
                "claims": [claim(supports=[support(quote="A fabricated literal source quote")])],
            }
        )
    assert schema.model_validate({"coverage_complete": True, "claims": [claim()]}).coverage_complete


def test_protocol_errors_retry_once_with_diagnostics_and_then_pass(monkeypatch):
    import json

    calls = []
    outputs = [
        {"coverage_complete": True, "claims": [claim("C1a")]},
        {"coverage_complete": True, "claims": [claim()]},
    ]

    class Client:
        def invoke(self, messages):
            calls.append(list(messages))
            return SimpleNamespace(content=json.dumps(outputs[len(calls) - 1]), usage_metadata={})

    monkeypatch.setattr(guard, "resolve_generation_target", lambda _: ("test", "model", {}))
    monkeypatch.setattr(guard, "create_chat_client", lambda *a, **k: Client())
    result = guard.validate_answer("target", "The target is 43%. [1]", CHUNKS, CFG)
    assert result["allowed"] and result["telemetry"]["attempts"] == 2
    assert "protocol validation" in calls[1][-1].content
