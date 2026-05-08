"""Tests for ``tests.backends.fixtures._live_env`` (spec 048 / TEST-001).

Each opt-in path the validator can reach gets one test. The contract is
"once the user opts in, misconfiguration fails loud, not silent" — the
tests assert each ``pytest.fail`` branch fires with a message that points
the user at the missing piece.
"""

from __future__ import annotations

import pytest

from tests.backends.fixtures._live_env import require_azure_live_connection_string

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
