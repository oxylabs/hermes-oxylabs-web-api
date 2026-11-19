"""Calls the real Oxylabs Web API. Run with `pytest -m live`; needs OXYLABS_WEB_API_KEY."""

from __future__ import annotations

import pytest
from conftest import LIVE_API_KEY

pytestmark = [pytest.mark.live, pytest.mark.skipif(not LIVE_API_KEY, reason="OXYLABS_WEB_API_KEY is not set")]


@pytest.fixture
def live_provider(fake_hermes, monkeypatch: pytest.MonkeyPatch):
    del fake_hermes
    monkeypatch.setenv("OXYLABS_WEB_API_KEY", LIVE_API_KEY)
    from hermes_oxylabs_web_api.provider import OxylabsWebSearchProvider

    return OxylabsWebSearchProvider(lambda key, default=None: {"location": "DE"}.get(key, default))


def test_live_search(live_provider) -> None:
    result = live_provider.search("oxylabs web api", limit=3)
    assert result["success"] is True, result.get("error")
    assert 0 < len(result["data"]["web"]) <= 3


async def test_live_extract(live_provider) -> None:
    docs = await live_provider.extract(["https://example.com"])
    assert "error" not in docs[0], docs[0].get("error")
    assert "documentation examples" in docs[0]["content"]


def test_live_bad_key(live_provider, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OXYLABS_WEB_API_KEY", "not-a-real-key")
    result = live_provider.search("rejected key check")
    assert result["success"] is False
    assert "rejected the API key (401)" in result["error"]
