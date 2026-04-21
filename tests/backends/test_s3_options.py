"""S3 / S3-PyArrow shared s3fs options tests -- covers S3-026, S3PA-026.

Unit-level; does not connect to S3. Requires s3fs and botocore.
"""

from __future__ import annotations

import pytest

pytest.importorskip("s3fs", reason="s3fs not installed")
pytest.importorskip("botocore", reason="botocore not installed")


@pytest.mark.parametrize(
    "backend_cls",
    [
        pytest.param(
            "remote_store.backends._s3:S3Backend",
            id="s3",
            marks=pytest.mark.spec("S3-026"),
        ),
        pytest.param(
            "remote_store.backends._s3_pyarrow:S3PyArrowBackend",
            id="s3-pyarrow",
            marks=pytest.mark.spec("S3PA-026"),
        ),
    ],
)
class TestConfigKwargsRetryCollision:
    """BUG-178: config_kwargs + RetryPolicy must not collide on aiobotocore config=."""

    def _load_backend_cls(self, dotted: str) -> type:
        module_path, cls_name = dotted.split(":")
        import importlib

        mod = importlib.import_module(module_path)
        return getattr(mod, cls_name)

    def test_config_kwargs_not_forwarded_to_s3fs(self, backend_cls: str) -> None:
        """BUG-178: top-level config_kwargs must be consumed before s3fs sees the opts dict.

        On the bug: s3fs turns config_kwargs into config= for aiobotocore.create_client(),
        which then collides with the retry-derived client_kwargs["config"], giving
        TypeError('got multiple values for keyword argument ''config''').
        """
        from unittest.mock import patch

        import botocore.config

        from remote_store._config import RetryPolicy

        cls = self._load_backend_cls(backend_cls)
        backend = cls(
            bucket="mybucket",
            client_options={
                "config_kwargs": {
                    "connect_timeout": 10,
                    "retries": {"max_attempts": 3, "mode": "standard"},
                },
            },
            retry=RetryPolicy(max_attempts=5),
        )
        try:
            with patch("s3fs.S3FileSystem") as mock_cls:
                _ = backend._s3fs

            call_kwargs = mock_cls.call_args.kwargs
            # BUG-178: config_kwargs must be consumed (folded into client_kwargs["config"])
            # before reaching s3fs, not forwarded as a top-level kwarg.
            assert "config_kwargs" not in call_kwargs, (
                "config_kwargs must not reach s3fs.S3FileSystem — "
                "it collides with client_kwargs['config'] inside aiobotocore"
            )
            # The merged Config must be in client_kwargs["config"]
            assert "client_kwargs" in call_kwargs
            merged = call_kwargs["client_kwargs"]["config"]
            assert isinstance(merged, botocore.config.Config)
            assert merged.connect_timeout == 10
            assert merged.retries["max_attempts"] == 5
        finally:
            backend.close()

    def test_existing_client_kwargs_config_wins_over_config_kwargs(self, backend_cls: str) -> None:
        """Invariant 2: a pre-existing client_kwargs["config"] wins over config_kwargs on conflicts.

        When the caller passes both client_kwargs={"config": Config(...)} and
        config_kwargs={...}, the existing Config object takes precedence on any
        overlapping fields.
        """
        from unittest.mock import patch

        import botocore.config

        cls = self._load_backend_cls(backend_cls)
        backend = cls(
            bucket="mybucket",
            client_options={
                "config_kwargs": {"connect_timeout": 7},
                "client_kwargs": {
                    "config": botocore.config.Config(retries={"max_attempts": 99}, connect_timeout=20),
                },
            },
        )
        try:
            with patch("s3fs.S3FileSystem") as mock_cls:
                _ = backend._s3fs

            call_kwargs = mock_cls.call_args.kwargs
            assert "config_kwargs" not in call_kwargs
            merged = call_kwargs["client_kwargs"]["config"]
            assert isinstance(merged, botocore.config.Config)
            # existing client_kwargs["config"] wins on conflict: 20, not 7
            assert merged.connect_timeout == 20
            # non-overlapping fields from the existing Config survive the merge
            assert merged.retries["max_attempts"] == 99
        finally:
            backend.close()
