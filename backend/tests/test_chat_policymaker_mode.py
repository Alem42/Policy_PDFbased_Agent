from uuid import uuid4

import pytest

from app.modules.chat import router as chat_router
from app.modules.chat.rag.graph.nodes import (
    _answer_mode,
    _response_mode,
    route_after_evidence_check,
)
from app.modules.chat.rag.graph.state import normalize_answer_mode
from app.modules.chat.rag.prompts import get_insufficient_evidence_message, get_system_prompt
from app.modules.chat.schemas import ChatRequest


def test_chat_request_accepts_policymaker_mode() -> None:
    payload = ChatRequest(
        question="What evidence is provided?",
        document_ids=[uuid4()],
        response_mode="policymaker",
    )
    assert payload.response_mode == "policymaker"


def test_policymaker_mode_is_preserved_in_rag_state() -> None:
    state = {"question": "test", "response_mode": "policymaker", "answer_mode": "analysis"}
    assert _response_mode(state) == "policymaker"


def test_policymaker_prompt_is_independent_and_document_grounded() -> None:
    prompt = get_system_prompt("policymaker", "analysis")
    lower = prompt.lower()

    assert "policymaker" in lower
    assert "policy implementation professionals" in lower
    assert "only the supplied excerpts" in lower
    assert "do not use pretrained model knowledge" in lower
    assert "do not independently recommend a policy option" in lower
    assert "do not make policy decisions for the user" in lower
    assert "## Relevant Cases" not in prompt
    assert "## Practical Recommendations" not in prompt


def test_policymaker_chat_request_is_normalized_to_document_analysis() -> None:
    assert normalize_answer_mode("policymaker", "chat") == "analysis"
    state = {"question": "test", "response_mode": "policymaker", "answer_mode": "chat"}
    assert _answer_mode(state) == "analysis"


def test_policymaker_weak_evidence_always_stops_generation() -> None:
    state = {
        "question": "What is the implementation cost?",
        "response_mode": "policymaker",
        "answer_mode": "chat",
        "evidence_sufficient": False,
    }
    assert route_after_evidence_check(state) == "insufficient_evidence"


def test_policymaker_insufficient_evidence_message_is_explicit() -> None:
    message = get_insufficient_evidence_message(
        "What is the implementation cost?",
        "No relevant implementation cost evidence was retrieved.",
        "policymaker",
    )
    lower = message.lower()
    assert "selected documents do not provide enough information" in lower
    assert "not filled this gap with general model knowledge" in lower
    assert "suggested next steps" not in lower


def test_existing_modes_keep_their_answer_mode_behaviour() -> None:
    assert normalize_answer_mode("researcher", "chat") == "chat"
    assert normalize_answer_mode("student", "chat") == "chat"
    assert normalize_answer_mode("researcher", "analysis") == "analysis"
    assert normalize_answer_mode("student", "analysis") == "analysis"


@pytest.mark.asyncio
async def test_policymaker_router_normalizes_chat_to_analysis(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_id = str(uuid4())
    captured: dict[str, str] = {}

    monkeypatch.setattr(
        chat_router.chat_history_repository,
        "create_session",
        lambda *_args, **_kwargs: session_id,
    )
    monkeypatch.setattr(
        chat_router.chat_history_repository,
        "add_message",
        lambda *_args, **_kwargs: str(uuid4()),
    )
    monkeypatch.setattr(
        chat_router.chat_history_repository,
        "touch_session",
        lambda *_args, **_kwargs: None,
    )

    def fake_run_pdf_qa(**kwargs):
        captured["answer_mode"] = kwargs["answer_mode"]
        return {
            "answer": "Grounded answer",
            "citations": [],
            "evidence_sufficient": True,
            "evidence_reason": None,
        }

    monkeypatch.setattr(chat_router, "run_pdf_qa", fake_run_pdf_qa)

    payload = ChatRequest(
        question="What evidence is provided?",
        document_ids=[uuid4()],
        response_mode="policymaker",
        answer_mode="chat",
    )
    response = await chat_router.chat(
        payload,
        {"id": str(uuid4()), "role": "user"},
    )

    assert captured["answer_mode"] == "analysis"
    assert response.response_mode == "policymaker"
    assert response.answer_mode == "analysis"
