"""Oxylabs Web API search and page extraction for Hermes Agent."""

from __future__ import annotations

__version__ = "0.1.1"

__all__ = ["__version__", "register"]


def register(ctx) -> None:
    """Register the Oxylabs web search and extract provider."""
    from .provider import OxylabsWebSearchProvider

    ctx.register_web_search_provider(OxylabsWebSearchProvider(settings=ctx.get_config))
