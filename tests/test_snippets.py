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


class TestAsyncSyncBridgesSnippets:
    """Snippets used in the Async/Sync Bridges guide."""

    @pytest.mark.spec("ID-143c")
    def test_async_sync_bridges_demo(self) -> None:
        from examples.snippets.async_sync_bridges import demo

        result = demo()
        assert result is None


class TestWriteIntegritySnippets:
    """Snippets used in the Write Integrity guide."""

    @pytest.mark.spec("ID-148")
    def test_write_integrity_demo(self) -> None:
        from examples.snippets.write_integrity import demo

        result = demo()
        assert result is None


class TestAsyncWriteIntegritySnippets:
    """Snippets used in the async section of the Write Integrity guide."""

    @pytest.mark.spec("EW-001")
    def test_async_write_integrity_demo(self) -> None:
        import asyncio

        from examples.snippets.write_integrity_async import demo

        result = asyncio.run(demo())
        assert result is None


class TestS3BotocoreTuningSnippets:
    """Snippets used in the S3 backend guide's Botocore client tuning section."""

    @pytest.mark.spec("S3-026")
    def test_s3_botocore_tuning_demo(self) -> None:
        # Snippet imports S3Backend, which imports s3fs at module load.
        # Skip cleanly when the s3 extra isn't installed (matches the guard
        # used in tests/backends/test_s3_options.py and test_s3_shared.py).
        pytest.importorskip("s3fs", reason="s3fs not installed")
        pytest.importorskip("botocore", reason="botocore not installed")

        from examples.snippets.s3_botocore_tuning import demo

        result = demo()
        assert result is None
