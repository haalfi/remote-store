"""Tests for ``tests.backends.fixtures._live_env`` (spec 048 / TEST-001).

Each opt-in path the validator can reach gets one test. The contract is
"once the user opts in, misconfiguration fails loud, not silent" — the
tests assert each ``pytest.fail`` branch fires with a message that points
the user at the missing piece.
"""

from __future__ import annotations

import pytest

from tests.backends.fixtures._live_env import (
    require_azure_live_connection_string,
    require_live_credentials,
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
        transport="memory",
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
