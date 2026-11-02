from app.modules.settings.service import get_web_search_provider
from app.modules.web_search.contracts import WebSearchProvider, WebSearchProviderError


def get_active_web_search_provider() -> WebSearchProvider:
    """Construct the provider selected in runtime settings."""

    provider_id = get_web_search_provider()
    if provider_id == "firecrawl":
        from app.modules.web_search.providers.firecrawl import FirecrawlSearchProvider

        return FirecrawlSearchProvider()
    if provider_id == "tavily":
        from app.modules.web_search.providers.tavily import TavilySearchProvider

        return TavilySearchProvider()
    if provider_id == "deepseek":
        from app.modules.web_search.providers.deepseek import DeepSeekSearchProvider

        return DeepSeekSearchProvider()
    raise WebSearchProviderError(f"Unknown web search provider: {provider_id!r}")
