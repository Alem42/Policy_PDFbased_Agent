import math
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qs, urlencode, urljoin, urlparse, urlunparse

from bs4 import BeautifulSoup


@dataclass(slots=True)
class PaginationPage:
    urls: list[str]
    expected_documents: int | None = None


class ConfigPaginationStrategy:
    """Generate listing-page URLs from source.config.pagination."""

    def next_pages(
        self,
        soup: BeautifulSoup,
        *,
        current_url: str,
        config: dict[str, Any] | None,
    ) -> PaginationPage | None:
        if not config:
            return None
        strategy_type = str(config.get("type", "link"))
        expected = self.expected_documents(soup, config)

        if strategy_type == "link":
            urls = self._link_pages(soup, current_url, config)
        elif strategy_type in {"numbered", "template"}:
            urls = self._numbered_pages(
                current_url,
                config,
                expected_documents=expected,
            )
        else:
            raise ValueError(f"Unsupported pagination type: {strategy_type}")
        return PaginationPage(urls=urls, expected_documents=expected)

    def expected_documents(
        self,
        soup: BeautifulSoup,
        config: dict[str, Any],
    ) -> int | None:
        fixed_total = config.get("total_documents")
        if isinstance(fixed_total, int):
            return fixed_total

        selector = config.get("total_selector")
        if not isinstance(selector, str):
            return None
        node = soup.select_one(selector)
        if node is None:
            return None
        attribute = str(config.get("total_attribute", "text"))
        if attribute == "text":
            value = node.get_text(" ", strip=True)
        else:
            raw = node.get(attribute)
            if not isinstance(raw, str):
                return None
            value = raw
        pattern = str(config.get("total_regex", r"([\d,]+)"))
        match = re.search(pattern, value)
        if match is None:
            return None
        group = int(config.get("total_group", 1 if match.lastindex else 0))
        return int(match.group(group).replace(",", ""))

    @staticmethod
    def _link_pages(
        soup: BeautifulSoup,
        current_url: str,
        config: dict[str, Any],
    ) -> list[str]:
        selector = str(config.get("selector", 'a[href][rel~="next"]'))
        urls: list[str] = []
        for anchor in soup.select(selector):
            href = anchor.get("href")
            if isinstance(href, str):
                urls.append(urljoin(current_url, href))
        return list(dict.fromkeys(urls))

    @staticmethod
    def _numbered_pages(
        current_url: str,
        config: dict[str, Any],
        *,
        expected_documents: int | None,
    ) -> list[str]:
        parsed = urlparse(current_url)
        page_parameter = str(config.get("page_parameter", "page"))
        query = parse_qs(parsed.query)
        start_page = int(config.get("start_page", 1))
        current_page = ConfigPaginationStrategy._current_page(
            current_url,
            query,
            config,
            page_parameter=page_parameter,
            start_page=start_page,
        )
        end_page = ConfigPaginationStrategy._end_page(
            config,
            expected_documents=expected_documents,
            start_page=start_page,
        )
        next_page = current_page + 1
        if end_page is not None and next_page > end_page:
            return []

        template = config.get("url_template")
        if isinstance(template, str):
            return [urljoin(current_url, template.format(page=next_page))]

        query[page_parameter] = [str(next_page)]
        static_query = config.get("query", {})
        if isinstance(static_query, dict):
            for key, value in static_query.items():
                query[str(key)] = [str(value)]
        return [
            urlunparse(
                parsed._replace(
                    query=urlencode(
                        [(key, item) for key, values in query.items() for item in values]
                    ),
                    fragment="",
                )
            )
        ]

    @staticmethod
    def _end_page(
        config: dict[str, Any],
        *,
        expected_documents: int | None,
        start_page: int,
    ) -> int | None:
        max_page = config.get("max_page")
        if isinstance(max_page, int):
            return max_page
        if expected_documents is None:
            return None
        page_size = int(config.get("page_size", 0))
        if page_size <= 0:
            return None
        return start_page + math.ceil(expected_documents / page_size) - 1

    @staticmethod
    def _current_page(
        current_url: str,
        query: dict[str, list[str]],
        config: dict[str, Any],
        *,
        page_parameter: str,
        start_page: int,
    ) -> int:
        if page_parameter in query:
            return int(query[page_parameter][0])
        pattern = config.get("current_page_regex")
        if isinstance(pattern, str):
            match = re.search(pattern, current_url)
            if match:
                group = int(config.get("current_page_group", 1))
                return int(match.group(group))
        return start_page


pagination_strategy = ConfigPaginationStrategy()
