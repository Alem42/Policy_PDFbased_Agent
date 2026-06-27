import httpx
import pytest

from app.modules.crawling.crawlers.http import HttpCrawler
from app.modules.crawling.schemas.source import CrawlSourceRead


@pytest.mark.asyncio
async def test_two_phase_crawler_does_not_persist_listing_pages(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pages = {
        "https://example.com/policies": """
            <html><body>
              <a href="/policies/one">One</a>
              <a href="/policies/two">Two</a>
              <a href="/policies?page=2">Next</a>
            </body></html>
        """,
        "https://example.com/policies/one": "<main><h1>One</h1></main>",
        "https://example.com/policies/two": "<main><h1>Two</h1></main>",
    }

    async def fake_get_html(
        _: HttpCrawler,
        __: httpx.AsyncClient,
        url: str,
    ) -> httpx.Response:
        request = httpx.Request("GET", url)
        return httpx.Response(
            200,
            request=request,
            text=pages[url],
            headers={"content-type": "text/html"},
        )

    monkeypatch.setattr(HttpCrawler, "_get_html", fake_get_html)
    source = CrawlSourceRead(
        name="Example",
        start_url="https://example.com/policies",
        allowed_domains=["example.com"],
        include_patterns=[r"^/policies(?:/.*)?$"],
        max_pages=3,
        max_documents=2,
    )

    result = await HttpCrawler().crawl(source)

    assert [document.url for document in result.documents] == [
        "https://example.com/policies/one",
        "https://example.com/policies/two",
    ]
    assert result.pages_visited == 3
    assert result.detail_urls_discovered == 2


@pytest.mark.asyncio
async def test_pagination_is_not_limited_by_max_depth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pages = {
        "https://example.com/policies": """
            <html><body>
              <a href="/policies/one">One</a>
              <a href="/policies?page=2">Next</a>
            </body></html>
        """,
        "https://example.com/policies?page=2": """
            <html><body>
              <a href="/policies/two">Two</a>
            </body></html>
        """,
        "https://example.com/policies/one": "<main><h1>One</h1></main>",
        "https://example.com/policies/two": "<main><h1>Two</h1></main>",
    }

    async def fake_get_html(
        _: HttpCrawler,
        __: httpx.AsyncClient,
        url: str,
    ) -> httpx.Response:
        request = httpx.Request("GET", url)
        return httpx.Response(
            200,
            request=request,
            text=pages[url],
            headers={"content-type": "text/html"},
        )

    monkeypatch.setattr(HttpCrawler, "_get_html", fake_get_html)
    source = CrawlSourceRead(
        name="Example",
        start_url="https://example.com/policies",
        allowed_domains=["example.com"],
        include_patterns=[r"^/policies(?:/.*)?$"],
        max_pages=4,
        max_documents=2,
        max_depth=0,
    )

    result = await HttpCrawler().crawl(source)

    assert [document.url for document in result.documents] == [
        "https://example.com/policies/one",
        "https://example.com/policies/two",
    ]
