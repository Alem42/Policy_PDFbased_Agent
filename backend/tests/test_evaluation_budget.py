import asyncio
from unittest.mock import Mock

import pytest
from langchain_core.messages import HumanMessage

from app.core.ai import budget
from app.modules.evaluation.config import EvaluationConfig
from app.modules.evaluation.sampling import balanced


def test_reservations_reject_before_the_next_request_and_do_not_refund_retries():
    value = budget.LLMBudget(token_limit=1000, call_limit=2, input_limit=500)
    messages = [HumanMessage(content="a" * 100)]
    value.reserve(messages, 100)
    value.reserve(messages, 100)
    with pytest.raises(budget.BudgetExceeded):
        value.reserve(messages, 100)
    assert value.snapshot()["api_calls"] == 2
    assert value.snapshot()["reserved_tokens"] <= 1000
    assert value.exhausted


def test_oversized_full_source_prompt_cannot_send_even_its_first_request(monkeypatch):
    from app.modules.evidence_validation import service

    client = Mock()
    monkeypatch.setattr(service, "create_chat_client", lambda *a, **k: client)
    monkeypatch.setattr(service, "resolve_generation_target", lambda _: ("test", "model", {}))
    with budget.scope({"max_input_tokens": 1000}):
        with pytest.raises(budget.BudgetExceeded):
            service.json_call("test/model", "schema", {"source": "x" * 10000}, service.Plan)
    client.invoke.assert_not_called()


async def test_budget_is_shared_by_async_worker_threads():
    with budget.scope({"max_api_calls": 1}) as value:
        assert await asyncio.to_thread(budget.active) is value
        await asyncio.to_thread(budget.reserve, [HumanMessage(content="small")], 20)
        with pytest.raises(budget.BudgetExceeded):
            await asyncio.to_thread(budget.reserve, [HumanMessage(content="small")], 20)
    assert budget.active() is None


def test_cost_defaults_are_flash_and_opt_in_scoring():
    settings = EvaluationConfig()
    assert settings.judge_model.endswith("flash") and not settings.judge_enabled
    assert settings.max_cases == 20 and settings.max_api_calls == 40
    assert not settings.allow_full_source_audit


def test_small_batch_keeps_category_and_split_coverage():
    cases = [
        {"id": f"{c}{s}{i}", "category": c, "split": s}
        for c in ("positive", "negative")
        for s in ("calibration", "validation")
        for i in range(10)
    ]
    selected = balanced(cases, 8)
    assert len(selected) == 8 and len({c["id"] for c in selected}) == 8
    assert {(c["category"], c["split"]) for c in selected} == {
        (c, s) for c in ("positive", "negative") for s in ("calibration", "validation")
    }


def test_full_source_audit_requires_explicit_opt_in_before_any_llm(monkeypatch):
    from app.modules.evaluation import service

    monkeypatch.setattr(service, "get_provider_api_key", Mock(side_effect=AssertionError()))
    with pytest.raises(ValueError, match="disabled"):
        service.start_run(EvaluationConfig(kind="audit"), "actor")
