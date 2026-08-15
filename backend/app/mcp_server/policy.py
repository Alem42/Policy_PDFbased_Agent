"""Policy-search MCP server with explicit source and call-budget boundaries."""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass, field
from typing import Any, Literal

from mcp.server.fastmcp import FastMCP

from app.modules.chat.capabilities import PolicySearchCapability, PolicySearchRequest
from app.modules.chat.capabilities.policy_search import policy_search_capability
from app.modules.retrieval.contracts import MetadataFilters, RetrievalResult

MCPSourcePolicy = Literal["selected_only", "library_allowed"]
SearchScope = Literal["selected", "library"]


@dataclass(frozen=True)
class MCPAccessPolicy:
    """Process-level permission and resource budget for an MCP client."""

    source_policy: MCPSourcePolicy = "selected_only"
    max_calls: int = 10
    max_top_k: int = 12

    def __post_init__(self) -> None:
        if self.source_policy not in {"selected_only", "library_allowed"}:
            raise ValueError(f"Unsupported MCP source policy: {self.source_policy!r}")
        if not 1 <= self.max_calls <= 1000:
            raise ValueError("MCP max_calls must be between 1 and 1000.")
        if not 1 <= self.max_top_k <= 50:
            raise ValueError("MCP max_top_k must be between 1 and 50.")

    @classmethod
    def from_environment(cls) -> MCPAccessPolicy:
        return cls(
            source_policy=os.getenv("POLICY_MCP_SOURCE_POLICY", "selected_only"),
            max_calls=_integer_environment("POLICY_MCP_MAX_CALLS", 10),
            max_top_k=_integer_environment("POLICY_MCP_MAX_TOP_K", 12),
        )


@dataclass
class MCPPolicySearchRuntime:
    capability: PolicySearchCapability
    policy: MCPAccessPolicy
    _calls_used: int = 0
    _budget_lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    @property
    def calls_remaining(self) -> int:
        return max(self.policy.max_calls - self._calls_used, 0)

    async def search(
        self,
        *,
        query: str,
        identifiers: list[str],
        scope: SearchScope,
        top_k: int,
        policy_areas: list[str],
        country_regions: list[str],
        source_organisations: list[str],
        languages: list[str],
        tags: list[str],
        year_from: int | None,
        year_to: int | None,
        freshness_requested: bool,
    ) -> dict[str, Any]:
        normalized_query = query.strip()
        if not normalized_query:
            raise ValueError("query must not be empty.")
        if scope == "selected" and not identifiers:
            raise ValueError("selected scope requires at least one document identifier.")
        if scope == "library" and self.policy.source_policy != "library_allowed":
            raise PermissionError(
                "Library search is disabled. Start the server with "
                "POLICY_MCP_SOURCE_POLICY=library_allowed to enable it."
            )
        if not 1 <= top_k <= self.policy.max_top_k:
            raise ValueError(f"top_k must be between 1 and {self.policy.max_top_k}.")

        async with self._budget_lock:
            if self._calls_used >= self.policy.max_calls:
                raise RuntimeError("MCP policy-search call budget exhausted.")
            self._calls_used += 1

        result = await asyncio.to_thread(
            self.capability.search,
            PolicySearchRequest(
                query=normalized_query,
                scope=scope,
                identifiers=tuple(identifiers),
                top_k=top_k,
                include_restricted=False,
                metadata_filters=MetadataFilters(
                    policy_areas=tuple(policy_areas),
                    country_regions=tuple(country_regions),
                    source_organisations=tuple(source_organisations),
                    languages=tuple(languages),
                    tags=tuple(tags),
                    year_from=year_from,
                    year_to=year_to,
                    freshness_requested=freshness_requested,
                ),
            ),
        )
        return _public_result(result, scope, self.calls_remaining)


def build_policy_mcp_server(
    capability: PolicySearchCapability = policy_search_capability,
    policy: MCPAccessPolicy | None = None,
) -> FastMCP:
    access_policy = policy or MCPAccessPolicy.from_environment()
    runtime = MCPPolicySearchRuntime(capability, access_policy)
    server = FastMCP(
        name="Policy PDF Agent",
        instructions=(
            "Search grounded policy-document evidence. The server never exposes restricted "
            "documents and enforces its configured source boundary and process call budget."
        ),
    )

    @server.tool(structured_output=True)
    async def get_policy_search_status() -> dict[str, Any]:
        """Return the active non-secret MCP permission and budget configuration."""

        return {
            "server": "Policy PDF Agent",
            "source_policy": access_policy.source_policy,
            "library_search_allowed": access_policy.source_policy == "library_allowed",
            "max_calls": access_policy.max_calls,
            "calls_remaining": runtime.calls_remaining,
            "max_top_k": access_policy.max_top_k,
            "restricted_documents_allowed": False,
        }

    @server.tool(structured_output=True)
    async def search_policy_documents(
        query: str,
        identifiers: list[str] | None = None,
        scope: SearchScope = "selected",
        top_k: int = 6,
        policy_areas: list[str] | None = None,
        country_regions: list[str] | None = None,
        source_organisations: list[str] | None = None,
        languages: list[str] | None = None,
        tags: list[str] | None = None,
        year_from: int | None = None,
        year_to: int | None = None,
        freshness_requested: bool = False,
    ) -> dict[str, Any]:
        """Search selected policy PDFs or, when permitted, the shared document library.

        Returns grounded citation excerpts and deterministic evidence sufficiency. Restricted
        documents are never included. Use selected scope unless the server status explicitly
        reports that library search is allowed.
        """

        return await runtime.search(
            query=query,
            identifiers=identifiers or [],
            scope=scope,
            top_k=top_k,
            policy_areas=policy_areas or [],
            country_regions=country_regions or [],
            source_organisations=source_organisations or [],
            languages=languages or [],
            tags=tags or [],
            year_from=year_from,
            year_to=year_to,
            freshness_requested=freshness_requested,
        )

    return server


def _public_result(
    result: RetrievalResult,
    scope: SearchScope,
    calls_remaining: int,
) -> dict[str, Any]:
    return {
        "scope": scope,
        "evidence_sufficient": result.evidence.sufficient,
        "evidence_reason": result.evidence.reason,
        "citations": [_public_citation(citation) for citation in result.citations],
        "citation_count": len(result.citations),
        "filter_applied": result.filter_applied,
        "filter_fallback": result.filter_fallback,
        "filter_notice": result.filter_notice,
        "calls_remaining": calls_remaining,
    }


def _public_citation(citation: dict[str, Any]) -> dict[str, Any]:
    allowed = (
        "document_id",
        "chunk_id",
        "title",
        "page",
        "quote",
        "source_url",
    )
    return {
        key: _json_scalar(citation[key])
        for key in allowed
        if citation.get(key) is not None
    }


def _json_scalar(value: Any) -> str | int | float | bool:
    if isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _integer_environment(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer.") from exc
