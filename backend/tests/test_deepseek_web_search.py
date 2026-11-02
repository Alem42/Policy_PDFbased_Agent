import json
from types import SimpleNamespace

import httpx
import pytest

from app.modules.settings import service as settings
from app.modules.settings.schemas import RuntimeSettings
from app.modules.web_search import registry
from app.modules.web_search.contracts import WebSearchProviderError
from app.modules.web_search.providers.deepseek import DeepSeekSearchProvider


@pytest.fixture
def credentials(monkeypatch):
    state = {"value": RuntimeSettings(provider_api_keys={"deepseek": "shared-test-key"})}
    monkeypatch.setattr(
        settings.settings_repository, "load", lambda: state["value"].model_copy(deep=True)
    )
    monkeypatch.setattr(
        settings.settings_repository, "save", lambda value: state.update(value=value)
    )
    return state


def test_registry_supports_deepseek_and_reuses_key(credentials, monkeypatch):
    monkeypatch.setattr(registry, "get_web_search_provider", lambda: "deepseek")
    assert isinstance(registry.get_active_web_search_provider(), DeepSeekSearchProvider)
    assert settings.get_web_search_provider_api_key("deepseek") == "shared-test-key"
    public = settings.get_public_settings()
    assert public["web_search_key_sources"]["deepseek"] == "llm"
    assert public["masked_web_search_provider_keys"]["deepseek"] == "shar...-key"
    assert "shared-test-key" not in json.dumps(public)


def test_dedicated_key_overrides_shared_key_and_clearing_restores_it(credentials):
    settings.update_public_settings(
        web_search_provider="deepseek",
        web_search_provider_api_keys={"deepseek": "separate-test-key"},
    )
    assert settings.get_web_search_provider_api_key("deepseek") == "separate-test-key"
    assert settings.get_public_settings()["web_search_key_sources"]["deepseek"] == "search"
    settings.update_public_settings(web_search_provider_api_keys={"deepseek": ""})
    assert settings.get_web_search_provider_api_key("deepseek") == "shared-test-key"
    assert credentials["value"].provider_api_keys["deepseek"] == "shared-test-key"
    assert credentials["value"].web_search_provider == "deepseek"


def test_shared_key_tracks_rotation_and_does_not_depend_on_active_chat_provider(credentials):
    credentials["value"].llm_provider = "zhipu"
    credentials["value"].provider_api_keys["deepseek"] = "rotated-key"
    assert settings.get_web_search_provider_api_key("deepseek") == "rotated-key"
    assert settings.get_web_search_provider_api_key("tavily") is None


def test_firecrawl_key_and_environment_fallback_stay_separate(credentials, monkeypatch):
    monkeypatch.setattr(
        settings, "get_settings", lambda: SimpleNamespace(firecrawl_api_key="fc-env")
    )
    assert settings.get_web_search_provider_api_key("firecrawl") == "fc-env"
    credentials["value"].web_search_provider_api_keys["firecrawl"] = "fc-saved"
    assert settings.get_web_search_provider_api_key("firecrawl") == "fc-saved"
    assert settings.get_web_search_provider_api_key("deepseek") == "shared-test-key"


async def test_search_sends_raw_api_request_and_maps_page_evidence():
    def handler(request):
        assert str(request.url) == "https://api.deepseek.com/v1/tools/search"
        assert request.headers["Authorization"] == "Bearer test-key"
        assert json.loads(request.content) == {
            "query": "政策 evidence",
            "count": 2,
            "need_content": True,
        }
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "url": "https://nist.gov/policy",
                        "title": "Policy",
                        "content": "Original page text",
                        "snippet": "Snippet",
                        "summary": "Generated summary",
                        "date": "2026-10-01T00:00:00Z",
                        "authority": 4,
                    },
                    {
                        "url": "https://example.org/other",
                        "title": "Other",
                        "content": "",
                        "snippet": "Search excerpt",
                        "summary": "Not original source text",
                    },
                ]
            },
        )

    provider = DeepSeekSearchProvider("test-key", transport=httpx.MockTransport(handler))
    results = await provider.search("  政策 evidence  ", limit=2)
    assert results[0].content == "Original page text"
    assert results[0].published_at == "2026-10-01T00:00:00Z"
    assert results[0].metadata["authority"] == 4
    assert results[1].content == "Search excerpt"
    assert results[1].metadata["content_type"] == "search_snippet"


