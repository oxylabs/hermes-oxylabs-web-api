"""HTTP client for the Oxylabs Web API (`/v1/search`, `/v1/scrape`, `/v1/async/scrape`)."""

from __future__ import annotations

import asyncio
import platform
import time
from typing import Any

import httpx

from . import __version__

API_BASE_URL = "https://webapi.oxylabs.io"
API_KEY_ENV = "OXYLABS_WEB_API_KEY"
MAX_SEARCH_RESULTS = 20
SEARCH_TIMEOUT_SECONDS = 30.0
SYNC_SCRAPE_TIMEOUT_SECONDS = 60.0
POLL_INTERVAL_SECONDS = 3.0

_ERROR_DETAIL_MAX_CHARS = 300
_SCRAPE_TIMEOUT_TITLE = "REQUEST_FAILED_SCRAPE_TIMEOUT"


class OxylabsApiError(RuntimeError):
    """A Web API error with a message safe to show the agent. It never contains the API key."""

    def __init__(self, message: str, status: int, request_id: str | None = None) -> None:
        super().__init__(message)
        self.status = status
        self.request_id = request_id


def sdk_header() -> str:
    """The `x-oxylabs-sdk` value Oxylabs uses to count usage per integration."""
    return f"oxylabs-web-api-hermes/{__version__} (hermes; python {platform.python_version()})"


def _headers(api_key: str) -> dict[str, str]:
    return {
        "Accept": "application/json",
        "Authorization": f"Bearer {api_key}",
        "x-oxylabs-sdk": sdk_header(),
    }


def _json_body(response: httpx.Response) -> dict[str, Any] | None:
    try:
        body = response.json()
    except ValueError:
        return None
    return body if isinstance(body, dict) else None


def _request_id(body: dict[str, Any] | None) -> str | None:
    if not body:
        return None
    metadata = body.get("metadata")
    value = metadata.get("request_id") if isinstance(metadata, dict) else None
    value = value if value is not None else body.get("request_id")
    return str(value) if isinstance(value, (str, int)) else None


def describe_api_error(status: int, body: dict[str, Any] | None) -> str:
    """Turn a failed response into a message the agent (and the user) can act on."""
    request_id = _request_id(body)
    suffix = f" (request_id {request_id})" if request_id else ""
    if status == 401:
        return f"Oxylabs Web API rejected the API key (401). Check {API_KEY_ENV}."
    if status == 403:
        return f"Oxylabs Web API refused the request (403): the account has no access to this feature{suffix}."
    title = body.get("title") if body else None
    if status == 429 and title == "QUOTA_EXCEEDED":
        return "Oxylabs Web API quota is used up (429 QUOTA_EXCEEDED). Top up the plan in the Oxylabs dashboard."
    errors = body.get("errors") if body else None
    field_errors = "; ".join(
        f"{str(entry.get('pointer', '')).removeprefix('#/')}: {entry.get('detail', '')}"
        for entry in (errors if isinstance(errors, list) else [])
        if isinstance(entry, dict)
    )
    detail = field_errors or (body.get("detail") if body and isinstance(body.get("detail"), str) else "")
    message = f"Oxylabs Web API error {status} {title if isinstance(title, str) else 'request failed'}"
    if detail:
        message += f": {detail}"
    if len(message) > _ERROR_DETAIL_MAX_CHARS:
        message = message[:_ERROR_DETAIL_MAX_CHARS] + "…"
    return message + suffix


def _ensure_ok(response: httpx.Response) -> dict[str, Any]:
    body = _json_body(response)
    if 200 <= response.status_code < 300 and body is not None:
        return body
    raise OxylabsApiError(describe_api_error(response.status_code, body), response.status_code, _request_id(body))


