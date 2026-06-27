import asyncio
import re
from collections import deque
from collections.abc import AsyncIterator
from urllib.parse import urljoin, urlparse, urlunparse

import httpx
from bs4 import BeautifulSoup, Tag

from app.core.config import get_settings
from app.modules.crawling.cleaning.html import HtmlCleaner
from app.modules.crawling.crawlers.base import BaseCrawler, CrawledDocument, CrawlResult
from app.modules.crawling.crawlers.pagination import pagination_strategy
from app.modules.crawling.extraction.fields import field_extractor
from app.modules.crawling.schemas.source import CrawlSourceRead
from app.modules.crawling.security.urls import is_url_allowed, validate_public_url


class HttpCrawler(BaseCrawler):
    """Two-phase crawler: discover detail URLs, then fetch detail documents."""

    name = "http"

    def __init__(self) -> None:
        self.cleaner = HtmlCleaner()

    async def crawl(self, crawl_source: CrawlSourceRead) -> CrawlResult:
        documents: list[CrawledDocument] = []
        final_result: CrawlResult | None = None
        async for batch in self.crawl_batches(crawl_source):
            documents.extend(batch.documents)
            final_result = batch

        if final_result is None:
            return CrawlResult(crawler=self.name)

        return CrawlResult(
            crawler=self.name,
            documents=documents,
            errors=final_result.errors,
            pages_visited=final_result.pages_visited,
            detail_urls_discovered=final_result.detail_urls_discovered,
            expected_documents=final_result.expected_documents,
            discovery_exhausted=final_result.discovery_exhausted,
        )

    async def crawl_batches(
        self,
        crawl_source: CrawlSourceRead,
    ) -> AsyncIterator[CrawlResult]:
        settings = get_settings()
        page_limit = crawl_source.max_pages or settings.default_max_pages
        document_limit = crawl_source.max_documents or page_limit
        batch_size = int(crawl_source.config.get("sync_batch_size", 5))
        batch_size = max(batch_size, 1)
        errors: list[str] = []
        pages_visited = 0

        async with httpx.AsyncClient(
            timeout=settings.default_request_timeout_seconds,
            follow_redirects=True,
            headers={"User-Agent": settings.user_agent},
        ) as client:
            (
                detail_urls,
                discovery_pages,
                discovery_errors,
                expected_documents,
                discovery_exhausted,
            ) = await self._discover(
                client,
                crawl_source,
                page_limit=page_limit,
                document_limit=document_limit,
            )
            pages_visited += discovery_pages
            errors.extend(discovery_errors)

            batch: list[CrawledDocument] = []
            emitted = False
            for url in detail_urls[:document_limit]:
                if pages_visited >= page_limit:
                    break
                try:
                    response = await self._get_html(client, url)
                    pages_visited += 1
                    batch.append(self._parse_document(response, crawl_source))
                except Exception as exc:
                    pages_visited += 1
                    errors.append(f"{url}: {exc}")
                if len(batch) >= batch_size:
                    yield CrawlResult(
                        crawler=self.name,
                        documents=batch,
                        errors=list(errors),
                        pages_visited=pages_visited,
                        detail_urls_discovered=len(detail_urls),
                        expected_documents=expected_documents,
                        discovery_exhausted=discovery_exhausted,
                    )
                    emitted = True
                    batch = []
                await asyncio.sleep(0)

            if batch or not emitted:
                yield CrawlResult(
                    crawler=self.name,
                    documents=batch,
                    errors=list(errors),
                    pages_visited=pages_visited,
                    detail_urls_discovered=len(detail_urls),
                    expected_documents=expected_documents,
                    discovery_exhausted=discovery_exhausted,
                )

    async def _discover(
        self,
        client: httpx.AsyncClient,
        crawl_source: CrawlSourceRead,
        *,
        page_limit: int,
        document_limit: int,
    ) -> tuple[list[str], int, list[str], int | None, bool]:
        queue: deque[tuple[str, int]] = deque([(str(crawl_source.start_url), 0)])
        visited: set[str] = set()
        detail_urls: list[str] = []
        detail_seen: set[str] = set()
        errors: list[str] = []
        pages_visited = 0
        expected_documents: int | None = None

        while queue and pages_visited < page_limit and len(detail_urls) < document_limit:
            url, depth = queue.popleft()
            url = self._canonicalize(url)
            if url in visited:
                continue
            visited.add(url)

            try:
                response = await self._get_html(client, url)
                pages_visited += 1
                soup = BeautifulSoup(response.text, "html.parser")
                for target in self._detail_links(soup, str(response.url), crawl_source):
                    if target not in detail_seen:
                        detail_seen.add(target)
                        detail_urls.append(target)
                        if len(detail_urls) >= document_limit:
                            break
                pagination_page = pagination_strategy.next_pages(
                    soup,
                    current_url=str(response.url),
                    config=crawl_source.config.get("pagination"),
                )
                if pagination_page is not None and pagination_page.expected_documents is not None:
                    expected_documents = pagination_page.expected_documents
                pagination_links = (
                    pagination_page.urls
                    if pagination_page is not None
                    else self._pagination_links(
                        soup,
                        str(response.url),
                        crawl_source,
                    )
                )
                next_depth = depth if pagination_links else depth + 1
                if depth < crawl_source.max_depth or pagination_links:
                    for target in pagination_links:
                        if not is_url_allowed(target, crawl_source):
                            continue
                        if target not in visited:
                            queue.append((target, next_depth))
            except Exception as exc:
                pages_visited += 1
                errors.append(f"{url}: {exc}")
            await asyncio.sleep(0)

        discovery_exhausted = not queue and len(detail_urls) < document_limit
        return (
            detail_urls,
            pages_visited,
            errors,
            expected_documents,
            discovery_exhausted,
        )

    async def _get_html(
        self,
        client: httpx.AsyncClient,
        url: str,
    ) -> httpx.Response:
        await validate_public_url(url)
        response = await client.get(url)
        response.raise_for_status()
        content_type = response.headers.get("content-type", "")
        if "text/html" not in content_type:
            raise ValueError(
                f"Response is not HTML: content-type={content_type or '<missing>'}, "
                f"bytes={len(response.content)}"
            )
        return response

    def _detail_links(
        self,
        soup: BeautifulSoup,
        base_url: str,
        crawl_source: CrawlSourceRead,
    ) -> list[str]:
        selector = str(crawl_source.config.get("detail_link_selector", "a[href]"))
        patterns = crawl_source.config.get("detail_url_patterns", [])
        start_path = urlparse(str(crawl_source.start_url)).path.rstrip("/")
        links: list[str] = []

        for anchor in soup.select(selector):
            target = self._anchor_target(anchor, base_url)
            if not target or not is_url_allowed(target, crawl_source):
                continue
            path = urlparse(target).path.rstrip("/")
            if patterns:
                if not any(re.search(pattern, target) for pattern in patterns):
                    continue
            elif not path.startswith(f"{start_path}/"):
                continue
            links.append(target)
        return self._unique(links)

    def _pagination_links(
        self,
        soup: BeautifulSoup,
        base_url: str,
        crawl_source: CrawlSourceRead,
    ) -> list[str]:
        selector = crawl_source.config.get("pagination_link_selector")
        patterns = crawl_source.config.get("pagination_url_patterns", [])
        if selector:
            anchors = soup.select(str(selector))
        else:
            anchors = soup.select('a[href][rel~="next"], a[href]')

        start_path = urlparse(str(crawl_source.start_url)).path.rstrip("/")
        links: list[str] = []
        for anchor in anchors:
            target = self._anchor_target(anchor, base_url)
            if not target or not is_url_allowed(target, crawl_source):
                continue
            parsed = urlparse(target)
            if patterns:
                if not any(re.search(pattern, target) for pattern in patterns):
                    continue
            elif not (
                parsed.path.rstrip("/") == start_path
                and parsed.query
                and re.search(r"(?:^|&)(?:page|p|offset)=\d+", parsed.query)
            ):
                continue
            links.append(target)
        return self._unique(links)

    def _parse_document(
        self,
        response: httpx.Response,
        crawl_source: CrawlSourceRead,
    ) -> CrawledDocument:
        soup = BeautifulSoup(response.text, "html.parser")
        extracted = field_extractor.extract(
            soup,
            page_url=str(response.url),
            config=crawl_source.config.get("field_extraction"),
        )
        cleaned = self.cleaner.clean(
            response.text,
            page_url=str(response.url),
            content_selector=crawl_source.config.get("content_selector"),
            exclude_selectors=crawl_source.config.get("exclude_selectors"),
            asset_link_selector=str(crawl_source.config.get("asset_link_selector", "a[href]")),
        )
        return CrawledDocument(
            url=str(response.url),
            title=extracted.structured.get("title", cleaned.title),
            markdown=cleaned.markdown,
            metadata={
                "status_code": response.status_code,
                "assets": cleaned.assets,
                "structured": extracted.structured,
                "extracted": extracted.metadata,
            },
        )

    @staticmethod
    def _anchor_target(anchor: Tag, base_url: str) -> str | None:
        href = anchor.get("href")
        if not isinstance(href, str):
            return None
        return HttpCrawler._canonicalize(urljoin(base_url, href))

    @staticmethod
    def _canonicalize(url: str) -> str:
        parsed = urlparse(url)
        return urlunparse(parsed._replace(fragment=""))

    @staticmethod
    def _unique(values: list[str]) -> list[str]:
        return list(dict.fromkeys(values))
