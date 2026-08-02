"""Compatibility imports for the former Chat-owned Firecrawl adapter."""

from app.modules.web_search.providers.firecrawl import (
    FirecrawlSearchProvider,
    _result_from_item,
)

__all__ = ["FirecrawlSearchProvider", "_result_from_item"]
