from app.crawlers.base import CrawledDocument, CrawlResult
from app.services.crawl_service import CrawlService


def test_known_expected_total_requires_every_document() -> None:
    result = CrawlResult(
        crawler="http",
        documents=[CrawledDocument(url="https://example.com/1")],
        detail_urls_discovered=1,
        expected_documents=2,
    )

    assert CrawlService._is_complete(None, result) is False


def test_unknown_total_is_complete_when_discovery_exhausts() -> None:
    result = CrawlResult(
        crawler="http",
        documents=[CrawledDocument(url="https://example.com/1")],
        detail_urls_discovered=1,
        discovery_exhausted=True,
    )

    assert CrawlService._is_complete(None, result) is True
