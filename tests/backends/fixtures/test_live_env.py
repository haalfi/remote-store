"""Tests for ``tests.backends.fixtures._live_env`` (spec 048 / TEST-001).

Each opt-in path the validator can reach gets one test. The contract is
"once the user opts in, misconfiguration fails loud, not silent" — the
tests assert each ``pytest.fail`` branch fires with a message that points
the user at the missing piece.
"""

from __future__ import annotations

import pytest

from tests.backends.fixtures._live_env import (
    _S3_EMULATOR_FRAGMENTS,
    require_azure_live_connection_string,
    require_live_credentials,
    require_s3_live_credentials,
)
from tests.backends.fixtures._loader import FixtureDescriptor

_REAL_CONN = (
    "DefaultEndpointsProtocol=https;EndpointSuffix=core.windows.net;"
    "AccountName=realaccount;AccountKey=ZmFrZWtleQ==;"
    "BlobEndpoint=https://realaccount.blob.core.windows.net/"
)
_AZURITE_SHORTHAND_CONN = "UseDevelopmentStorage=true"
_AZURITE_EXPLICIT_CONN = (
    "DefaultEndpointsProtocol=http;AccountName=devstoreaccount1;"
    "AccountKey=Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq/K1SZFPTOtr/KBHBeksoGMGw==;"
    "BlobEndpoint=http://127.0.0.1:10000/devstoreaccount1;"
)

_REAL_AWS_CREDS = {
    "AWS_ACCESS_KEY_ID": "AKIAIOSFODNN7EXAMPLE",
    "AWS_SECRET_ACCESS_KEY": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
    "AWS_DEFAULT_REGION": "eu-central-1",
}


