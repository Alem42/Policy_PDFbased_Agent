from __future__ import annotations

from collections.abc import Callable

from app.modules.web_search.contracts import WebSearchProvider, WebSearchResult
from app.modules.web_search.registry import get_active_web_search_provider


class WebSearchService:
    """Small black-box facade over the configured web provider.

    The facade is intentionally stateless: settings changes take effect on the
    next call because the provider is resolved lazily. Tests can inject a
    deterministic provider factory without patching concrete SDK adapters.
    """

    def __init__(
        self,
        provider_factory: Callable[[], WebSearchProvider] = get_active_web_search_provider,
    ) -> None:
        self._provider_factory = provider_factory

    async def search(self, query: str, *, limit: int = 5) -> list[WebSearchResult]:
        return await self._provider_factory().search(query, limit=limit)

    async def fetch_page(self, url: str) -> WebSearchResult:
        return await self._provider_factory().fetch_page(url)


web_search_service = WebSearchService()
