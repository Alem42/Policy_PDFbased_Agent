"""Executable stdio entrypoint for the Policy PDF Agent MCP server."""

from app.mcp_server.policy import build_policy_mcp_server


def main() -> None:
    build_policy_mcp_server().run(transport="stdio")


if __name__ == "__main__":
    main()
