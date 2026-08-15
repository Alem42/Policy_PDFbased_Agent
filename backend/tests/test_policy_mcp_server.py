from __future__ import annotations

import pytest
from mcp.server.fastmcp.exceptions import ToolError

from app.mcp_server.policy import MCPAccessPolicy, build_policy_mcp_server
from app.modules.retrieval.contracts import EvidenceDecision, RetrievalResult


class RecordingCapability:
    def __init__(self) -> None:
        self.requests = []

    def search(self, request):
        self.requests.append(request)
        return RetrievalResult(
            citations=[
                {
                    "document_id": "doc-1",
                    "title": "Responsible AI Policy",
                    "quote": "Agencies must publish a transparency statement.",
                    "private_debug": "must-not-leak",
                }
            ],
            evidence=EvidenceDecision(True, "supported"),
        )


async def test_mcp_server_lists_status_and_search_tools() -> None:
    server = build_policy_mcp_server(RecordingCapability(), MCPAccessPolicy())

    tools = await server.list_tools()

    assert {tool.name for tool in tools} == {
        "get_policy_search_status",
        "search_policy_documents",
    }


async def test_mcp_search_calls_capability_and_sanitizes_result() -> None:
    capability = RecordingCapability()
    server = build_policy_mcp_server(
        capability,
        MCPAccessPolicy(source_policy="library_allowed", max_calls=2),
    )

    _content, result = await server.call_tool(
        "search_policy_documents",
        {
            "query": "What must agencies publish?",
            "identifiers": ["doc-1"],
            "scope": "selected",
            "top_k": 5,
            "country_regions": ["Australia"],
        },
    )

    assert result["evidence_sufficient"] is True
    assert result["citation_count"] == 1
    assert result["calls_remaining"] == 1
    assert "private_debug" not in result["citations"][0]
    request = capability.requests[0]
    assert request.identifiers == ("doc-1",)
    assert request.include_restricted is False
    assert request.metadata_filters.country_regions == ("Australia",)


async def test_mcp_selected_only_policy_blocks_library_scope() -> None:
    server = build_policy_mcp_server(
        RecordingCapability(),
        MCPAccessPolicy(source_policy="selected_only"),
    )

    with pytest.raises(ToolError, match="Library search is disabled"):
        await server.call_tool(
            "search_policy_documents",
            {"query": "search everything", "scope": "library"},
        )


async def test_mcp_call_budget_is_enforced() -> None:
    server = build_policy_mcp_server(
        RecordingCapability(),
        MCPAccessPolicy(max_calls=1),
    )
    arguments = {
        "query": "policy",
        "identifiers": ["doc-1"],
        "scope": "selected",
    }

    await server.call_tool("search_policy_documents", arguments)
    with pytest.raises(ToolError, match="budget exhausted"):
        await server.call_tool("search_policy_documents", arguments)
