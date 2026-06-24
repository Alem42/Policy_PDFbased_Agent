from urllib.parse import urlparse

from app.core.config import get_settings
from app.crawlers.adapters.oecd_ai import OecdAiCrawler
from app.crawlers.base import BaseCrawler
from app.crawlers.firecrawl import FirecrawlCrawler
from app.crawlers.http import HttpCrawler
from app.crawlers.playwright import PlaywrightCrawler
from app.schemas.source import CrawlerPreference, SourceRead


class CrawlerSelector:
    """Choose the cheapest suitable crawler.

    Auto starts with plain HTTP. The crawl service may fall back to Playwright
    and then Firecrawl when an adapter returns no usable documents or fails.
    """

    def primary(self, source: SourceRead) -> BaseCrawler:
        if (
            source.crawler_preference
            in {CrawlerPreference.AUTO, CrawlerPreference.HTTP}
            and source.config.get("adapter", "auto") != "none"
            and self._is_oecd_ai_policy_source(source)
        ):
            return OecdAiCrawler()
        mapping: dict[CrawlerPreference, type[BaseCrawler]] = {
            CrawlerPreference.HTTP: HttpCrawler,
            CrawlerPreference.PLAYWRIGHT: PlaywrightCrawler,
            CrawlerPreference.FIRECRAWL: FirecrawlCrawler,
        }
        crawler_type = mapping.get(source.crawler_preference, HttpCrawler)
        return crawler_type()

    def fallbacks(self, source: SourceRead) -> list[BaseCrawler]:
        if source.crawler_preference != CrawlerPreference.AUTO:
            return []
        fallbacks: list[BaseCrawler] = [PlaywrightCrawler()]
        if get_settings().firecrawl_api_key:
            fallbacks.append(FirecrawlCrawler())
        return fallbacks

    @staticmethod
    def _is_oecd_ai_policy_source(source: SourceRead) -> bool:
        parsed = urlparse(str(source.start_url))
        return (
            parsed.hostname == "oecd.ai"
            and parsed.path.rstrip("/") == "/en/dashboards/policy-initiatives"
        )


crawler_selector = CrawlerSelector()
