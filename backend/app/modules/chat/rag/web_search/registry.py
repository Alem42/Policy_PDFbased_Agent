from __future__ import annotations

from app.modules.chat.rag.web_search.contracts import WebSearchProvider, WebSearchProviderError
from app.modules.settings.service import get_web_search_provider


def get_active_web_search_provider() -> WebSearchProvider:
    """Return the WebSearchProvider selected by settings.web_search_provider.

    Concrete provider classes are imported lazily so picking one backend
    never requires the other backend's SDK to be installed.
    """
    provider_id = get_web_search_provider()
    if provider_id == "firecrawl":
        from app.modules.chat.rag.web_search.providers.firecrawl import FirecrawlSearchProvider

        return FirecrawlSearchProvider()
    if provider_id == "tavily":
        from app.modules.chat.rag.web_search.providers.tavily import TavilySearchProvider

        return TavilySearchProvider()
    raise WebSearchProviderError(f"Unknown web search provider: {provider_id!r}")
