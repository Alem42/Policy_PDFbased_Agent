"""WebSearchProvider abstraction: registry selection and settings validation."""

from __future__ import annotations

import pytest

from app.modules.settings import service as settings_service
from app.modules.web_search import registry as web_search_registry
from app.modules.web_search.contracts import WebSearchProviderError
from app.modules.web_search.providers.firecrawl import FirecrawlSearchProvider
from app.modules.web_search.providers.tavily import TavilySearchProvider
from app.modules.web_search.registry import get_active_web_search_provider


def test_registry_defaults_to_firecrawl(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(web_search_registry, "get_web_search_provider", lambda: "firecrawl")
    provider = get_active_web_search_provider()
    assert isinstance(provider, FirecrawlSearchProvider)
    assert provider.name == "firecrawl"


def test_registry_selects_tavily(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(web_search_registry, "get_web_search_provider", lambda: "tavily")
    provider = get_active_web_search_provider()
    assert isinstance(provider, TavilySearchProvider)


def test_registry_rejects_unknown_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(web_search_registry, "get_web_search_provider", lambda: "bing")
    with pytest.raises(WebSearchProviderError):
        get_active_web_search_provider()


@pytest.mark.asyncio
async def test_tavily_provider_not_implemented() -> None:
    provider = TavilySearchProvider(api_key="unused")
    with pytest.raises(WebSearchProviderError):
        await provider.search("test query")
    with pytest.raises(WebSearchProviderError):
        await provider.fetch_page("https://example.com")


def test_update_public_settings_rejects_unknown_web_search_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.modules.settings.repository import settings_repository
    from app.modules.settings.schemas import RuntimeSettings

    monkeypatch.setattr(settings_repository, "load", lambda: RuntimeSettings())
    monkeypatch.setattr(settings_repository, "save", lambda settings: None)

    with pytest.raises(ValueError):
        settings_service.update_public_settings(web_search_provider="bing")


def test_update_public_settings_accepts_known_web_search_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.modules.settings.repository import settings_repository
    from app.modules.settings.schemas import RuntimeSettings

    saved: dict = {}
    monkeypatch.setattr(settings_repository, "load", lambda: RuntimeSettings())
    monkeypatch.setattr(
        settings_repository, "save", lambda settings: saved.update({"settings": settings})
    )
    monkeypatch.setattr("app.modules.embedding.service.invalidate_provider_cache", lambda: None)

    settings_service.update_public_settings(
        web_search_provider="tavily",
        web_search_provider_api_keys={"tavily": "tvly-secret"},
    )

    assert saved["settings"].web_search_provider == "tavily"
    assert saved["settings"].web_search_provider_api_keys == {"tavily": "tvly-secret"}
