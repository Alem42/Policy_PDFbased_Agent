"""Provider-independent public web search and page fetching.

Callers should normally use :data:`web_search_service` rather than importing a
concrete provider.  Keeping provider selection here prevents document and chat
features from depending on each other.
"""

from app.modules.web_search.service import WebSearchService, web_search_service

__all__ = ["WebSearchService", "web_search_service"]
