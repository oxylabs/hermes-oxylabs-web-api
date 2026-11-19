from __future__ import annotations

import importlib.util
import shutil
import sys
import tomllib
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


class Context:
    def __init__(self) -> None:
        self.providers = []

    def register_web_search_provider(self, provider) -> None:
        self.providers.append(provider)

    def get_config(self, key, default=None):
        return {"location": "US"}.get(key, default)


def test_pip_entry_point_registers_the_provider(fake_hermes) -> None:
    del fake_hermes
    entry_points = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["entry-points"]
    assert entry_points["hermes_agent.plugins"] == {"oxylabs-web-api": "hermes_oxylabs_web_api"}

    import hermes_oxylabs_web_api

    context = Context()
    hermes_oxylabs_web_api.register(context)
    assert [provider.name for provider in context.providers] == ["oxylabs"]
    assert context.providers[0]._location() == ("US", None)


def test_git_checkout_loads_without_the_pypi_package(
    fake_hermes, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    del fake_hermes
    plugin_dir = tmp_path / "plugins" / "oxylabs-web-api"
    plugin_dir.mkdir(parents=True)
    shutil.copy2(ROOT / "__init__.py", plugin_dir / "__init__.py")
    shutil.copytree(
        ROOT / "src" / "hermes_oxylabs_web_api",
        plugin_dir / "src" / "hermes_oxylabs_web_api",
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    # A Git install must work even when the PyPI module is not importable.
    monkeypatch.setitem(sys.modules, "hermes_oxylabs_web_api", None)
    namespace = types.ModuleType("hermes_plugins")
    namespace.__path__ = []
    monkeypatch.setitem(sys.modules, "hermes_plugins", namespace)
    module_name = "hermes_plugins.oxylabs_web_api"
    spec = importlib.util.spec_from_file_location(
        module_name, plugin_dir / "__init__.py", submodule_search_locations=[str(plugin_dir)]
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, module_name, module)
    spec.loader.exec_module(module)

    context = Context()
    module.register(context)
    assert [provider.name for provider in context.providers] == ["oxylabs"]
    assert type(context.providers[0]).__module__ == f"{module_name}.src.hermes_oxylabs_web_api.provider"
