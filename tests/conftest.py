"""Shared test fixtures and marker registration."""

from __future__ import annotations


def pytest_configure(config: object) -> None:
    """Register custom markers."""
    import pytest

    if isinstance(config, pytest.Config):
        config.addinivalue_line("markers", "spec(id): links test to a spec section ID")
        config.addinivalue_line("markers", "integration: requires external services")
