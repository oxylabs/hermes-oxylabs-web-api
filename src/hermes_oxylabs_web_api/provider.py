"""Hermes web search and extraction backed by the Oxylabs Web API."""

from __future__ import annotations

import asyncio
import logging
import re
import time
from collections.abc import Callable
from typing import Any

import httpx
from agent.web_search_provider import WebSearchProvider, get_provider_env

from .client import API_KEY_ENV, MAX_SEARCH_RESULTS, OxylabsApiError, scrape_page, search_web

logger = logging.getLogger(__name__)

PROVIDER_NAME = "oxylabs"
SIGNUP_URL = "https://dashboard.oxylabs.io/"
# Hermes cancels a whole extract() dispatch after `web.extract_timeout` (120 s by default);
# finish a little earlier so each page reports its own error instead of a blanket timeout.
EXTRACT_DEADLINE_SECONDS = 110.0
_COUNTRY_CODE = re.compile(r"^[A-Za-z]{2}$")

# Reads one of this plugin's settings (`plugins.entries.oxylabs-web-api.settings.<key>`).
SettingReader = Callable[[str, Any], Any]


def _no_settings(key: str, default: Any = None) -> Any:
    return default


def _missing_key_error() -> str:
    return (
        f"{API_KEY_ENV} is not set. Get a Web API key at {SIGNUP_URL}, then run `hermes tools` "
        f"(Web Search & Extract → Oxylabs Web API) or add {API_KEY_ENV} to ~/.hermes/.env."
    )


def _title_from_markdown(markdown: str) -> str:
    for line in markdown.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return ""


class OxylabsWebSearchProvider(WebSearchProvider):
    """Search Google and fetch pages as Markdown through the Oxylabs Web API."""

    def __init__(self, settings: SettingReader = _no_settings) -> None:
        self._settings = settings

    @property
    def name(self) -> str:
        return PROVIDER_NAME

    @property
    def display_name(self) -> str:
        return "Oxylabs Web API"

    def is_available(self) -> bool:
        """True when a key is configured. No network call."""
        return bool(get_provider_env(API_KEY_ENV))

    def supports_search(self) -> bool:
        return True

    def supports_extract(self) -> bool:
        return True

    def _location(self) -> tuple[str | None, str | None]:
        """The configured country as ``(code, None)``, or ``(None, error)`` when it is not a country code."""
        value = self._settings("location", "")
        if not value:
            return None, None
        if not isinstance(value, str) or not _COUNTRY_CODE.match(value.strip()):
            return None, f"Oxylabs location setting must be a two-letter country code such as US, not {value!r}."
        return value.strip().upper(), None

    def search(self, query: str, limit: int = 5) -> dict[str, Any]:
        query = str(query or "").strip()
        if not query:
            return {"success": False, "error": "Search query must not be empty"}
        api_key = get_provider_env(API_KEY_ENV)
        if not api_key:
            return {"success": False, "error": _missing_key_error()}
        location, location_error = self._location()
        if location_error:
            return {"success": False, "error": location_error}
        try:
            count = max(1, min(int(limit), MAX_SEARCH_RESULTS))
        except (TypeError, ValueError):
            count = 5
        try:
            hits = search_web(api_key, query, count, location)
        except OxylabsApiError as exc:
            logger.warning("Oxylabs search failed (HTTP %s)", exc.status)
            return {"success": False, "error": str(exc)}
        logger.info("Oxylabs search returned %d result(s)", len(hits))
        return {"success": True, "data": {"web": hits}}

    async def extract(self, urls: list[str], **kwargs: Any) -> list[dict[str, Any]]:
        """Fetch each URL as Markdown, in parallel, keeping the input order and per-URL errors.

        Hermes has already refused private and internal addresses before calling this.
        """
        if not urls:
            return []
        api_key = get_provider_env(API_KEY_ENV)
        if not api_key:
            return [{"url": url, "title": "", "content": "", "error": _missing_key_error()} for url in urls]
        render_js = self._settings("render_js", False) is True
        deadline = time.monotonic() + EXTRACT_DEADLINE_SECONDS

        async def extract_one(client: httpx.AsyncClient, url: str) -> dict[str, Any]:
            try:
                markdown, status = await scrape_page(client, api_key, url, render_js=render_js, deadline=deadline)
            except OxylabsApiError as exc:
                return {"url": url, "title": "", "content": "", "error": str(exc)}
            if status is not None and not 200 <= status < 300:
                return {"url": url, "title": "", "content": "", "error": f"{url} returned HTTP {status}."}
            if not markdown:
                return {"url": url, "title": "", "content": "", "error": f"No content returned for {url}."}
            title = _title_from_markdown(markdown)
            return {
                "url": url,
                "title": title,
                "content": markdown,
                "raw_content": markdown,
                "metadata": {"sourceURL": url, "title": title, "statusCode": status},
            }

        async with httpx.AsyncClient() as client:
            return list(await asyncio.gather(*(extract_one(client, url) for url in urls)))

    def get_setup_schema(self) -> dict[str, Any]:
        return {
            "name": "Oxylabs Web API",
            "badge": "paid",
            "tag": "Google search and page extraction, including JavaScript-heavy and bot-protected pages.",
            "env_vars": [{"key": API_KEY_ENV, "prompt": "Oxylabs Web API key", "url": SIGNUP_URL}],
        }
