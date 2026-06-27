from app.core.config import get_settings
from app.crawlers.base import BaseCrawler, CrawledDocument, CrawlResult
from app.schemas.source import SourceRead


class FirecrawlCrawler(BaseCrawler):
    name = "firecrawl"

    async def crawl(self, source: SourceRead) -> CrawlResult:
        settings = get_settings()
        if not settings.firecrawl_api_key:
            raise RuntimeError("FIRECRAWL_API_KEY is not configured")
        try:
            from firecrawl import AsyncFirecrawl  # type: ignore[import-not-found]
        except ImportError as exc:
            raise RuntimeError(
                "Firecrawl SDK is not installed. Install the 'crawlers' extra."
            ) from exc

        client = AsyncFirecrawl(api_key=settings.firecrawl_api_key)
        response = await client.crawl(
            url=str(source.start_url),
            limit=source.max_pages or settings.default_max_pages,
            include_paths=source.include_patterns or None,
            exclude_paths=source.exclude_patterns or None,
            max_discovery_depth=source.max_depth,
            scrape_options={"formats": ["markdown"], "only_main_content": True},
        )
        documents = [
            CrawledDocument(
                url=str(document.metadata.get("sourceURL", source.start_url)),
                title=document.metadata.get("title"),
                markdown=document.markdown,
                metadata=dict(document.metadata or {}),
            )
            for document in response.data
        ]
        return CrawlResult(crawler=self.name, documents=documents)
