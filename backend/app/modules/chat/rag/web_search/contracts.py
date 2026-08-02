"""Compatibility imports; new code uses :mod:`app.modules.web_search.contracts`."""

from app.modules.web_search.contracts import (
    WebSearchProvider,
    WebSearchProviderError,
    WebSearchResult,
)

__all__ = ["WebSearchProvider", "WebSearchProviderError", "WebSearchResult"]
