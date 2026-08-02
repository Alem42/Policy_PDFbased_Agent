"""Stable Server-Sent Event encoding and reasoning-trace mapping."""

import json
from typing import Any


def encode_sse(payload: dict) -> str:
    """Encode one JSON payload using the frontend's existing SSE contract."""

    return f"data: {json.dumps(payload, default=str)}\n\n"


def tool_result_event(message: Any) -> dict:
    """Map a LangChain ToolMessage to the compact public trace event."""

    result: dict = {}
    try:
        parsed = json.loads(message.content)
        if isinstance(parsed, dict):
            result = parsed
    except (TypeError, ValueError):
        pass

    results = result.get("results")
    result_count = len(results) if isinstance(results, list) else None
    source_titles: list[str] = []
    if isinstance(results, list):
        for item in results:
            title = item.get("title") if isinstance(item, dict) else None
            if title and title not in source_titles:
                source_titles.append(str(title))
            if len(source_titles) == 5:
                break
    return {
        "type": "tool_result",
        "tool": getattr(message, "name", None),
        "evidence_sufficient": result.get("evidence_sufficient"),
        "evidence_reason": result.get("reason") or result.get("error"),
        "result_count": result_count,
        "source_titles": source_titles,
        "answer_plan": result.get("answer_plan"),
        "citation_numbers": result.get("citation_numbers"),
        "filter_applied": result.get("filter_applied", False),
        "filter_fallback": result.get("filter_fallback", False),
        "filter_notice": result.get("filter_notice"),
    }


def step_from_tool_call(call: dict) -> dict:
    """Map a tool-call event to the persisted/frontend reasoning-step shape."""

    return {
        "tool": call.get("tool"),
        "status": "running",
        "query": call.get("query"),
        "decisionReason": call.get("decision_reason"),
        "question": call.get("question"),
        "url": call.get("url"),
        "title": call.get("title"),
        "tokensUsed": call.get("tokens_used"),
    }


def apply_tool_result(steps: list[dict], result_event: dict) -> None:
    """Complete the latest matching running step in place."""

    for step in reversed(steps):
        if step.get("tool") == result_event.get("tool") and step.get("status") == "running":
            step["status"] = "done"
            step["evidenceSufficient"] = result_event.get("evidence_sufficient")
            step["evidenceReason"] = result_event.get("evidence_reason")
            step["resultCount"] = result_event.get("result_count")
            step["sourceTitles"] = result_event.get("source_titles") or []
            step["answerPlan"] = result_event.get("answer_plan")
            step["citationNumbers"] = result_event.get("citation_numbers") or []
            step["filterApplied"] = result_event.get("filter_applied", False)
            step["filterFallback"] = result_event.get("filter_fallback", False)
            step["filterNotice"] = result_event.get("filter_notice")
            break
