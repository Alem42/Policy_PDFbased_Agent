"""Launch the Policy MCP server over stdio and print negotiated capabilities."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

BACKEND_ROOT = Path(__file__).resolve().parents[1]


async def check_server() -> dict:
    parameters = StdioServerParameters(
        command=sys.executable,
        args=["-m", "app.mcp_server.server"],
        cwd=BACKEND_ROOT,
        env={
            "POLICY_MCP_SOURCE_POLICY": "selected_only",
            "POLICY_MCP_MAX_CALLS": "3",
            "POLICY_MCP_MAX_TOP_K": "8",
        },
    )
    async with stdio_client(parameters) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            initialized = await session.initialize()
            tools = await session.list_tools()
            status = await session.call_tool("get_policy_search_status")
            return {
                "server": initialized.serverInfo.name,
                "protocol_version": initialized.protocolVersion,
                "tools": [tool.name for tool in tools.tools],
                "status": status.structuredContent,
            }


def main() -> None:
    print(json.dumps(asyncio.run(check_server()), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
