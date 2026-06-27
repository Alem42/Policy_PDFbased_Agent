from app.core.config import get_settings
from app.modules.crawling.crawlers.base import BaseCrawler, CrawledDocument, CrawlResult
from app.modules.crawling.schemas.source import CrawlSourceRead


class FirecrawlCrawler(BaseCrawler):
    name = "firecrawl"

    async def crawl(self, crawl_source: CrawlSourceRead) -> CrawlResult:
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
            url=str(crawl_source.start_url),
            limit=crawl_source.max_pages or settings.default_max_pages,
            include_paths=crawl_source.include_patterns or None,
            exclude_paths=crawl_source.exclude_patterns or None,
            max_discovery_depth=crawl_source.max_depth,
            scrape_options={"formats": ["markdown"], "only_main_content": True},
        )
        documents = [
            CrawledDocument(
                url=str(document.metadata.get("sourceURL", crawl_source.start_url)),
                title=document.metadata.get("title"),
                markdown=document.markdown,
                metadata=dict(document.metadata or {}),
            )
            for document in response.data
        ]
        return CrawlResult(crawler=self.name, documents=documents)