async def test_fetch_returns_markdown_for_existing_import_pipeline():
    def handler(request):
        assert str(request.url).endswith("/fetch")
        assert json.loads(request.content) == {"url": "https://example.org/policy"}
        return httpx.Response(200, json={"title": "Policy", "content": "# Original policy\nBody"})

    result = await DeepSeekSearchProvider(
        "test", transport=httpx.MockTransport(handler)
    ).fetch_page("https://example.org/policy")
    assert result.url == "https://example.org/policy" and result.content.startswith("# Original")


@pytest.mark.parametrize("query,limit", [("", 5), ("   ", 5), ("q" * 129, 5), ("q", 0), ("q", 51)])
async def test_invalid_search_inputs_never_send_a_request(query, limit):
    def unexpected(_):
        pytest.fail("Must reject before sending")

    provider = DeepSeekSearchProvider("test", transport=httpx.MockTransport(unexpected))
    with pytest.raises(WebSearchProviderError):
        await provider.search(query, limit=limit)


async def test_empty_search_is_a_valid_result_and_unsafe_links_are_ignored():
    responses = [[], [{"url": "javascript:alert(1)"}, {"url": "https://name:secret@example.org/"}]]
    provider = DeepSeekSearchProvider(
        "test",
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, json={"results": responses.pop(0)})
        ),
    )
    assert await provider.search("no match") == []
    assert await provider.search("unsafe links") == []


@pytest.mark.parametrize("status", [401, 402, 429, 503])
async def test_provider_http_errors_are_explicit_and_do_not_leak_credentials(status):
    transport = httpx.MockTransport(
        lambda _: httpx.Response(status, json={"error": {"message": "private-test-key"}})
    )
    with pytest.raises(WebSearchProviderError, match=f"HTTP {status}") as error:
        await DeepSeekSearchProvider("private-test-key", transport=transport).search(
            "public policy"
        )
    assert "private-test-key" not in str(error.value)


@pytest.mark.parametrize("payload", [[], {}, {"results": "bad"}, {"results": [None]}])
async def test_malformed_success_responses_fail_explicitly(payload):
    provider = DeepSeekSearchProvider(
        "test", transport=httpx.MockTransport(lambda _: httpx.Response(200, json=payload))
    )
    with pytest.raises(WebSearchProviderError):
        await provider.search("policy")


@pytest.mark.parametrize("url", ["file:///etc/passwd", "https://user:pass@example.org/", "bad url"])
async def test_fetch_rejects_invalid_or_credential_bearing_urls(url):
    with pytest.raises(WebSearchProviderError):
        await DeepSeekSearchProvider("test").fetch_page(url)


async def test_missing_key_does_not_call_provider():
    with pytest.raises(WebSearchProviderError, match="No DeepSeek API key"):
        await DeepSeekSearchProvider("").search("policy")


async def test_timeout_and_empty_fetch_are_provider_errors():
    def timeout(request):
        raise httpx.ReadTimeout("network timeout", request=request)

    with pytest.raises(WebSearchProviderError, match="timed out"):
        await DeepSeekSearchProvider("test", transport=httpx.MockTransport(timeout)).search(
            "policy"
        )
    provider = DeepSeekSearchProvider(
        "test",
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, json={"title": "Empty", "content": ""})
        ),
    )
    with pytest.raises(WebSearchProviderError, match="no readable"):
        await provider.fetch_page("https://example.org/policy")
