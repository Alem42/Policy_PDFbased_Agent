from __future__ import annotations

from dataclasses import replace

import pytest

from app.modules.documents.web_import import (
    WebImportRequest,
    WebImportService,
    normalize_web_url,
)
from app.modules.web_search.contracts import WebSearchResult


class FakeSearchService:
    def __init__(self, page: WebSearchResult) -> None:
        self.page = page
        self.requested_url: str | None = None

    async def fetch_page(self, url: str) -> WebSearchResult:
        self.requested_url = url
        return self.page


class FakeGovernanceService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str | None]] = []

    def register_import(self, document_id: str, *, created_by: str | None):
        self.calls.append((document_id, created_by))
        return {"document_id": document_id}


def request(**overrides) -> WebImportRequest:
    base = WebImportRequest(
        url="HTTPS://Example.COM:443/policy#overview",
        title="Admin title",
        imported_by="user-1",
        imported_via="web_import_admin",
    )
    return replace(base, **overrides)


def test_normalize_web_url_removes_non_semantic_parts() -> None:
    assert normalize_web_url(" HTTPS://Example.COM:443/policy?q=1#part ") == (
        "https://example.com/policy?q=1"
    )


@pytest.mark.parametrize(
    "url",
    ["file:///tmp/a", "https://user:secret@example.com/a", "https://example.com:bad/a"],
)
def test_normalize_web_url_rejects_unsafe_or_invalid_shapes(url: str) -> None:
    with pytest.raises(ValueError):
        normalize_web_url(url)


@pytest.mark.asyncio
async def test_import_page_validates_requested_and_canonical_url_and_persists_title() -> None:
    page = WebSearchResult(
        url="https://WWW.example.com:443/canonical#top",
        title="Site title",
        content="  # Policy\n\nReadable content.  ",
    )
    search = FakeSearchService(page)
    validated: list[str] = []
    saved: dict = {}

    async def validate(url: str) -> None:
        validated.append(url)

    async def save(**kwargs):
        saved.update(kwargs)
        return {
            "id": "document-1",
            "title": kwargs["title"],
            "source_url": kwargs["url"],
        }, False

    governance = FakeGovernanceService()
    service = WebImportService(
        search_service=search,
        url_validator=validate,
        saver=save,
        governance_service=governance,
    )
    result = await service.import_page(request())

    assert search.requested_url == "https://example.com/policy"
    assert validated == [
        "https://example.com/policy",
        "https://www.example.com/canonical",
    ]
    assert saved == {
        "url": "https://www.example.com/canonical",
        "title": "Admin title",
        "markdown": "# Policy\n\nReadable content.",
        "imported_by": "user-1",
        "imported_via": "web_import_admin",
    }
    assert result.title == "Admin title"
    assert result.source_url == "https://www.example.com/canonical"
    assert result.was_duplicate is False
    assert governance.calls == [("document-1", "user-1")]


@pytest.mark.asyncio
async def test_import_page_uses_provider_title_when_no_override() -> None:
    page = WebSearchResult(
        url="https://example.com/policy",
        title="Site title",
        content="Readable content",
    )

    async def validate(_: str) -> None: ...

    async def save(**kwargs):
        return {"id": "document-1", "source_url": kwargs["url"]}, False

    service = WebImportService(
        search_service=FakeSearchService(page),
        url_validator=validate,
        saver=save,
        governance_service=FakeGovernanceService(),
    )
    result = await service.import_page(request(title=None))
    assert result.title == "Site title"


@pytest.mark.asyncio
async def test_import_page_rejects_blank_content_before_saving() -> None:
    page = WebSearchResult(url="https://example.com", title="Empty", content="  \n")
    saved = False

    async def validate(_: str) -> None: ...

    async def save(**kwargs):
        nonlocal saved
        saved = True
        return {}, False

    service = WebImportService(
        search_service=FakeSearchService(page),
        url_validator=validate,
        saver=save,
        governance_service=FakeGovernanceService(),
    )
    with pytest.raises(ValueError, match="readable text"):
        await service.import_page(request(url="https://example.com"))
    assert saved is False


@pytest.mark.asyncio
async def test_import_page_rejects_oversized_content_before_saving() -> None:
    page = WebSearchResult(url="https://example.com", title="Large", content="12345")

    async def validate(_: str) -> None: ...

    async def save(**kwargs):  # pragma: no cover - must not be reached
        raise AssertionError("oversized content was saved")

    service = WebImportService(
        search_service=FakeSearchService(page),
        url_validator=validate,
        saver=save,
        governance_service=FakeGovernanceService(),
        max_content_bytes=4,
    )
    with pytest.raises(ValueError, match="too large"):
        await service.import_page(request(url="https://example.com"))
