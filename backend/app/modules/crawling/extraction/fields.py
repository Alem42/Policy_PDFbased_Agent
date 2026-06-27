import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

CORE_FIELDS = {
    "title",
    "summary",
    "country",
    "policy_status",
    "start_year",
    "end_year",
}


@dataclass(slots=True)
class ExtractedFields:
    structured: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


class ConfigFieldExtractor:
    """Extract common and site-specific fields from CSS selector rules."""

    def extract(
        self,
        soup: BeautifulSoup,
        *,
        page_url: str,
        config: dict[str, Any] | None,
    ) -> ExtractedFields:
        if not config:
            return ExtractedFields()

        structured: dict[str, Any] = {}
        metadata: dict[str, Any] = {}
        for name, raw_rule in config.items():
            if name == "metadata":
                if isinstance(raw_rule, dict):
                    for metadata_name, metadata_rule in raw_rule.items():
                        value = self._extract_rule(
                            soup,
                            page_url,
                            metadata_rule,
                        )
                        if value is not None and value != []:
                            metadata[metadata_name] = value
                continue
            if name not in CORE_FIELDS:
                continue
            value = self._extract_rule(soup, page_url, raw_rule)
            if value is not None and value != []:
                structured[name] = value
        return ExtractedFields(structured=structured, metadata=metadata)

    def _extract_rule(
        self,
        soup: BeautifulSoup,
        page_url: str,
        raw_rule: object,
    ) -> Any:
        rule = {"selector": raw_rule} if isinstance(raw_rule, str) else raw_rule
        if not isinstance(rule, dict):
            return None
        selector = rule.get("selector")
        if not isinstance(selector, str) or not selector:
            return rule.get("default")

        nodes = soup.select(selector)
        values = [
            value for node in nodes if (value := self._node_value(node, page_url, rule)) is not None
        ]
        multiple = bool(rule.get("multiple", False))
        if multiple:
            values = list(dict.fromkeys(values))
            return values or rule.get("default")
        return values[0] if values else rule.get("default")

    def _node_value(
        self,
        node: Tag,
        page_url: str,
        rule: dict[str, Any],
    ) -> Any:
        attribute = str(rule.get("attribute", "text"))
        if attribute == "text":
            value = node.get_text(
                str(rule.get("separator", " ")),
                strip=True,
            )
        else:
            raw_value = node.get(attribute)
            if not isinstance(raw_value, str):
                return None
            value = (
                urljoin(page_url, raw_value) if attribute in {"href", "src"} else raw_value.strip()
            )

        regex = rule.get("regex")
        if isinstance(regex, str):
            match = re.search(regex, value)
            if match is None:
                return None
            group = int(rule.get("group", 1 if match.lastindex else 0))
            value = match.group(group)

        transform = rule.get("transform")
        if transform in {"integer", "year"}:
            match = re.search(r"-?\d+", value.replace(",", ""))
            return int(match.group(0)) if match else None
        if transform == "lower":
            return value.lower()
        if transform == "upper":
            return value.upper()
        return re.sub(r"\s+", " ", value).strip()


field_extractor = ConfigFieldExtractor()
