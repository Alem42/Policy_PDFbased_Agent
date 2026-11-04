"""DeepSeek's raw Search / Fetch APIs; no chat completion is involved.

API reference: https://api-docs.deepseek.com/guides/search/
"""

from __future__ import annotations

import asyncio
from urllib.parse import urlsplit

import httpx

from app.modules.settings.service import get_web_search_provider_api_key
from app.modules.usage import budget, recorder
from app.modules.web_search.contracts import WebSearchProviderError, WebSearchResult

BASE_URL = "https://api.deepseek.com/v1/tools"


def _http_url(value: str) -> bool:
    try:
        parsed = urlsplit(value)
        return bool(
            parsed.scheme in {"http", "https"}
            and parsed.hostname
            and parsed.username is None
            and parsed.password is None
        )
    except ValueError:
        return False


class DeepSeekSearchProvider:
    name = "deepseek"

    def __init__(self, api_key: str | None = None, *, transport=None):
        self._api_key = (
            api_key if api_key is not None else get_web_search_provider_api_key(self.name)
        )
        self._transport = transport

    async def _post(self, operation: str, payload: dict) -> dict:
        if not self._api_key:
            raise WebSearchProviderError(
                "No DeepSeek API key is configured. Save a General Access Key in Web search "
                "or configure the DeepSeek key in the model settings."
            )
        budget.ensure_within_budget()
        try:
            async with httpx.AsyncClient(
                timeout=30,
                follow_redirects=False,
                transport=self._transport,
                headers={"Authorization": f"Bearer {self._api_key}"},
            ) as client:
                response = await client.post(f"{BASE_URL}/{operation}", json=payload)
                response.raise_for_status()
                data = response.json()
            await asyncio.to_thread(recorder.record, "deepseek", operation, "web_search")
            if not isinstance(data, dict):
                raise ValueError("Expected a JSON object")
            return data
        except httpx.HTTPStatusError as exc:
            # Do not echo provider bodies, request headers, or credentials.
            raise WebSearchProviderError(
                f"DeepSeek {operation} failed (HTTP {exc.response.status_code})."
            ) from exc
        except httpx.TimeoutException as exc:
            raise WebSearchProviderError(f"DeepSeek {operation} timed out.") from exc
        except httpx.RequestError as exc:
            raise WebSearchProviderError(f"DeepSeek {operation} could not connect.") from exc
        except ValueError as exc:
            raise WebSearchProviderError(f"DeepSeek {operation} returned invalid JSON.") from exc

    async def search(self, query: str, *, limit: int = 5) -> list[WebSearchResult]:
        query = query.strip()
        if not 1 <= len(query) <= 128:
            raise WebSearchProviderError("DeepSeek search queries must contain 1–128 characters.")
        if not 1 <= limit <= 50:
            raise WebSearchProviderError("DeepSeek search result count must be between 1 and 50.")
        data = await self._post("search", {"query": query, "count": limit, "need_content": True})
        items = data.get("results")
        if not isinstance(items, list):
            raise WebSearchProviderError("DeepSeek search returned an invalid results array.")
        results = []
        for item in items[:limit]:
            if not isinstance(item, dict):
                raise WebSearchProviderError("DeepSeek search returned an invalid result.")
            url = item.get("url")
            if not isinstance(url, str) or not _http_url(url):
                continue
            content = item.get("content") or item.get("snippet") or ""
            title = item.get("title") or url
            if not isinstance(content, str) or not isinstance(title, str):
                raise WebSearchProviderError("DeepSeek search returned invalid page text.")
            results.append(
                WebSearchResult(
                    url=url,
                    title=title,
                    content=content,
                    published_at=item.get("date") if isinstance(item.get("date"), str) else None,
                    metadata={
                        "provider": self.name,
                        "content_type": "page_content" if item.get("content") else "search_snippet",
                        **{
                            key: item.get(key)
                            for key in (
                                "rerank_score",
                                "authority",
                                "site_name",
                                "site_icon",
                            )
                        },
                    },
                )
            )
        return results

    async def fetch_page(self, url: str) -> WebSearchResult:
        url = url.strip()
        if len(url) > 8192 or not _http_url(url):
            raise WebSearchProviderError(
                "DeepSeek fetch requires an HTTP(S) URL without credentials."
            )
        data = await self._post("fetch", {"url": url})
        content = data.get("content")
        title = data.get("title") or url
        if not isinstance(content, str) or not content.strip() or not isinstance(title, str):
            raise WebSearchProviderError("DeepSeek fetch returned no readable page content.")
        return WebSearchResult(
            url=url,
            title=title,
            content=content,
            metadata={"provider": self.name, "content_type": "page_content"},
        )
