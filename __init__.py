"""Hermes directory-plugin entry point for Git installs and the plugin catalog."""

from __future__ import annotations


def register(ctx) -> None:
    """Register the implementation shipped in this checkout."""
    from .src.hermes_oxylabs_web_api import register as register_plugin

    register_plugin(ctx)
