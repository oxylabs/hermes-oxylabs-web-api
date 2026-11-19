from __future__ import annotations

import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "src" / "hermes_oxylabs_web_api" / "plugin.yaml"


def test_versions_match(client_module) -> None:
    from hermes_oxylabs_web_api import __version__

    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
    manifest = re.search(r"^version: (\S+)$", MANIFEST.read_text(), re.M)
    assert manifest is not None
    assert __version__ == pyproject == manifest.group(1)


def test_root_manifest_matches_package_manifest() -> None:
    assert (ROOT / "plugin.yaml").read_text() == MANIFEST.read_text()


def test_sdk_header_matches_the_oxylabs_allowlist(client_module) -> None:
    pattern = r"oxylabs-web-api-hermes/\d+\.\d+\.\d+ \(hermes; python [\d.]+\S*\)"
    assert re.fullmatch(pattern, client_module.sdk_header())


def test_describe_rejected_key(client_module) -> None:
    assert "rejected the API key" in client_module.describe_api_error(401, None)


def test_describe_field_errors_and_request_id(client_module) -> None:
    message = client_module.describe_api_error(
        400,
        {
            "title": "VALIDATION_ERROR",
            "detail": "1 request field is invalid",
            "errors": [{"pointer": "#/max_results", "detail": "Input should be less than or equal to 20"}],
            "metadata": {"request_id": "123"},
        },
    )
    assert message == (
        "Oxylabs Web API error 400 VALIDATION_ERROR: max_results: Input should be less than or equal to 20"
        " (request_id 123)"
    )


def test_describe_spent_quota(client_module) -> None:
    assert "quota is used up" in client_module.describe_api_error(429, {"title": "QUOTA_EXCEEDED"})
