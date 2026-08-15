"""Policy-search capability independent of HTTP, LangGraph, and MCP."""

from __future__ import annotations

from typing import Protocol

from app.modules.chat.capabilities.contracts import PolicySearchRequest
from app.modules.retrieval.contracts import RetrievalRequest, RetrievalResult
from app.modules.retrieval.service import retrieval_service


class RetrievalPort(Protocol):
    """The retrieval behavior required by the application capability."""

    def retrieve(self, request: RetrievalRequest) -> RetrievalResult: ...


class PolicySearchCapability:
    """Search policy evidence without transport or orchestration concerns."""

    def __init__(self, retriever: RetrievalPort) -> None:
        self._retriever = retriever

    def search(self, request: PolicySearchRequest) -> RetrievalResult:
        return self._retriever.retrieve(request.as_retrieval_request())


policy_search_capability = PolicySearchCapability(retrieval_service)
