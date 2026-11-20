"""End-to-end check inside a real Hermes install (run by .github/workflows/hermes-e2e.yml).

Runs with Hermes's own Python after the plugin is installed and selected, and calls Hermes's
web_search / web_extract tools the way the agent does. Needs OXYLABS_WEB_API_KEY.
"""

from __future__ import annotations

import asyncio
import json
import sys

from agent import web_search_registry
from tools.web_tools import _ensure_web_plugins_loaded, web_extract_tool, web_search_tool


def check(condition: bool, message: str) -> None:
    print(("ok   " if condition else "FAIL ") + message)
    if not condition:
        sys.exit(1)


def main() -> None:
    _ensure_web_plugins_loaded()
    search_provider = web_search_registry.get_active_search_provider()
    extract_provider = web_search_registry.get_active_extract_provider()
    check(search_provider is not None and search_provider.name == "oxylabs", "web_search backend is oxylabs")
    check(extract_provider is not None and extract_provider.name == "oxylabs", "web_extract backend is oxylabs")
    check(search_provider._location() == ("DE", None), "location setting reaches the plugin")

    search = json.loads(web_search_tool("oxylabs web api", limit=3))
    hits = search.get("data", {}).get("web", [])
    check(search.get("success") is True and 0 < len(hits) <= 3, f"web_search returned {len(hits)} result(s)")

    extract = json.loads(asyncio.run(web_extract_tool(["https://example.com", "http://127.0.0.1:8080/"])))
    public, private = extract["results"]
    check(
        not public.get("error") and "documentation examples" in public.get("content", ""),
        "web_extract read example.com",
    )
    check("private or internal" in (private.get("error") or ""), "Hermes blocked the private URL")


if __name__ == "__main__":
    main()
