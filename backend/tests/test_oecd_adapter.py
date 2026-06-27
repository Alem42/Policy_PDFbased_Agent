import httpx
from bs4 import BeautifulSoup

from app.modules.crawling.crawlers.adapters.oecd_ai import OecdAiCrawler
from app.modules.crawling.crawlers.http import HttpCrawler
from app.modules.crawling.crawlers.selector import CrawlerSelector
from app.modules.crawling.schemas.source import CrawlSourceRead


def test_oecd_adapter_generates_next_page_and_extracts_fields() -> None:
    listing = BeautifulSoup(
        """
        <h1>List of policy initiatives <span>(2348)</span></h1>
        """,
        "html.parser",
    )
    source = CrawlSourceRead(
        name="OECD",
        start_url="https://oecd.ai/en/dashboards/policy-initiatives",
        allowed_domains=["oecd.ai"],
    )
    crawler = OecdAiCrawler()

    assert crawler._pagination_links(
        listing,
        "https://oecd.ai/en/dashboards/policy-initiatives?page=1",
        source,
    ) == ["https://oecd.ai/en/dashboards/policy-initiatives?orderBy=startYearDesc&page=2"]

    html = """
    <html><head><title>Fallback</title></head><body><main>
      <h2 class="title is-2">Example policy</h2>
      <p>This is a sufficiently long policy summary used to validate structured
      extraction from an OECD policy detail page for the crawler adapter.</p>
      <h3>AI Tags</h3><ul><li>Transparency</li></ul>
      <div class="taxonomy-relation-list">
        <div class="flags"><span class="content">Australia</span></div>
        <div><p>Status:</p><ul><li>Active</li></ul></div>
        <div><p>Start Year:</p><ul><li>2026</li></ul></div>
        <div><p>Category:</p><ul><li>National strategy</li></ul></div>
      </div>
      <a download href="https://files.example/policy.pdf">Official PDF</a>
    </main></body></html>
    """
    response = httpx.Response(
        200,
        request=httpx.Request(
            "GET",
            "https://oecd.ai/en/dashboards/policy-initiatives/example",
        ),
        text=html,
        headers={"content-type": "text/html"},
    )

    document = crawler._parse_document(response, source)

    assert document.title == "Example policy"
    assert document.metadata["structured"]["country"] == "Australia"
    assert document.metadata["structured"]["policy_status"] == "Active"
    assert document.metadata["structured"]["start_year"] == 2026
    assert document.metadata["assets"][0]["asset_type"] == "pdf"


def test_oecd_adapter_can_be_disabled_for_config_only_crawling() -> None:
    source = CrawlSourceRead(
        name="OECD configured",
        start_url="https://oecd.ai/en/dashboards/policy-initiatives",
        allowed_domains=["oecd.ai"],
        config={"adapter": "none", "pagination": {"type": "numbered"}},
    )

    assert type(CrawlerSelector().primary(source)) is HttpCrawler
