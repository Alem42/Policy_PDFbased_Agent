import hashlib
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

import httpx

from app.core.config import get_settings
from app.modules.crawling.crawlers.base import CrawledDocument
from app.modules.crawling.schemas.source import CrawlSourceRead
from app.modules.crawling.security.urls import validate_public_url


class AttachmentDownloader:
    def __init__(self, download_dir: Path | None = None) -> None:
        self.download_dir = download_dir

    async def download(
        self,
        source: CrawlSourceRead,
        documents: list[CrawledDocument],
        *,
        client: httpx.AsyncClient | None = None,
    ) -> list[str]:
        if not source.config.get("download_pdf_attachments", False):
            return []

        settings = get_settings()
        errors: list[str] = []
        if client is not None:
            return await self._download_with_client(source, documents, client)

        async with httpx.AsyncClient(
            timeout=settings.default_request_timeout_seconds,
            follow_redirects=True,
            headers={"User-Agent": settings.user_agent},
        ) as owned_client:
            errors.extend(await self._download_with_client(source, documents, owned_client))
        return errors

    async def _download_with_client(
        self,
        source: CrawlSourceRead,
        documents: list[CrawledDocument],
        client: httpx.AsyncClient,
    ) -> list[str]:
        errors: list[str] = []
        for document in documents:
            assets = document.metadata.get("assets", [])
            if not isinstance(assets, list):
                continue
            for asset in assets:
                if not isinstance(asset, dict) or not self._is_pdf_asset(asset):
                    continue
                url = asset.get("url")
                if not isinstance(url, str):
                    continue
                try:
                    await self._download_asset(source, document, asset, url, client)
                except Exception as exc:
                    self._set_download_metadata(asset, status="failed", error=str(exc))
                    errors.append(f"{url}: {exc}")
        return errors

    async def _download_asset(
        self,
        source: CrawlSourceRead,
        document: CrawledDocument,
        asset: dict[str, object],
        url: str,
        client: httpx.AsyncClient,
    ) -> None:
        await validate_public_url(url)
        response = await client.get(url)
        response.raise_for_status()

        target = self._target_path(source, document, url)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(response.content)

        self._set_download_metadata(
            asset,
            status="downloaded",
            local_path=str(target),
            bytes=len(response.content),
            http_status=response.status_code,
        )

    def _target_path(
        self,
        source: CrawlSourceRead,
        document: CrawledDocument,
        url: str,
    ) -> Path:
        base_dir = self.download_dir or get_settings().attachment_download_dir
        document_key = hashlib.sha256(document.url.encode("utf-8")).hexdigest()[:16]
        asset_key = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
        suffix = Path(urlparse(url).path).suffix or ".pdf"
        return base_dir / str(source.id) / document_key / f"{asset_key}{suffix}"

    @staticmethod
    def _is_pdf_asset(asset: dict[str, object]) -> bool:
        url = asset.get("url")
        mime_type = asset.get("mime_type")
        return (
            asset.get("asset_type") == "pdf"
            or mime_type == "application/pdf"
            or (isinstance(url, str) and urlparse(url).path.lower().endswith(".pdf"))
        )

    @staticmethod
    def _set_download_metadata(asset: dict[str, object], **values: object) -> None:
        metadata = asset.get("metadata")
        if not isinstance(metadata, dict):
            metadata = {}
            asset["metadata"] = metadata
        metadata["download"] = {
            "downloaded_at": datetime.now(UTC).isoformat(),
            **values,
        }


attachment_downloader = AttachmentDownloader()
