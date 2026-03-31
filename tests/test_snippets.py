"""Tests for documentation code snippets.

Ensures that every snippet script in ``examples/snippets/`` executes
successfully, keeping docs code blocks in sync with the actual API.

See: ID-057 (single-source snippets).
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.os_sensitive


class TestHomepageSnippets:
    """Snippets used on the docs landing page (index.md)."""

    @pytest.mark.spec("ID-057")
    def test_homepage_demo(self) -> None:
        from examples.snippets.homepage import demo

        result = demo()
        assert result is None


class TestCoreOperationsSnippets:
    """Snippets used in guides and README."""

    @pytest.mark.spec("ID-057")
    def test_core_operations_demo(self) -> None:
        from examples.snippets.core_operations import demo

        result = demo()
        assert result is None


class TestDagsterGuideSnippets:
    """Snippets used in the Dagster Integration guide."""

    @pytest.mark.spec("DAG-020")
    def test_dagster_guide_demo(self) -> None:
        pytest.importorskip("dagster")

        from examples.snippets.dagster_guide import demo

        result = demo()
        assert result is None
