from __future__ import annotations

from app.modules.chat.rag.web_search.contracts import WebSearchProviderError, WebSearchResult
from app.modules.settings.service import get_web_search_provider_api_key


class TavilySearchProvider:
    """WebSearchProvider skeleton for Tavily.

    Structurally complete (satisfies the WebSearchProvider Protocol) but not
    wired up: Firecrawl is the active provider for now. Implement `search`/
    `fetch_page` against `tavily-python` (add it as a dependency first) when
    Tavily needs to become selectable via settings.web_search_provider.
    """

    name = "tavily"

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = (
            api_key if api_key is not None else get_web_search_provider_api_key("tavily")
        )

    async def search(self, query: str, *, limit: int = 5) -> list[WebSearchResult]:
        raise WebSearchProviderError("The Tavily web search provider is not implemented yet.")

    async def fetch_page(self, url: str) -> WebSearchResult:
        raise WebSearchProviderError("The Tavily web search provider is not implemented yet.")
