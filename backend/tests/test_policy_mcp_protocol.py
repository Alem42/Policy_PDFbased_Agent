from __future__ import annotations

import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

BACKEND_ROOT = Path(__file__).resolve().parents[1]


async def test_real_stdio_client_negotiates_and_calls_status_tool() -> None:
    parameters = StdioServerParameters(
        command=sys.executable,
        args=["-m", "app.mcp_server.server"],
        cwd=BACKEND_ROOT,
        env={
            "POLICY_MCP_SOURCE_POLICY": "selected_only",
            "POLICY_MCP_MAX_CALLS": "2",
            "POLICY_MCP_MAX_TOP_K": "7",
        },
    )

    async with stdio_client(parameters) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            initialized = await session.initialize()
            tools = await session.list_tools()
            status = await session.call_tool("get_policy_search_status")

    assert initialized.serverInfo.name == "Policy PDF Agent"
    assert {tool.name for tool in tools.tools} == {
        "get_policy_search_status",
        "search_policy_documents",
    }
    assert status.isError is False
    assert status.structuredContent == {
        "server": "Policy PDF Agent",
        "source_policy": "selected_only",
        "library_search_allowed": False,
        "max_calls": 2,
        "calls_remaining": 2,
        "max_top_k": 7,
        "restricted_documents_allowed": False,
    }
