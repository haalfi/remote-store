"""S3 / S3-PyArrow shared s3fs options tests -- covers S3-026, S3PA-026.

Unit-level; does not connect to S3. Requires s3fs and botocore.
"""

from __future__ import annotations

import logging

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
            assert isinstance(merged, dict)
            assert merged["connect_timeout"] == 3.0
            assert merged["read_timeout"] == 10.0
            assert merged["retries"] == {"max_attempts": 3, "mode": "standard"}
            assert merged["s3"] == {"addressing_style": "path"}
            assert merged["proxies"] == {"http": None, "https": None}
        finally:
            backend.close()

    def test_client_kwargs_config_is_rejected(self, backend_cls: str) -> None:
        """S3-026: caller-supplied ``client_kwargs['config']`` raises ``ValueError``.

        Silent rewriting hid both BUG-178 and BUG-185 because the test
        boundary was the kwargs handed to ``s3fs.S3FileSystem`` rather than
        what ``aiobotocore.create_client()`` actually receives. The
        supported channel is ``client_options['config_kwargs']`` (a dict);
        any pre-built ``botocore.config.Config`` in ``client_kwargs`` is a
        bug, so the builder fails fast.
        """
        import botocore.config

        cls = self._load_backend_cls(backend_cls)
        backend = cls(
            bucket="mybucket",
            client_options={
                "client_kwargs": {
                    "config": botocore.config.Config(connect_timeout=20),
                },
            },
        )
        try:
            with pytest.raises(ValueError, match="config_kwargs"):
                _ = backend._s3fs
        finally:
            backend.close()

    def test_retry_overrides_caller_retries_emits_warning(self, backend_cls: str) -> None:
        """S3-026: dropping caller-supplied retry knobs is observable.

        When ``retry=RetryPolicy(...)`` is passed alongside non-empty
        ``config_kwargs['retries']``, the builder replaces the retries dict
        wholesale. Silent rewriting hid BUG-178 and BUG-185; emit a
        ``log.warning`` enumerating the dropped keys so the next
        mis-configuration is a one-line search instead of a runtime
        surprise.
        """
        from unittest.mock import patch

        from remote_store._config import RetryPolicy

        cls = self._load_backend_cls(backend_cls)
        backend = cls(
            bucket="mybucket",
            client_options={
                "config_kwargs": {
                    "retries": {"max_attempts": 3, "mode": "adaptive", "total_max_attempts": 9},
                },
            },
            retry=RetryPolicy(max_attempts=5),
        )
        try:
            with patch("s3fs.S3FileSystem"), self._caplog(logging.WARNING) as records:
                _ = backend._s3fs
            messages = [r.getMessage() for r in records]
            matched = [m for m in messages if "config_kwargs['retries']" in m and "dropped" in m]
            assert matched, f"expected drop-warning; got {messages!r}"
            # Both non-max_attempts keys must be enumerated.
            assert "mode" in matched[0]
            assert "total_max_attempts" in matched[0]
        finally:
            backend.close()

    def _caplog(self, level: int):  # noqa: ANN202 -- private test helper
        from contextlib import contextmanager

        @contextmanager
        def _ctx():
            logger = logging.getLogger("remote_store.backends._s3_base")
            handler = _ListHandler(level)
            previous_level = logger.level
            logger.addHandler(handler)
            logger.setLevel(level)
            try:
                yield handler.records
            finally:
                logger.removeHandler(handler)
                logger.setLevel(previous_level)

        return _ctx()


class _ListHandler(logging.Handler):
    """Minimal logging.Handler that appends records to a list (mock-spec safe)."""

    def __init__(self, level: int) -> None:
        super().__init__(level=level)
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


class TestAiobotocoreCreateClientBoundary:
    """S3-026: assert at the actual ``aiobotocore.create_client`` call site.

    BUG-178 and BUG-185 both escaped because the kwarg-shape unit tests
    asserted at the ``s3fs.S3FileSystem`` boundary, one level above where
    the duplicate-``config`` ``TypeError`` actually fires. Patching
    ``aiobotocore.session.AioSession.create_client`` and triggering
    ``s3fs.connect()`` exercises the same code path the user hit and would
    catch a future variant of the same bug class.
    """

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
    @pytest.mark.parametrize(
        ("with_retry", "expected_max_attempts"),
        [
            pytest.param(True, 5, id="with-retry"),
            # No-retry case is the literal BUG-185 reproduction (config_kwargs alone).
            pytest.param(False, 3, id="without-retry"),
        ],
    )
    def test_create_client_receives_one_aioconfig_with_merged_values(
        self, backend_cls: str, with_retry: bool, expected_max_attempts: int
    ) -> None:
        """End-to-end: the user's MinIO scenario reaches aiobotocore correctly.

        ``set_session`` runs to completion up to its own ``create_client``
        call; we patch that call with a sentinel-raising side effect so the
        keyword arguments are captured at the actual collision boundary
        without spinning up an aiobotocore client. Asserts the captured
        call carries a single ``config=`` keyword whose ``AioConfig``
        reflects every merged option (timeouts, addressing style, proxies,
        retry policy). Parametrized over with/without ``RetryPolicy``
        because the no-retry variant is the literal BUG-185 reproduction.
        """
        import importlib
        from unittest.mock import patch

        from aiobotocore.config import AioConfig

        from remote_store._config import RetryPolicy

        module_path, cls_name = backend_cls.split(":")
        cls = getattr(importlib.import_module(module_path), cls_name)
        kwargs: dict[str, object] = {
            "bucket": "mybucket",
            "endpoint_url": "https://s3.internal:9000",
            "key": "AKIA...",
            "secret": "secret-redacted",
            "client_options": {
                "config_kwargs": {
                    "connect_timeout": 3.0,
                    "read_timeout": 10.0,
                    "retries": {"max_attempts": 3, "mode": "standard"},
                    "s3": {"addressing_style": "path"},
                    "proxies": {"http": None, "https": None},
                },
            },
        }
        if with_retry:
            kwargs["retry"] = RetryPolicy(max_attempts=5)
        backend = cls(**kwargs)
        try:
            sentinel = RuntimeError("short-circuit set_session for assertion")
            with (
                patch(
                    "aiobotocore.session.AioSession.create_client",
                    side_effect=sentinel,
                ) as mock_cc,
                pytest.raises(RuntimeError, match="short-circuit"),
            ):
                backend._s3fs.connect()

            assert mock_cc.call_count == 1
            kw = mock_cc.call_args.kwargs
            assert "config" in kw, "aiobotocore.create_client must receive config="
            cfg = kw["config"]
            assert isinstance(cfg, AioConfig)
            assert cfg.connect_timeout == 3.0
            assert cfg.read_timeout == 10.0
            # With RetryPolicy: replaces the retries dict (max_attempts=5).
            # Without: caller's config_kwargs.retries flows through (max_attempts=3).
            assert cfg.retries["max_attempts"] == expected_max_attempts
            assert cfg.retries["mode"] == "standard"
            assert cfg.s3 == {"addressing_style": "path"}
            assert cfg.proxies == {"http": None, "https": None}
        finally:
            backend.close()
