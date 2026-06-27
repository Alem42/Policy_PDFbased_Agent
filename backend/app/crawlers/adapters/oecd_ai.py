import math
import re
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import httpx
from bs4 import BeautifulSoup, Tag

from app.crawlers.base import CrawledDocument
from app.crawlers.http import HttpCrawler
from app.schemas.source import SourceRead


class OecdAiCrawler(HttpCrawler):
    """OECD.AI discovery and structured field adapter."""

    name = "http:oecd-ai"
    page_size = 20

    def _pagination_links(
        self,
        soup: BeautifulSoup,
        base_url: str,
        source: SourceRead,
    ) -> list[str]:
        heading = soup.find(
            string=lambda value: isinstance(value, str)
            and "List of policy initiatives" in value
        )
        heading_parent = heading.parent if heading else None
        container_text = (
            heading_parent.get_text(" ", strip=True)
            if isinstance(heading_parent, Tag)
            else ""
        )
        match = re.search(r"\(([\d,]+)\)", container_text)
        if match is None:
            return super()._pagination_links(soup, base_url, source)

        total = int(match.group(1).replace(",", ""))
        total_pages = math.ceil(total / self.page_size)
        parsed = urlparse(base_url)
        query = parse_qs(parsed.query)
        current_page = int(query.get("page", ["1"])[0])
        if current_page >= total_pages:
            return []

        next_query = {
            "orderBy": query.get("orderBy", ["startYearDesc"])[0],
            "page": str(current_page + 1),
        }
        return [
            urlunparse(
                parsed._replace(
                    path="/en/dashboards/policy-initiatives",
                    query=urlencode(next_query),
                    fragment="",
                )
            )
        ]

    def _parse_document(
        self,
        response: httpx.Response,
        source: SourceRead,
    ) -> CrawledDocument:
        document = super()._parse_document(response, source)
        document.markdown = self._clean_oecd_markdown(document.markdown)
        soup = BeautifulSoup(response.text, "html.parser")

        detail_title = soup.select_one("main h2.title.is-2")
        if detail_title is not None:
            document.title = detail_title.get_text(" ", strip=True)

        summary = self._summary_after(detail_title)
        country_node = soup.select_one(
            ".taxonomy-relation-list .flags span.content"
        )
        structured = {
            **document.metadata.get("structured", {}),
            "summary": summary,
            "country": (
                country_node.get_text(" ", strip=True) if country_node else None
            ),
            "policy_status": self._label_value(soup, "Status:"),
            "start_year": self._integer(self._label_value(soup, "Start Year:")),
            "end_year": self._integer(self._label_value(soup, "End Year:")),
        }
        document.metadata["structured"] = structured
        document.metadata["oecd_ai"] = {
            "category": self._label_values(soup, "Category:"),
            "initiative_type": self._label_values(soup, "Initiative type:"),
            "target_sectors": self._label_values(soup, "Target Sectors:"),
            "oecd_ai_principles": self._label_values(soup, "OECD AI Principles:"),
            "ai_tags": self._section_values(soup, "AI Tags"),
            "added_on": self._label_value(soup, "Added on:"),
            "updated_on": self._label_value(soup, "Updated on:"),
        }
        return document

    @staticmethod
    def _summary_after(title: Tag | None) -> str | None:
        if title is None:
            return None
        for paragraph in title.find_all_next("p"):
            text = paragraph.get_text(" ", strip=True)
            if len(text) >= 80:
                return text
        return None

    @staticmethod
    def _label_container(soup: BeautifulSoup, label: str) -> Tag | None:
        node = soup.find(
            string=lambda value: isinstance(value, str) and value.strip() == label
        )
        if node is None or not isinstance(node.parent, Tag):
            return None
        parent = node.parent.parent
        return parent if isinstance(parent, Tag) else None

    @classmethod
    def _label_values(cls, soup: BeautifulSoup, label: str) -> list[str]:
        container = cls._label_container(soup, label)
        if container is None:
            return []
        values = [
            item.get_text(" ", strip=True)
            for item in container.select("ul li")
            if item.get_text(" ", strip=True)
        ]
        if values:
            return values
        anchor = container.find("a")
        return [anchor.get_text(" ", strip=True)] if anchor else []

    @classmethod
    def _label_value(cls, soup: BeautifulSoup, label: str) -> str | None:
        values = cls._label_values(soup, label)
        if values:
            return values[0]
        container = cls._label_container(soup, label)
        if container is None:
            return None
        text = container.get_text(" ", strip=True).removeprefix(label).strip()
        return text or None

    @staticmethod
    def _section_values(soup: BeautifulSoup, heading_text: str) -> list[str]:
        heading = soup.find(
            ["h2", "h3", "h4"],
            string=lambda value: isinstance(value, str)
            and value.strip() == heading_text,
        )
        if heading is None:
            return []
        container = heading.parent
        if not isinstance(container, Tag):
            return []
        return [
            item.get_text(" ", strip=True)
            for item in container.select("li")
            if item.get_text(" ", strip=True)
        ]

    @staticmethod
    def _integer(value: str | None) -> int | None:
        if value is None:
            return None
        match = re.search(r"\b(18|19|20|21)\d{2}\b", value)
        return int(match.group(0)) if match else None
    
    @staticmethod
    def _clean_oecd_markdown(markdown: str | None) -> str:
        if not markdown:
            return ""

        text = markdown

        # Remove OECD.AI page-level navigator block before the actual policy title.
        text = re.sub(
            r"^# The OECD\.AI Policy Navigator[\s\S]*?(?=\n##\s+)",
            "",
            text,
            count=1,
        )

        # Fix adjacent markdown links, e.g. [Overview](...)[National](...)
        text = re.sub(r"\)\[", ") [", text)

        # Remove meaningless broken markdown line: ** -
        text = re.sub(
            r"^\s*\*\*\s*-\s*$",
            "",
            text,
            flags=re.MULTILINE,
        )

        # Fix broken bold metadata lines:
        # ** Added by: OECD analyst
        # -> **Added by:** OECD analyst
        text = re.sub(
            r"^\s*\*\*\s*(Added by|Added on|Updated by|Updated on):\s*(?!\*\*)(.*)$",
            r"**\1:** \2",
            text,
            flags=re.MULTILINE,
        )

        # Compress excessive blank lines.
        text = re.sub(r"\n{3,}", "\n\n", text)

        return text.strip()
