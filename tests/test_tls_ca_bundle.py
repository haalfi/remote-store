"""TLS CA bundle resolution and validation tests -- covers TLS-xxx spec items."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

if TYPE_CHECKING:
    from pathlib import Path

from remote_store.backends._s3_base import (
    _S3_CA_ENV_VARS,
    _resolve_tls_ca_bundle,
    _validate_tls_ca_bundle,
)


class TestResolveTlsCaBundle:
    """TLS-003: env var fallback chain resolution."""

    @pytest.mark.spec("TLS-003")
    def test_explicit_wins_over_env_vars(self) -> None:
        env = {"AWS_CA_BUNDLE": "/env/ca.pem", "REQUESTS_CA_BUNDLE": "/env/req.pem"}
        with patch.dict("os.environ", env, clear=False):
            result = _resolve_tls_ca_bundle("/explicit/ca.pem", _S3_CA_ENV_VARS)
        assert result == "/explicit/ca.pem"

    @pytest.mark.spec("TLS-003")
    def test_first_env_var_wins(self) -> None:
        env = {"AWS_CA_BUNDLE": "/aws/ca.pem", "REQUESTS_CA_BUNDLE": "/req/ca.pem"}
        with patch.dict("os.environ", env, clear=False):
            result = _resolve_tls_ca_bundle(None, _S3_CA_ENV_VARS)
        assert result == "/aws/ca.pem"

    @pytest.mark.spec("TLS-003")
    def test_falls_through_to_ssl_cert_file(self) -> None:
        env = {"AWS_CA_BUNDLE": "", "REQUESTS_CA_BUNDLE": "", "SSL_CERT_FILE": "/ssl/ca.pem"}
        with patch.dict("os.environ", env, clear=False):
            result = _resolve_tls_ca_bundle(None, _S3_CA_ENV_VARS)
        assert result == "/ssl/ca.pem"

    @pytest.mark.spec("TLS-003")
    def test_all_unset_returns_none(self) -> None:
        env = {v: "" for v in _S3_CA_ENV_VARS}
        with patch.dict("os.environ", env, clear=False):
            result = _resolve_tls_ca_bundle(None, _S3_CA_ENV_VARS)
        assert result is None

    @pytest.mark.spec("TLS-003")
    def test_empty_env_var_treated_as_unset(self) -> None:
        env = {"AWS_CA_BUNDLE": "", "REQUESTS_CA_BUNDLE": "/req/ca.pem"}
        with patch.dict("os.environ", env, clear=False):
            result = _resolve_tls_ca_bundle(None, _S3_CA_ENV_VARS)
        assert result == "/req/ca.pem"


class TestValidateTlsCaBundle:
    """TLS-004: early path validation at construction time."""

    @pytest.mark.spec("TLS-004")
    def test_none_is_valid(self) -> None:
        _validate_tls_ca_bundle(None)

    @pytest.mark.spec("TLS-004")
    def test_valid_file_is_accepted(self, tmp_path: Path) -> None:
        cert = tmp_path / "ca.pem"
        cert.write_text("fake cert")
        _validate_tls_ca_bundle(str(cert))

    @pytest.mark.spec("TLS-004")
    def test_nonexistent_path_raises(self) -> None:
        with pytest.raises(ValueError, match="does not exist or is not a file"):
            _validate_tls_ca_bundle("/nonexistent/ca.pem")

    @pytest.mark.spec("TLS-004")
    def test_directory_path_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="does not exist or is not a file"):
            _validate_tls_ca_bundle(str(tmp_path))
