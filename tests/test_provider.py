from __future__ import annotations

import json

import httpx
import pytest
from conftest import json_response, scrape_result


def settings(values: dict):
    return lambda key, default=None: values.get(key, default)


def test_available_only_with_a_key(provider_module, monkeypatch: pytest.MonkeyPatch) -> None:
    provider = provider_module.OxylabsWebSearchProvider()
    assert provider.is_available() is False
    monkeypatch.setenv("OXYLABS_WEB_API_KEY", "test-key")
    assert provider.is_available() is True
    assert provider.name == "oxylabs"
    assert provider.supports_search() and provider.supports_extract()


def test_search_without_a_key_explains_setup(provider_module) -> None:
    result = provider_module.OxylabsWebSearchProvider().search("q")
    assert result["success"] is False
    assert "OXYLABS_WEB_API_KEY is not set" in result["error"]


def test_search_maps_results_and_sends_tracking_header(
    provider_module, fake_api, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OXYLABS_WEB_API_KEY", "test-key")
    requests = fake_api(
        lambda request: json_response(
            200,
            {
                "results": [
                    {
                        "title": "Example",
                        "url": "https://example.com/a",
                        "outline": ["one", "two"],
                        "metadata": {"position": 1},
                    }
                ]
            },
        )
    )
    provider = provider_module.OxylabsWebSearchProvider(settings({"location": "de"}))
    result = provider.search("espresso", limit=50)

    assert result == {
        "success": True,
        "data": {
            "web": [{"title": "Example", "url": "https://example.com/a", "description": "one … two", "position": 1}]
        },
    }
    request = requests[0]
    assert request.url == "https://webapi.oxylabs.io/v1/search"
    assert json.loads(request.content) == {"query": "espresso", "max_results": 20, "location": "DE"}
    assert request.headers["authorization"] == "Bearer test-key"
    assert request.headers["x-oxylabs-sdk"].startswith("oxylabs-web-api-hermes/")


def test_search_rejects_a_location_that_is_not_a_country_code(
    provider_module, fake_api, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OXYLABS_WEB_API_KEY", "test-key")
    requests = fake_api(lambda request: json_response(200, {"results": []}))
    result = provider_module.OxylabsWebSearchProvider(settings({"location": "Germany"})).search("q")
    assert result["success"] is False
    assert "two-letter country code" in result["error"]
    assert requests == []


def test_search_reports_api_errors(provider_module, fake_api, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OXYLABS_WEB_API_KEY", "wrong-key")
    fake_api(lambda request: httpx.Response(401))
    result = provider_module.OxylabsWebSearchProvider().search("q")
    assert result["success"] is False
    assert "rejected the API key (401)" in result["error"]
    assert "wrong-key" not in result["error"]


async def test_extract_returns_documents_in_order(provider_module, fake_api, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OXYLABS_WEB_API_KEY", "test-key")

    def handler(request: httpx.Request) -> httpx.Response:
        url = json.loads(request.content)["url"]
        if url.endswith("/missing"):
            return json_response(200, scrape_result("Not found", code=404))
        return json_response(200, scrape_result(f"# Title of {url}\n\nBody"))

    requests = fake_api(handler)
    provider = provider_module.OxylabsWebSearchProvider(settings({"render_js": True}))
    docs = await provider.extract(["https://example.com/a", "https://example.com/missing"])

    assert docs[0]["url"] == "https://example.com/a"
    assert docs[0]["title"] == "Title of https://example.com/a"
    assert docs[0]["content"] == docs[0]["raw_content"] == "# Title of https://example.com/a\n\nBody"
    assert docs[0]["metadata"]["statusCode"] == 200
    assert docs[1]["error"] == "https://example.com/missing returned HTTP 404."
    assert all(json.loads(r.content)["run_js"] is True for r in requests)
    assert all(json.loads(r.content)["output"] == ["markdown"] for r in requests)


async def test_extract_falls_back_to_async_when_the_page_is_slow(
    provider_module, client_module, fake_api, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OXYLABS_WEB_API_KEY", "test-key")
    monkeypatch.setattr(client_module, "POLL_INTERVAL_SECONDS", 0)
    polls = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/scrape":
            return json_response(504, {"title": "REQUEST_FAILED_SCRAPE_TIMEOUT"})
        if request.url.path == "/v1/async/scrape":
            return json_response(202, {"metadata": {"request_id": "abc"}})
        polls.append(request.url.path)
        if len(polls) == 1:
            return json_response(200, {"state": "pending"})
        return json_response(200, scrape_result("# Slow page"))

    fake_api(handler)
    docs = await provider_module.OxylabsWebSearchProvider().extract(["https://example.com/slow"])
    assert docs[0]["content"] == "# Slow page"
    assert polls == ["/v1/async/scrape/abc", "/v1/async/scrape/abc"]


async def test_extract_without_a_key_fails_each_url(provider_module) -> None:
    docs = await provider_module.OxylabsWebSearchProvider().extract(["https://example.com"])
    assert docs[0]["url"] == "https://example.com"
    assert "OXYLABS_WEB_API_KEY is not set" in docs[0]["error"]
