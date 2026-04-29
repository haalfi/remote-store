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
    """BUG-178 / BUG-185: config never reaches s3fs via ``client_kwargs['config']``.

    s3fs ``set_session`` always passes ``config=AioConfig(**self.config_kwargs)``
    to ``aiobotocore.create_client()``; any ``client_kwargs['config']`` we add
    on top would duplicate that keyword and raise ``TypeError`` at call time.
    The shared builder must therefore route every ``Config`` source (caller's
    ``config_kwargs``, caller's pre-built ``client_kwargs['config']``, retry
    policy) through a single merged ``opts['config_kwargs']`` dict.
    """

    def _load_backend_cls(self, dotted: str) -> type:
        module_path, cls_name = dotted.split(":")
        import importlib

        mod = importlib.import_module(module_path)
        return getattr(mod, cls_name)

    def test_config_kwargs_routed_to_s3fs_config_kwargs(self, backend_cls: str) -> None:
        """BUG-185: config_kwargs + RetryPolicy must route through opts['config_kwargs'].

        s3fs builds ``AioConfig(**self.config_kwargs)`` itself and passes it as
        ``config=`` to ``aiobotocore.create_client``; setting
        ``client_kwargs['config']`` causes ``got multiple values for keyword
        argument 'config'``. The merged values therefore land in
        ``call_kwargs['config_kwargs']``, and ``client_kwargs`` (if present)
        must not contain a ``config`` key.
        """
        from unittest.mock import patch

        from remote_store._config import RetryPolicy

        cls = self._load_backend_cls(backend_cls)
        backend = cls(
            bucket="mybucket",
            client_options={
                "config_kwargs": {
                    "connect_timeout": 10,
                    "retries": {"max_attempts": 3, "mode": "standard"},
                    "s3": {"addressing_style": "path"},
                    "proxies": {"http": None, "https": None},
                },
            },
            retry=RetryPolicy(max_attempts=5),
        )
        try:
            with patch("s3fs.S3FileSystem") as mock_cls:
                _ = backend._s3fs

            call_kwargs = mock_cls.call_args.kwargs
            assert "client_kwargs" not in call_kwargs or "config" not in call_kwargs["client_kwargs"], (
                "client_kwargs['config'] must not be set — it duplicates the "
                "config= argument s3fs passes to aiobotocore.create_client()"
            )
            assert "config_kwargs" in call_kwargs
            merged = call_kwargs["config_kwargs"]
            assert isinstance(merged, dict)
            assert merged["connect_timeout"] == 10
            # retry policy wins on conflicts
            assert merged["retries"]["max_attempts"] == 5
            assert merged["retries"]["mode"] == "standard"
            # non-retry fields survive
            assert merged["s3"] == {"addressing_style": "path"}
            assert merged["proxies"] == {"http": None, "https": None}
        finally:
            backend.close()

    def test_config_kwargs_only_no_retry_policy(self, backend_cls: str) -> None:
        """BUG-185: plain ``config_kwargs`` (no RetryPolicy) also must not collide.

        Reproduces the scenario from the user report: only ``config_kwargs`` is
        set, no ``retry=``. The merged dict still flows through
        ``opts['config_kwargs']``; ``client_kwargs['config']`` is never set.
        """
        from unittest.mock import patch

        cls = self._load_backend_cls(backend_cls)
        backend = cls(
            bucket="mybucket",
            client_options={
                "config_kwargs": {
                    "connect_timeout": 3.0,
                    "read_timeout": 10.0,
                    "retries": {"max_attempts": 3, "mode": "standard"},
                    "s3": {"addressing_style": "path"},
                    "proxies": {"http": None, "https": None},
                },
            },
        )
        try:
            with patch("s3fs.S3FileSystem") as mock_cls:
                _ = backend._s3fs

            call_kwargs = mock_cls.call_args.kwargs
            assert "client_kwargs" not in call_kwargs or "config" not in call_kwargs["client_kwargs"]
            merged = call_kwargs["config_kwargs"]
            assert merged["connect_timeout"] == 3.0
            assert merged["read_timeout"] == 10.0
            assert merged["retries"] == {"max_attempts": 3, "mode": "standard"}
            assert merged["s3"] == {"addressing_style": "path"}
            assert merged["proxies"] == {"http": None, "https": None}
        finally:
            backend.close()

    def test_existing_client_kwargs_config_wins_over_config_kwargs(self, backend_cls: str) -> None:
        """Invariant 2: a pre-existing ``client_kwargs['config']`` wins over ``config_kwargs``.

        When the caller passes both ``client_kwargs={'config': Config(...)}``
        and ``config_kwargs={...}``, the pre-built Config takes precedence on
        overlapping fields. The merged result still leaves s3fs as
        ``opts['config_kwargs']`` (a dict) — not as ``client_kwargs['config']``,
        which would collide with s3fs's own ``config=`` argument.
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
            assert "client_kwargs" not in call_kwargs or "config" not in call_kwargs["client_kwargs"]
            merged = call_kwargs["config_kwargs"]
            assert isinstance(merged, dict)
            # existing client_kwargs["config"] wins on conflict: 20, not 7
            assert merged["connect_timeout"] == 20
            # non-overlapping fields from the existing Config survive the merge
            assert merged["retries"]["max_attempts"] == 99
        finally:
            backend.close()
