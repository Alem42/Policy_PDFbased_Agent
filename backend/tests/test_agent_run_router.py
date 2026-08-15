from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.modules.chat.runtime import router as run_router


async def test_list_agent_runs_uses_bounded_limit(monkeypatch) -> None:
    captured = []

    def list_runs(limit):
        captured.append(limit)
        return [{"run_id": "run-1"}]

    monkeypatch.setattr(run_router.agent_run_repository, "list_runs", list_runs)

    result = await run_router.list_agent_runs({"role": "admin"}, limit=25)

    assert result == [{"run_id": "run-1"}]
    assert captured == [25]


async def test_get_agent_run_returns_ordered_trace(monkeypatch) -> None:
    expected = {
        "run": {"run_id": "run-1"},
        "events": [{"sequence": 1, "event_type": "run_started"}],
    }
    monkeypatch.setattr(
        run_router.agent_run_repository,
        "get_run",
        lambda run_id: expected if run_id == "run-1" else None,
    )

    assert await run_router.get_agent_run("run-1", {"role": "admin"}) == expected


async def test_get_agent_run_returns_404_for_unknown_run(monkeypatch) -> None:
    monkeypatch.setattr(run_router.agent_run_repository, "get_run", lambda run_id: None)

    with pytest.raises(HTTPException) as exc_info:
        await run_router.get_agent_run("missing", {"role": "admin"})

    assert exc_info.value.status_code == 404