def search_web(api_key: str, query: str, limit: int, location: str | None = None) -> list[dict[str, Any]]:
    """`POST /v1/search`: organic results, each with a short outline of the page."""
    payload: dict[str, Any] = {"query": query, "max_results": limit}
    if location:
        payload["location"] = location
    try:
        response = httpx.post(
            f"{API_BASE_URL}/v1/search", json=payload, headers=_headers(api_key), timeout=SEARCH_TIMEOUT_SECONDS
        )
    except httpx.RequestError as exc:
        raise OxylabsApiError(f"Could not reach the Oxylabs Web API ({type(exc).__name__}).", 0) from None
    data = _ensure_ok(response)
    results = data.get("results")
    hits = []
    for entry in results if isinstance(results, list) else []:
        if not isinstance(entry, dict):
            continue
        outline = entry.get("outline")
        metadata = entry.get("metadata")
        position = metadata.get("position") if isinstance(metadata, dict) else None
        hits.append(
            {
                "title": str(entry.get("title") or ""),
                "url": str(entry.get("url") or ""),
                "description": " … ".join(line for line in outline if isinstance(line, str))
                if isinstance(outline, list)
                else "",
                "position": position if isinstance(position, int) else len(hits) + 1,
            }
        )
    return hits


def _read_page(data: dict[str, Any]) -> tuple[str, int | None]:
    results = data.get("results")
    first = results[0] if isinstance(results, list) and results and isinstance(results[0], dict) else {}
    markdown = first.get("markdown")
    metadata = first.get("metadata")
    statuses = metadata.get("statuses") if isinstance(metadata, dict) else None
    http_request = statuses.get("http_request") if isinstance(statuses, dict) else None
    code = http_request.get("code") if isinstance(http_request, dict) else None
    return (markdown if isinstance(markdown, str) else ""), (code if isinstance(code, int) else None)


async def scrape_page(
    client: httpx.AsyncClient, api_key: str, url: str, *, render_js: bool, deadline: float
) -> tuple[str, int | None]:
    """`POST /v1/scrape` for one page as Markdown; returns ``(markdown, target HTTP status)``.

    Most pages finish inside the synchronous call. When it times out, the same request is queued on
    `/v1/async/scrape` and polled until ``deadline`` (a ``time.monotonic()`` value), instead of being
    resent synchronously.
    """
    payload: dict[str, Any] = {"url": url, "output": ["markdown"]}
    if render_js:
        payload["run_js"] = True
    headers = _headers(api_key)

    def remaining() -> float:
        return max(1.0, deadline - time.monotonic())

    try:
        response = await client.post(
            f"{API_BASE_URL}/v1/scrape",
            json=payload,
            headers=headers,
            timeout=min(SYNC_SCRAPE_TIMEOUT_SECONDS, remaining()),
        )
        body = _json_body(response)
        timed_out = response.status_code == 504 or (body or {}).get("title") == _SCRAPE_TIMEOUT_TITLE
        if not timed_out:
            return _read_page(_ensure_ok(response))
    except httpx.TimeoutException:
        pass
    except httpx.RequestError as exc:
        raise OxylabsApiError(f"Could not reach the Oxylabs Web API ({type(exc).__name__}).", 0) from None

    try:
        queued = _ensure_ok(
            await client.post(f"{API_BASE_URL}/v1/async/scrape", json=payload, headers=headers, timeout=remaining())
        )
        request_id = _request_id(queued)
        if not request_id:
            raise OxylabsApiError("Oxylabs Web API queued the scrape but returned no request_id.", 502)
        while True:
            if time.monotonic() + POLL_INTERVAL_SECONDS > deadline:
                raise OxylabsApiError(
                    f"Oxylabs Web API did not finish scraping {url} in time (request_id {request_id}). Try again.",
                    504,
                    request_id,
                )
            await asyncio.sleep(POLL_INTERVAL_SECONDS)
            polled = await client.get(
                f"{API_BASE_URL}/v1/async/scrape/{request_id}", headers=headers, timeout=remaining()
            )
            if (_json_body(polled) or {}).get("state") == "pending":
                continue
            return _read_page(_ensure_ok(polled))
    except httpx.RequestError as exc:
        raise OxylabsApiError(f"Could not reach the Oxylabs Web API ({type(exc).__name__}).", 0) from None
