"""Secure, provider-independent permanent web-page import.

This module is the only supported entry point for turning a public web page
into a shared-library document. It owns validation and fetching, then delegates
the document-specific ingestion and deduplication work to ``save_web_import``.
HTTP routes and Agent tools should not duplicate any of these policies.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from urllib.parse import SplitResult, urlsplit, urlunsplit

from app.modules.documents.service import save_web_import
from app.modules.documents.web_governance import WebGovernanceService, web_governance_service
from app.modules.web_search.contracts import WebSearchResult
from app.modules.web_search.service import WebSearchService, web_search_service
from app.modules.web_search.url_security import validate_public_url

MAX_WEB_IMPORT_BYTES = 2 * 1024 * 1024
MAX_WEB_IMPORT_TITLE_CHARACTERS = 200


@dataclass(frozen=True)
class WebImportRequest:
    """Inputs required to permanently import one public page."""

    url: str
    imported_by: str
    imported_via: str
    title: str | None = None


@dataclass(frozen=True)
class WebImportResult:
    """Stable result returned to admin routes and Agent tools."""

    document: dict
    was_duplicate: bool
    source_url: str
    title: str


def normalize_web_url(url: str) -> str:
    """Return a stable public-URL identity without changing resource semantics.

    Scheme/host casing, default ports and fragments are non-semantic and are
    normalised. Paths and query parameters are preserved because changing them
    can select a different page. Public-address validation is performed
    separately because it requires DNS resolution.
    """

    raw = url.strip()
    parsed = urlsplit(raw)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Only public HTTP(S) URLs are supported")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("Web-page URLs must not contain embedded credentials")

    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError("The web-page URL contains an invalid port") from exc

    scheme = parsed.scheme.lower()
    hostname = parsed.hostname.lower().rstrip(".")
    host = f"[{hostname}]" if ":" in hostname else hostname
    default_port = (scheme == "http" and port == 80) or (scheme == "https" and port == 443)
    netloc = host if port is None or default_port else f"{host}:{port}"
    return urlunsplit(SplitResult(scheme, netloc, parsed.path, parsed.query, ""))


class WebImportService:
    """Fetch and permanently ingest one public web page.

    Side effects are all-or-nothing at the document-ingestion boundary:
    successful calls return an indexed document (or an existing duplicate),
    while failed new ingestions are cleaned up by ``save_web_import``.

    A service/provider and validator can be injected for deterministic tests.
    """

    def __init__(
        self,
        *,
        search_service: WebSearchService = web_search_service,
        url_validator: Callable[[str], Awaitable[None]] = validate_public_url,
        saver: Callable[..., Awaitable[tuple[dict, bool]]] = save_web_import,
        governance_service: WebGovernanceService = web_governance_service,
        max_content_bytes: int = MAX_WEB_IMPORT_BYTES,
    ) -> None:
        self._search_service = search_service
        self._url_validator = url_validator
        self._saver = saver
        self._governance_service = governance_service
        self._max_content_bytes = max_content_bytes

    async def import_page(self, request: WebImportRequest) -> WebImportResult:
        requested_url = normalize_web_url(request.url)
        await self._url_validator(requested_url)

        page = await self._search_service.fetch_page(requested_url)
        source_url = normalize_web_url(page.url or requested_url)
        if source_url != requested_url:
            # Provider-returned canonical/redirect URLs become the persisted
            # identity and therefore receive the same public-address policy.
            await self._url_validator(source_url)

        content = self._validated_content(page)
        title = self._resolved_title(request.title, page, source_url)
        document, was_duplicate = await self._saver(
            url=source_url,
            title=title,
            markdown=content,
            imported_by=request.imported_by,
            imported_via=request.imported_via,
        )
        await asyncio.to_thread(
            self._governance_service.register_import,
            str(document["id"]),
            created_by=request.imported_by,
        )
        display_title = document.get("title") or title or document.get("name") or source_url
        return WebImportResult(
            document=document,
            was_duplicate=was_duplicate,
            source_url=document.get("source_url") or source_url,
            title=display_title,
        )

    def _validated_content(self, page: WebSearchResult) -> str:
        content = page.content.strip()
        if not content:
            raise ValueError("The page did not contain readable text to import.")
        size = len(content.encode("utf-8"))
        if size > self._max_content_bytes:
            limit_mb = self._max_content_bytes / (1024 * 1024)
            raise ValueError(
                f"The page is too large to import ({size} bytes; limit {limit_mb:g} MB)."
            )
        return content

    @staticmethod
    def _resolved_title(
        requested_title: str | None,
        page: WebSearchResult,
        source_url: str,
    ) -> str:
        title = (requested_title or "").strip() or page.title.strip() or source_url
        return title[:MAX_WEB_IMPORT_TITLE_CHARACTERS]


web_import_service = WebImportService()
