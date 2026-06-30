from urllib.parse import urlparse

from app.core.config import get_settings
from app.modules.crawling.crawlers.adapters.oecd_ai import OecdAiCrawler
from app.modules.crawling.crawlers.base import BaseCrawler
from app.modules.crawling.crawlers.firecrawl import FirecrawlCrawler
from app.modules.crawling.crawlers.http import HttpCrawler
from app.modules.crawling.crawlers.playwright import PlaywrightCrawler
from app.modules.crawling.schemas.source import CrawlerPreference, CrawlSourceRead


class CrawlerSelector:
    """Choose the cheapest suitable crawler.

    Auto starts with plain HTTP. The crawl service may fall back to Playwright
    and then Firecrawl when an adapter returns no usable documents or fails.
    """

    def primary(self, crawl_source: CrawlSourceRead) -> BaseCrawler:
        if (
            crawl_source.crawler_preference in {CrawlerPreference.AUTO, CrawlerPreference.HTTP}
            and crawl_source.config.get("adapter", "auto") != "none"
            and self._is_oecd_ai_policy_source(crawl_source)
        ):
            return OecdAiCrawler()
        mapping: dict[CrawlerPreference, type[BaseCrawler]] = {
            CrawlerPreference.HTTP: HttpCrawler,
            CrawlerPreference.PLAYWRIGHT: PlaywrightCrawler,
            CrawlerPreference.FIRECRAWL: FirecrawlCrawler,
        }
        crawler_type = mapping.get(crawl_source.crawler_preference, HttpCrawler)
        return crawler_type()

    def fallbacks(self, crawl_source: CrawlSourceRead) -> list[BaseCrawler]:
        if crawl_source.crawler_preference != CrawlerPreference.AUTO:
            return []
        fallbacks: list[BaseCrawler] = []
        if crawl_source.config.get("allow_playwright_fallback", False):
            fallbacks.append(PlaywrightCrawler())
        if get_settings().firecrawl_api_key:
            fallbacks.append(FirecrawlCrawler())
        return fallbacks

    @staticmethod
    def _is_oecd_ai_policy_source(crawl_source: CrawlSourceRead) -> bool:
        parsed = urlparse(str(crawl_source.start_url))
        return (
            parsed.hostname == "oecd.ai"
            and parsed.path.rstrip("/") == "/en/dashboards/policy-initiatives"
        )


crawler_selector = CrawlerSelector()
