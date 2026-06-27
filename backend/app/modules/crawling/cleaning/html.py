import re
from dataclasses import dataclass, field
from html import unescape
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup, NavigableString, Tag

DEFAULT_EXCLUDE_SELECTORS = [
    "script",
    "style",
    "noscript",
    "template",
    "svg",
    "nav",
    "footer",
    "[hidden]",
    "[aria-hidden='true']",
    ".cookie",
    ".cookies",
    ".cookie-banner",
    ".social-share",
    ".share",
]


@dataclass(slots=True)
class CleanedPage:
    title: str | None
    markdown: str
    assets: list[dict[str, object]] = field(default_factory=list)


class HtmlCleaner:
    def clean(
        self,
        html: str,
        *,
        page_url: str,
        content_selector: str | None = None,
        exclude_selectors: list[str] | None = None,
        asset_link_selector: str = "a[href]",
    ) -> CleanedPage:
        soup = BeautifulSoup(html, "html.parser")
        title = soup.title.get_text(" ", strip=True) if soup.title else None
        root = (
            soup.select_one(content_selector)
            if content_selector
            else soup.find("main") or soup.find("article") or soup.body or soup
        )
        if root is None:
            return CleanedPage(title=title, markdown="")

        for selector in [*DEFAULT_EXCLUDE_SELECTORS, *(exclude_selectors or [])]:
            for node in root.select(selector):
                node.decompose()

        assets = self._assets(root, page_url, asset_link_selector)
        markdown = self._normalize(self._render(root, page_url))
        return CleanedPage(title=title, markdown=markdown, assets=assets)

    def _render(self, node: object, page_url: str) -> str:
        if isinstance(node, NavigableString):
            return unescape(str(node))
        if not isinstance(node, Tag):
            return ""
        if self._is_decorative_icon(node):
            return ""

        name = node.name.lower()
        content = "".join(self._render(child, page_url) for child in node.children)

        if name in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            level = int(name[1])
            return f"\n\n{'#' * level} {self._inline(content)}\n\n"
        if name == "p":
            return f"\n\n{self._inline(content)}\n\n"
        if name == "br":
            return "\n"
        if name == "a":
            label = self._inline(content)
            href = node.get("href")
            if not isinstance(href, str) or not label:
                return label
            return f"[{label}]({urljoin(page_url, href)})"
        if name in {"strong", "b"}:
            inline = self._inline(content)
            return f"**{inline}**" if inline else ""
        if name in {"em", "i"}:
            inline = self._inline(content)
            return f"*{inline}*" if inline else ""
        if name == "code" and node.parent and node.parent.name != "pre":
            return f"`{self._inline(content)}`"
        if name == "pre":
            return f"\n\n```\n{node.get_text(chr(10), strip=False).strip()}\n```\n\n"
        if name == "blockquote":
            lines = self._normalize(content).splitlines()
            return "\n\n" + "\n".join(f"> {line}" for line in lines) + "\n\n"
        if name == "li":
            marker = "1." if node.parent and node.parent.name == "ol" else "-"
            return f"\n{marker} {self._inline(content)}"
        if name in {"ul", "ol"}:
            return f"\n{content.strip()}\n"
        if name == "tr":
            cells = [
                self._inline(self._render(cell, page_url))
                for cell in node.find_all(["th", "td"], recursive=False)
            ]
            return f"\n| {' | '.join(cells)} |" if cells else ""
        if name == "table":
            rows = [line for line in content.splitlines() if line.strip()]
            if not rows:
                return ""
            column_count = max(rows[0].count("|") - 1, 1)
            separator = f"| {' | '.join(['---'] * column_count)} |"
            return f"\n\n{rows[0]}\n{separator}\n" + "\n".join(rows[1:]) + "\n\n"
        if name in {"div", "section", "article", "main", "header"}:
            return f"\n{content}\n"
        return content

    def _assets(
        self,
        root: Tag,
        page_url: str,
        selector: str,
    ) -> list[dict[str, object]]:
        assets: list[dict[str, object]] = []
        seen: set[str] = set()
        for anchor in root.select(selector):
            href = anchor.get("href")
            if not isinstance(href, str):
                continue
            url = urljoin(page_url, href)
            parsed = urlparse(url)
            path = parsed.path.lower()
            mime_type = self._mime_type(path)
            download = anchor.has_attr("download")
            if mime_type is None and not download:
                continue
            if url in seen:
                continue
            seen.add(url)
            assets.append(
                {
                    "url": url,
                    "asset_type": "pdf" if mime_type == "application/pdf" else "attachment",
                    "title": anchor.get_text(" ", strip=True) or None,
                    "mime_type": mime_type,
                }
            )
        return assets

    @staticmethod
    def _mime_type(path: str) -> str | None:
        mapping = {
            ".pdf": "application/pdf",
            ".doc": "application/msword",
            ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ".xls": "application/vnd.ms-excel",
            ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ".csv": "text/csv",
        }
        return next((mime for suffix, mime in mapping.items() if path.endswith(suffix)), None)

    @staticmethod
    def _is_decorative_icon(node: Tag) -> bool:
        if not node.name or node.name.lower() not in {"i", "span"}:
            return False

        classes = node.get("class", [])
        if isinstance(classes, str):
            classes = classes.split()
        class_tokens = {class_name.lower() for class_name in classes}

        return any(
            class_name == "icon"
            or class_name.startswith("icon-")
            or class_name.endswith("-icon")
            or class_name in {"fa", "fas", "far", "fab", "fal", "fad", "bi", "glyphicon"}
            or class_name.startswith(
                ("fa-", "bi-", "glyphicon-", "material-icons", "material-symbols")
            )
            for class_name in class_tokens
        )

    @staticmethod
    def _inline(value: str) -> str:
        return re.sub(r"\s+", " ", value).strip()

    @staticmethod
    def _normalize(value: str) -> str:
        value = value.replace("\r\n", "\n").replace("\r", "\n")

        # Fix adjacent markdown links:
        # [Overview](...)[National](...) -> [Overview](...) [National](...)
        value = re.sub(r"\)\[", ") [", value)

        # Remove meaningless broken bold line, such as "** -"
        value = re.sub(
            r"^\s*\*\*\s*-\s*$",
            "",
            value,
            flags=re.MULTILINE,
        )

        # Fix broken metadata bold lines:
        # ** Added by: National contact point
        # -> **Added by:** National contact point
        value = re.sub(
            r"^\s*\*\*\s*(Added by|Added on|Updated by|Updated on):\s*(?!\*\*)(.*)$",
            r"**\1:** \2",
            value,
            flags=re.MULTILINE,
        )

        value = re.sub(r"[ \t]+\n", "\n", value)
        value = re.sub(r"\n[ \t]+", "\n", value)
        value = re.sub(r"\n{3,}", "\n\n", value)
        return value.strip()
