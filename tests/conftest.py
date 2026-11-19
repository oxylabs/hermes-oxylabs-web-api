from __future__ import annotations

import importlib
import json
import os
import sys
import types
from collections.abc import Callable

import httpx
import pytest

PACKAGE = "hermes_oxylabs_web_api"
# The real key, if any, for the live tests; fake_hermes clears the variable so unit tests start clean.
LIVE_API_KEY = os.getenv("OXYLABS_WEB_API_KEY", "")


@pytest.fixture
def fake_hermes(monkeypatch: pytest.MonkeyPatch):
    """Install a minimal stand-in for Hermes's public web-provider module."""
    for module_name in list(sys.modules):
        if module_name == PACKAGE or module_name.startswith(f"{PACKAGE}."):
            sys.modules.pop(module_name)

    agent_module = types.ModuleType("agent")
    web_search_provider_module = types.ModuleType("agent.web_search_provider")

    class WebSearchProvider:
        pass

    def get_provider_env(name: str) -> str:
        return os.getenv(name, "").strip()

    web_search_provider_module.WebSearchProvider = WebSearchProvider
    web_search_provider_module.get_provider_env = get_provider_env
    agent_module.web_search_provider = web_search_provider_module
    monkeypatch.setitem(sys.modules, "agent", agent_module)
    monkeypatch.setitem(sys.modules, "agent.web_search_provider", web_search_provider_module)
    monkeypatch.delenv("OXYLABS_WEB_API_KEY", raising=False)
    return WebSearchProvider


@pytest.fixture
def client_module(fake_hermes):
    del fake_hermes
    return importlib.import_module(f"{PACKAGE}.client")


@pytest.fixture
def provider_module(fake_hermes):
    del fake_hermes
    return importlib.import_module(f"{PACKAGE}.provider")


Handler = Callable[[httpx.Request], httpx.Response]


@pytest.fixture
def fake_api(monkeypatch: pytest.MonkeyPatch):
    """Route every httpx call to a handler; returns the list of requests made."""
    requests: list[httpx.Request] = []
    state: dict[str, Handler] = {}
    transport = httpx.MockTransport(lambda request: (requests.append(request), state["handler"](request))[1])
    real_async_client = httpx.AsyncClient

    def fake_post(url: str, **kwargs) -> httpx.Response:
        with httpx.Client(transport=transport) as client:
            return client.post(url, **kwargs)

    monkeypatch.setattr(httpx, "post", fake_post)
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: real_async_client(transport=transport, **kwargs))

    def use(handler: Handler) -> list[httpx.Request]:
        state["handler"] = handler
        return requests

    return use


def json_response(status: int, body: object) -> httpx.Response:
    return httpx.Response(status, content=json.dumps(body).encode(), headers={"content-type": "application/json"})


def scrape_result(markdown: str, code: int = 200) -> dict:
    return {"results": [{"markdown": markdown, "metadata": {"statuses": {"http_request": {"code": code}}}}]}
