from app.modules.settings.service import get_web_search_provider_api_key
from app.modules.web_search.contracts import WebSearchProviderError, WebSearchResult


class TavilySearchProvider:
    """Reserved Tavily adapter; selecting it fails explicitly until implemented."""

    name = "tavily"

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = (
            api_key if api_key is not None else get_web_search_provider_api_key("tavily")
        )

    async def search(self, query: str, *, limit: int = 5) -> list[WebSearchResult]:
        raise WebSearchProviderError("The Tavily web search provider is not implemented yet.")

    async def fetch_page(self, url: str) -> WebSearchResult:
        raise WebSearchProviderError("The Tavily web search provider is not implemented yet.")
