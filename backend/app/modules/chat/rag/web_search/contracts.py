from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass
class WebSearchResult:
    """One web page, either a search hit or a fully fetched page.

    ``content`` is markdown/plain text: a short excerpt for search() results
    (providers return partial content up front), the full page body for
    fetch_page() results.
    """

    url: str
    title: str
    content: str
    published_at: str | None = None
    metadata: dict = field(default_factory=dict)


@runtime_checkable
class WebSearchProvider(Protocol):
    """Abstraction over a web search backend (Firecrawl, Tavily, ...).

    Callers must go through `registry.get_active_web_search_provider()` rather
    than importing a concrete provider class directly, so the active backend
    stays a pure settings.web_search_provider switch.
    """

    name: str

    async def search(self, query: str, *, limit: int = 5) -> list[WebSearchResult]:
        """Search the web and return short result summaries."""
        ...

    async def fetch_page(self, url: str) -> WebSearchResult:
        """Fetch one URL's full page content, for import into the knowledge base."""
        ...


class WebSearchProviderError(RuntimeError):
    """Raised when a provider is misconfigured or a request fails."""
