from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class WebSearchResult:
    """One search hit or fetched page in provider-independent form.

    ``content`` is a short excerpt for search results and the complete
    markdown/plain-text body for ``fetch_page`` results.
    """

    url: str
    title: str
    content: str
    published_at: str | None = None
    metadata: dict = field(default_factory=dict)


@runtime_checkable
class WebSearchProvider(Protocol):
    """Contract implemented by web-search backends such as Firecrawl."""

    name: str

    async def search(self, query: str, *, limit: int = 5) -> list[WebSearchResult]: ...

    async def fetch_page(self, url: str) -> WebSearchResult: ...


class WebSearchProviderError(RuntimeError):
    """A selected provider is unavailable, misconfigured, or failed."""
