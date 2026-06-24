import asyncio
import sys

from bs4 import BeautifulSoup

from app.cleaning.html import HtmlCleaner
from app.crawlers.base import BaseCrawler, CrawledDocument, CrawlResult
from app.extraction.fields import field_extractor
from app.schemas.source import SourceRead


class PlaywrightCrawler(BaseCrawler):
    name = "playwright"

    def __init__(self) -> None:
        self.cleaner = HtmlCleaner()

    async def crawl(self, source: SourceRead) -> CrawlResult:
        self._ensure_subprocess_event_loop()
        try:
            from playwright.async_api import async_playwright  # type: ignore[import-not-found]
        except ImportError as exc:
            raise RuntimeError(
                "Playwright is not installed. Install the 'crawlers' extra and Chromium."
            ) from exc

        # This adapter deliberately captures one rendered page first. Link discovery
        # can be extended per source once its JavaScript navigation is understood.
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.goto(str(source.start_url), wait_until="networkidle")
            html = await page.content()
            title = await page.title()
            final_url = page.url
            await browser.close()

        extracted = field_extractor.extract(
            BeautifulSoup(html, "html.parser"),
            page_url=final_url,
            config=source.config.get("field_extraction"),
        )
        cleaned = self.cleaner.clean(
            html,
            page_url=final_url,
            content_selector=source.config.get("content_selector"),
            exclude_selectors=source.config.get("exclude_selectors"),
            asset_link_selector=str(
                source.config.get("asset_link_selector", "a[href]")
            ),
        )
        return CrawlResult(
            crawler=self.name,
            documents=[
                CrawledDocument(
                    url=final_url,
                    title=extracted.structured.get(
                        "title",
                        cleaned.title or title,
                    ),
                    markdown=cleaned.markdown,
                    metadata={
                        "assets": cleaned.assets,
                        "structured": extracted.structured,
                        "extracted": extracted.metadata,
                    },
                )
            ],
            pages_visited=1,
            detail_urls_discovered=1,
        )

    @staticmethod
    def _ensure_subprocess_event_loop() -> None:
        if sys.platform != "win32":
            return
        loop = asyncio.get_running_loop()
        if loop.__class__.__name__ == "_WindowsSelectorEventLoop":
            raise RuntimeError(
                "Playwright requires a Windows Proactor event loop to launch Chromium. "
                "Run uvicorn without --reload, or use crawler_preference='http' for this source."
            )
