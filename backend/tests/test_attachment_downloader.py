import anyio
import httpx
import pytest

from app.crawlers.base import CrawledDocument
from app.schemas.crawl_source import CrawlSourceRead
from app.services.attachment_downloader import AttachmentDownloader


@pytest.mark.asyncio
async def test_attachment_downloader_saves_pdf_and_updates_metadata(
    tmp_path,
    monkeypatch,
) -> None:
    async def validate_public_url_stub(url: str) -> None:
        return None

    monkeypatch.setattr(
        "app.services.attachment_downloader.validate_public_url",
        validate_public_url_stub,
    )

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://files.example/policy.pdf"
        return httpx.Response(
            200,
            content=b"%PDF-1.7 example",
            headers={"content-type": "application/pdf"},
        )

    source = CrawlSourceRead(
        name="Example",
        start_url="https://example.com",
        allowed_domains=["example.com"],
        config={"download_pdf_attachments": True},
    )
    document = CrawledDocument(
        url="https://example.com/policy",
        metadata={
            "assets": [
                {
                    "url": "https://files.example/policy.pdf",
                    "asset_type": "pdf",
                    "mime_type": "application/pdf",
                }
            ]
        },
    )
    downloader = AttachmentDownloader(download_dir=tmp_path)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        errors = await downloader.download(source, [document], client=client)

    assert errors == []
    asset = document.metadata["assets"][0]
    metadata = asset["metadata"]["download"]
    assert metadata["status"] == "downloaded"
    assert metadata["bytes"] == len(b"%PDF-1.7 example")
    assert metadata["http_status"] == 200
    assert await anyio.Path(metadata["local_path"]).exists()


@pytest.mark.asyncio
async def test_attachment_downloader_skips_when_source_config_is_disabled(tmp_path) -> None:
    source = CrawlSourceRead(
        name="Example",
        start_url="https://example.com",
        allowed_domains=["example.com"],
        config={"download_pdf_attachments": False},
    )
    document = CrawledDocument(
        url="https://example.com/policy",
        metadata={"assets": [{"url": "https://files.example/policy.pdf", "asset_type": "pdf"}]},
    )
    downloader = AttachmentDownloader(download_dir=tmp_path)

    errors = await downloader.download(source, [document])

    assert errors == []
    assert "metadata" not in document.metadata["assets"][0]
    assert list(tmp_path.iterdir()) == []
