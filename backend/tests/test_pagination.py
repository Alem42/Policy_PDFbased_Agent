from bs4 import BeautifulSoup

from app.crawlers.pagination import ConfigPaginationStrategy


def test_numbered_pagination_extracts_total_and_generates_next_url() -> None:
    soup = BeautifulSoup(
        '<h1 class="results">Policies <span>(2,348)</span></h1>',
        "html.parser",
    )
    config = {
        "type": "numbered",
        "page_parameter": "page",
        "start_page": 1,
        "page_size": 20,
        "total_selector": "h1.results",
        "total_regex": r"\(([\d,]+)\)",
        "query": {"orderBy": "startYearDesc"},
    }

    result = ConfigPaginationStrategy().next_pages(
        soup,
        current_url="https://example.com/policies?page=1",
        config=config,
    )

    assert result is not None
    assert result.expected_documents == 2348
    assert result.urls == ["https://example.com/policies?page=2&orderBy=startYearDesc"]


def test_template_pagination_can_use_fixed_end_page() -> None:
    result = ConfigPaginationStrategy().next_pages(
        BeautifulSoup("", "html.parser"),
        current_url="https://example.com/policies/page/1",
        config={
            "type": "template",
            "page_parameter": "page",
            "url_template": "/policies/page/{page}",
            "current_page_regex": r"/page/(\d+)",
            "max_page": 3,
        },
    )

    assert result is not None
    assert result.urls == ["https://example.com/policies/page/2"]