@pytest.fixture(autouse=True)
def _disable_dotenv_load(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stub ``dotenv.load_dotenv`` so the helper's lazy backstop does not
    repopulate ``AZURE_STORAGE_CONNECTION_STRING`` from the project ``.env``
    during each test. Without this, ``monkeypatch.delenv`` is silently
    undone by the helper before its empty-check fires.
    """
    import dotenv

    monkeypatch.setattr(dotenv, "load_dotenv", lambda *args, **kwargs: False)


@pytest.mark.spec("TEST-001")
class TestRequireAzureLiveConnectionString:
    """Each fail-loud branch of ``require_azure_live_connection_string``."""

    def test_returns_real_connection_string_unchanged(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("AZURE_STORAGE_CONNECTION_STRING", _REAL_CONN)
        assert require_azure_live_connection_string() == _REAL_CONN

    def test_missing_connection_string_fails_loud(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.delenv("AZURE_STORAGE_CONNECTION_STRING", raising=False)
        with pytest.raises(pytest.fail.Exception, match="AZURE_STORAGE_CONNECTION_STRING is empty"):
            require_azure_live_connection_string()

    def test_whitespace_only_connection_string_fails_loud(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Whitespace-only env var must fail-loud, not pass through to the SDK."""
        monkeypatch.setenv("AZURE_STORAGE_CONNECTION_STRING", "   ")
        with pytest.raises(pytest.fail.Exception, match="AZURE_STORAGE_CONNECTION_STRING is empty"):
            require_azure_live_connection_string()

    def test_azurite_shorthand_fails_loud(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("AZURE_STORAGE_CONNECTION_STRING", _AZURITE_SHORTHAND_CONN)
        with pytest.raises(pytest.fail.Exception, match="points at Azurite"):
            require_azure_live_connection_string()

    def test_azurite_explicit_endpoint_fails_loud(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Explicit-endpoint Azurite carries ``AccountName=devstoreaccount1``."""
        monkeypatch.setenv("AZURE_STORAGE_CONNECTION_STRING", _AZURITE_EXPLICIT_CONN)
        with pytest.raises(pytest.fail.Exception, match="points at Azurite"):
            require_azure_live_connection_string()


def _synthetic_descriptor(
    *,
    live_creds_env: tuple[str, ...],
    live_opt_in_env: str | None = None,
) -> FixtureDescriptor:
    """Build a minimal ``FixtureDescriptor`` for direct
    ``require_live_credentials`` testing.

    The on-disk ``fixtures.toml`` has no entry with empty
    ``live_creds_env`` and no entry without ``live_opt_in_env``, so
    these branches need a synthetic record to exercise.
    """
    return FixtureDescriptor(
        name="synthetic",
        backend="memory",
        stage=1,
        kind="real-local",
        container="none",
        is_async=False,
        flat_namespace=False,
        self_op_supported=True,
        rejects_write_under_file_ancestor=True,
        strict_only=False,
        conformance_excluded=False,
        large_write_distinct=False,
        transport="memory",
        concurrency="thread_safe",
        live_opt_in_env=live_opt_in_env,
        live_creds_env=live_creds_env,
    )


@pytest.mark.spec("TEST-001")
class TestRequireLiveCredentials:
    """Cover the descriptor-driven branches of ``require_live_credentials``
    that ``require_azure_live_connection_string`` does not reach: empty
    ``live_creds_env`` (TOML misconfiguration) and the no-gate prefix
    path when ``live_opt_in_env`` is unset.
    """

    def test_empty_live_creds_env_fails_loud(self) -> None:
        desc = _synthetic_descriptor(
            live_creds_env=(),
            live_opt_in_env="RS_TEST_SYNTHETIC",
        )
        with pytest.raises(pytest.fail.Exception, match="has no live_creds_env"):
            require_live_credentials(desc)

    def test_missing_env_without_opt_in_omits_gate_prefix(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When ``live_opt_in_env`` is ``None`` the failure message has no
        ``<VAR>=1 set but `` prefix.
        """
        monkeypatch.delenv("RS_TEST_SYNTHETIC_CREDS", raising=False)
        desc = _synthetic_descriptor(
            live_creds_env=("RS_TEST_SYNTHETIC_CREDS",),
            live_opt_in_env=None,
        )
        with pytest.raises(pytest.fail.Exception) as exc_info:
            require_live_credentials(desc)
        msg = str(exc_info.value)
        assert "RS_TEST_SYNTHETIC_CREDS is empty" in msg
        assert "set but" not in msg


@pytest.mark.spec("TEST-001")
class TestRequireS3LiveCredentials:
    """Each fail-loud branch of ``require_s3_live_credentials``."""

    def _set_real_creds(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for var, val in _REAL_AWS_CREDS.items():
            monkeypatch.setenv(var, val)
        monkeypatch.delenv("AWS_ENDPOINT_URL", raising=False)
        monkeypatch.delenv("AWS_S3_ENDPOINT_URL", raising=False)

    def test_returns_real_credentials_unchanged(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        self._set_real_creds(monkeypatch)
        assert require_s3_live_credentials() == _REAL_AWS_CREDS

    @pytest.mark.parametrize("missing_var", list(_REAL_AWS_CREDS))
    def test_missing_cred_env_var_fails_loud(
        self,
        monkeypatch: pytest.MonkeyPatch,
        missing_var: str,
    ) -> None:
        self._set_real_creds(monkeypatch)
        monkeypatch.delenv(missing_var)
        with pytest.raises(pytest.fail.Exception, match=f"{missing_var} is empty"):
            require_s3_live_credentials()

    def test_whitespace_only_cred_fails_loud(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        self._set_real_creds(monkeypatch)
        monkeypatch.setenv("AWS_ACCESS_KEY_ID", "   ")
        with pytest.raises(pytest.fail.Exception, match="AWS_ACCESS_KEY_ID is empty"):
            require_s3_live_credentials()

    @pytest.mark.parametrize("fragment", list(_S3_EMULATOR_FRAGMENTS))
    def test_emulator_endpoint_url_fails_loud(
        self,
        monkeypatch: pytest.MonkeyPatch,
        fragment: str,
    ) -> None:
        self._set_real_creds(monkeypatch)
        monkeypatch.setenv("AWS_ENDPOINT_URL", f"http://{fragment}/")
        with pytest.raises(pytest.fail.Exception, match="points at an S3 emulator"):
            require_s3_live_credentials()

    @pytest.mark.parametrize("fragment", list(_S3_EMULATOR_FRAGMENTS))
    def test_emulator_s3_endpoint_url_fails_loud(
        self,
        monkeypatch: pytest.MonkeyPatch,
        fragment: str,
    ) -> None:
        self._set_real_creds(monkeypatch)
        monkeypatch.setenv("AWS_S3_ENDPOINT_URL", f"http://{fragment}/")
        with pytest.raises(pytest.fail.Exception, match="points at an S3 emulator"):
            require_s3_live_credentials()
