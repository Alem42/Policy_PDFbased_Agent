# Policy PDF Agent MCP Server

The first MCP adapter exposes the existing framework-independent `PolicySearchCapability`; it does not call a LangGraph Tool or duplicate retrieval logic.

## Tools

- `get_policy_search_status`: shows the active non-secret permission and budget policy.
- `search_policy_documents`: searches selected PDFs or, when explicitly enabled, the shared library and returns grounded citation excerpts.

Restricted documents are always disabled in this first server. The server does not expose document mutation or web import tools, so no destructive confirmation flow is required yet.

## Run over stdio

From `backend/`:

```powershell
python -m app.mcp_server.server
```

Normally an MCP host starts that process and uses stdin/stdout for JSON-RPC. To see a real client handshake, tool discovery and tool call without configuring a host:

```powershell
python scripts/check_policy_mcp.py
```

## Permission and budget environment

```text
POLICY_MCP_SOURCE_POLICY=selected_only | library_allowed
POLICY_MCP_MAX_CALLS=10
POLICY_MCP_MAX_TOP_K=12
```

The safe default is `selected_only`. A model cannot request library scope unless the process owner explicitly starts the server with `library_allowed`. Search calls consume a process-local budget; status calls do not.

## Example host configuration

Replace the working directory and Python executable with values for the deployment environment:

```json
{
  "mcpServers": {
    "policy-pdf-agent": {
      "command": "python",
      "args": ["-m", "app.mcp_server.server"],
      "cwd": "C:/path/to/repository/backend",
      "env": {
        "POLICY_MCP_SOURCE_POLICY": "selected_only",
        "POLICY_MCP_MAX_CALLS": "10",
        "POLICY_MCP_MAX_TOP_K": "12"
      }
    }
  }
}
```

Database configuration still comes from the backend environment. Do not place database passwords or provider API keys in model-visible tool arguments.
