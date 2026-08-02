"""Compatibility import for the former Chat-owned provider registry."""

from app.modules.web_search.registry import get_active_web_search_provider

__all__ = ["get_active_web_search_provider"]
