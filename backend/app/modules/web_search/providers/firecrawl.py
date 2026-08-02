from __future__ import annotations

from typing import Any

from app.modules.settings.service import get_web_search_provider_api_key
from app.modules.web_search.contracts import WebSearchProviderError, WebSearchResult


def _result_from_item(item: Any) -> WebSearchResult:
    metadata: dict = getattr(item, "metadata_dict", None) or {}
    url = metadata.get("source_url") or getattr(item, "url", None) or metadata.get("url") or ""
    title = metadata.get("title") or getattr(item, "title", None) or url
    content = (
        getattr(item, "markdown", None)
        or metadata.get("description")
        or getattr(item, "description", None)
        or ""
    )
    return WebSearchResult(
        url=url,
        title=title,
        content=content,
        published_at=metadata.get("published_time"),
        metadata=metadata,
    )


class FirecrawlSearchProvider:
    """Firecrawl adapter for web search and main-content Markdown scraping."""

    name = "firecrawl"

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = (
            api_key if api_key is not None else get_web_search_provider_api_key("firecrawl")
        )

    def _client(self):
        if not self._api_key:
            raise WebSearchProviderError(
                "No Firecrawl API key is configured. Set it via Manage > Settings "
                "or the FIRECRAWL_API_KEY environment variable."
            )
        try:
            from firecrawl import AsyncFirecrawl  # type: ignore[import-not-found]
        except ImportError as exc:
            raise WebSearchProviderError(
                "Firecrawl SDK is not installed. Install the 'crawlers' extra."
            ) from exc
        return AsyncFirecrawl(api_key=self._api_key)

    async def search(self, query: str, *, limit: int = 5) -> list[WebSearchResult]:
        try:
            response = await self._client().search(
                query,
                limit=limit,
                scrape_options={"formats": ["markdown"], "only_main_content": True},
            )
        except WebSearchProviderError:
            raise
        except Exception as exc:  # noqa: BLE001 - provider boundary
            raise WebSearchProviderError(f"Firecrawl search failed: {exc}") from exc
        return [_result_from_item(item) for item in (response.web or [])]

    async def fetch_page(self, url: str) -> WebSearchResult:
        try:
            document = await self._client().scrape(
                url,
                formats=["markdown"],
                only_main_content=True,
            )
        except WebSearchProviderError:
            raise
        except Exception as exc:  # noqa: BLE001 - provider boundary
            raise WebSearchProviderError(f"Firecrawl scrape failed for {url}: {exc}") from exc
        return _result_from_item(document)
