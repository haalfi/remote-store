"""GraphAuth construction, flow selection, masking, and token acquisition.

MSAL is faked via ``monkeypatch`` (real fake classes, not ``Mock`` — see
``check_mock_spec``) so the GR-006/007/008 control flow is exercised without a
network handshake. The live device-code path is reality-checked separately in
the GR-CORE PR.
"""

from __future__ import annotations

from typing import Any

import pytest

from remote_store._config import Secret
from remote_store._errors import PermissionDenied
from remote_store.aio.backends._graph.auth import GraphAuth


class _FakeConfidentialApp:
    def __init__(self, client_id: str, *, authority: str, client_credential: Any, token_cache: Any) -> None:
        self.client_credential = client_credential

    def acquire_token_for_client(self, scopes: list[str]) -> dict[str, str]:
        return {"access_token": "tok-cc"}


class _FakePublicApp:
    accounts: list[dict[str, str]] = []
    silent_result: dict[str, str] | None = {"access_token": "tok-silent"}

    def __init__(self, client_id: str, *, authority: str, token_cache: Any) -> None:
        self.authority = authority

    def get_accounts(self) -> list[dict[str, str]]:
        return type(self).accounts

    def acquire_token_silent(self, scopes: list[str], account: Any) -> dict[str, str] | None:
        return type(self).silent_result

    def initiate_device_flow(self, scopes: list[str]) -> dict[str, str]:
        return {"user_code": "ABC123", "message": "Sign in at https://microsoft.com/devicelogin"}

    def acquire_token_by_device_flow(self, flow: dict[str, str]) -> dict[str, str]:
        return {"access_token": "tok-device"}


@pytest.fixture
def fake_msal(monkeypatch: pytest.MonkeyPatch) -> None:
    import msal

    # The token cache is a real msal_extensions.PersistedTokenCache over the
    # test's tmp_path (BK-291); the fake apps ignore the token_cache arg, so no
    # cache monkeypatch is needed — only the two MSAL app classes are faked.
    monkeypatch.setattr(msal, "ConfidentialClientApplication", _FakeConfidentialApp)
    monkeypatch.setattr(msal, "PublicClientApplication", _FakePublicApp)
    # Reset the device-code fake's class state between tests.
    _FakePublicApp.accounts = []
    _FakePublicApp.silent_result = {"access_token": "tok-silent"}


class TestConstruction:
    @pytest.mark.spec("GR-006")
    @pytest.mark.parametrize(("tenant", "client"), [("", "c"), ("  ", "c"), ("t", ""), ("t", "  ")])
    def test_empty_ids_rejected(self, tenant: str, client: str) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            GraphAuth(tenant, client)

    @pytest.mark.spec("GR-006")
    def test_secret_and_certificate_mutually_exclusive(self) -> None:
        with pytest.raises(ValueError, match="at most one"):
            GraphAuth("t", "c", client_secret="s", client_certificate={"thumbprint": "x"})

    @pytest.mark.spec("GR-006")
    def test_authority_from_tenant(self) -> None:
        assert GraphAuth("consumers", "c").authority == "https://login.microsoftonline.com/consumers"

    @pytest.mark.spec("GR-006")
    def test_client_secret_selects_app_only_flow(self) -> None:
        assert GraphAuth("t", "c", client_secret="s")._app_only is True

    @pytest.mark.spec("GR-007")
    def test_no_credential_selects_device_flow(self) -> None:
        auth = GraphAuth("consumers", "c")
        assert auth._app_only is False
        # Consumer-compatible delegated default (the reality-check finding).
        assert auth._scopes == ["Files.ReadWrite", "User.Read"]

    @pytest.mark.spec("GR-006")
    def test_client_credentials_default_scope(self) -> None:
        assert GraphAuth("t", "c", client_secret="s")._scopes == ["https://graph.microsoft.com/.default"]


class TestMasking:
    @pytest.mark.spec("GR-035")
    def test_repr_masks_secret(self) -> None:
        r = repr(GraphAuth("t", "c", client_secret="topsecret"))
        assert "topsecret" not in r
        assert "***" in r
        assert "client_credentials" in r

    @pytest.mark.spec("GR-035")
    def test_secret_wrapper_accepted_and_masked(self) -> None:
        r = repr(GraphAuth("t", "c", client_secret=Secret("wrapped-secret")))
        assert "wrapped-secret" not in r

    @pytest.mark.spec("GR-007")
    def test_repr_device_flow_has_no_secret_fields(self) -> None:
        r = repr(GraphAuth("consumers", "c"))
        assert "client_secret=None" in r
        assert "device_code" in r


class TestGetToken:
    @pytest.mark.spec("GR-006")
    def test_client_credentials_token(self, fake_msal: None, tmp_path: Any) -> None:
        auth = GraphAuth("t", "c", client_secret="s", cache_path=str(tmp_path / "c.json"))
        assert auth.get_token() == "tok-cc"

    @pytest.mark.spec("GR-007")
    def test_device_code_uses_cached_account_silently(self, fake_msal: None, tmp_path: Any) -> None:
        _FakePublicApp.accounts = [{"username": "u@example.com"}]
        auth = GraphAuth("consumers", "c", cache_path=str(tmp_path / "c.json"))
        assert auth.get_token() == "tok-silent"

    @pytest.mark.spec("GR-007")
    def test_device_code_interactive_when_no_account(self, fake_msal: None, tmp_path: Any) -> None:
        _FakePublicApp.accounts = []
        prompts: list[dict[str, str]] = []
        auth = GraphAuth("consumers", "c", cache_path=str(tmp_path / "c.json"), prompt_callback=prompts.append)
        assert auth.get_token() == "tok-device"
        assert len(prompts) == 1
        assert "user_code" in prompts[0]

    @pytest.mark.spec("GR-008")
    def test_callable_protocol(self, fake_msal: None, tmp_path: Any) -> None:
        auth = GraphAuth("t", "c", client_secret="s", cache_path=str(tmp_path / "c.json"))
        assert auth() == "tok-cc"  # GraphAuth instance IS a token provider

    @pytest.mark.spec("GR-006")
    def test_acquisition_failure_raises(self, fake_msal: None, tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
        def _fail(self: Any, scopes: list[str]) -> dict[str, str]:
            return {"error": "invalid_client", "error_description": "bad secret"}

        monkeypatch.setattr(_FakeConfidentialApp, "acquire_token_for_client", _fail)
        auth = GraphAuth("t", "c", client_secret="sup3r-s3cret", cache_path=str(tmp_path / "c.json"))
        # Typed error, catchable via `except RemoteStoreError` — never the
        # stdlib PermissionError (audit-016 M7); the detail carries the MSAL
        # error_description, never the secret.
        with pytest.raises(PermissionDenied, match="bad secret") as excinfo:
            auth.get_token()
        assert excinfo.value.backend == "graph"
        assert "sup3r-s3cret" not in str(excinfo.value)

    @pytest.mark.spec("GR-006")
    def test_app_is_built_once(self, fake_msal: None, tmp_path: Any) -> None:
        auth = GraphAuth("t", "c", client_secret="s", cache_path=str(tmp_path / "c.json"))
        auth.get_token()
        first = auth._app
        auth.get_token()
        assert auth._app is first  # cached, not rebuilt

    @pytest.mark.spec("GR-007")
    def test_existing_cache_file_is_loaded(self, fake_msal: None, tmp_path: Any) -> None:
        cache_file = tmp_path / "c.json"
        cache_file.write_text("{}", encoding="utf-8")
        auth = GraphAuth("consumers", "c", cache_path=str(cache_file))
        _FakePublicApp.accounts = [{"username": "u@example.com"}]
        auth.get_token()
        assert auth._cache is not None

    @pytest.mark.spec("GR-007")
    def test_device_flow_initiation_failure(
        self, fake_msal: None, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            _FakePublicApp, "initiate_device_flow", lambda self, scopes: {"error_description": "no flow"}
        )
        auth = GraphAuth("consumers", "c", cache_path=str(tmp_path / "c.json"))
        with pytest.raises(ValueError, match="device-code flow"):
            auth.get_token()

    @pytest.mark.spec("GR-007")
    def test_device_flow_prints_message_without_callback(
        self, fake_msal: None, tmp_path: Any, capsys: pytest.CaptureFixture[str]
    ) -> None:
        auth = GraphAuth("consumers", "c", cache_path=str(tmp_path / "c.json"))
        assert auth.get_token() == "tok-device"
        assert "devicelogin" in capsys.readouterr().out


class TestCachePersistence:
    """GR-007 token-cache persistence via msal_extensions.PersistedTokenCache.

    BK-291: the cache writes through to disk multi-process-safely on every
    acquisition; ``flush_cache`` is a best-effort no-op kept only for the
    GR-051 ``close()`` hook.
    """

    @pytest.mark.spec("GR-007")
    def test_default_cache_path_uses_user_config_dir(self) -> None:
        path = GraphAuth("consumers", "c")._resolve_cache_path()
        assert path.endswith("graph_token_cache.json")
        assert "remote-store" in path

    @pytest.mark.spec("GR-007")
    def test_cache_is_multiprocess_safe_persisted_cache(self, tmp_path: Any) -> None:
        # BK-291: the cache must be a lock-coordinated, multi-process-safe
        # PersistedTokenCache (not a bare SerializableTokenCache whose
        # truncate-then-write corrupts under concurrent writers). Assert the
        # public type, not msal-extensions' private `_lock_location` attr — the
        # lockfile-backed guarantee is exercised behaviourally by the
        # write-through and best-effort tests below.
        from msal_extensions import PersistedTokenCache

        cache = GraphAuth("consumers", "c", cache_path=str(tmp_path / "c.json"))._load_cache()
        assert isinstance(cache, PersistedTokenCache)

    @pytest.mark.spec("GR-007")
    def test_persistence_failure_is_best_effort(
        self, tmp_path: Any, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # BK-291 review: persistence now happens inside MSAL's lock-coordinated
        # modify() (not a separate flush). A disk/lock failure there must be
        # swallowed + logged (best-effort), never escape token acquisition as an
        # untyped exception — preserving the GR-006/GR-008 typed-error contract.
        cache = GraphAuth("consumers", "c", cache_path=str(tmp_path / "c.json"))._load_cache()

        def _boom(_content: str) -> None:
            raise OSError("disk full")

        monkeypatch.setattr(cache._persistence, "save", _boom)
        cache.add(  # add() -> modify() -> save(); the OSError must not propagate
            {
                "client_id": "c",
                "scope": ["s1"],
                "token_endpoint": "https://login.microsoftonline.com/consumers/oauth2/v2.0/token",
                "response": {"access_token": "atoken", "token_type": "Bearer", "expires_in": 3600},
            }
        )
        assert any("token cache" in r.getMessage() for r in caplog.records)

    @pytest.mark.spec("GR-007")
    def test_read_failure_is_best_effort(
        self, tmp_path: Any, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # BK-291 review round 2: the READ path must also be best-effort. A
        # corrupt / persistently-contended cache makes PersistedTokenCache's
        # search() (and the find() that delegates to it) re-raise after its
        # dirty-read retries; that must degrade to a cache miss, not escape
        # acquisition as an untyped json/OS error.
        import msal_extensions.token_cache as mxtc

        monkeypatch.setattr(mxtc.time, "sleep", lambda *_a, **_k: None)  # skip retry backoff
        cache = GraphAuth("consumers", "c", cache_path=str(tmp_path / "c.json"))._load_cache()

        def _boom() -> None:
            raise OSError("cache unreadable")

        monkeypatch.setattr(cache, "_reload_if_necessary", _boom)
        result = cache.search(cache.CredentialType.ACCESS_TOKEN)
        assert result == []  # degraded to "no cached token", not raised
        assert any("token cache" in r.getMessage() for r in caplog.records)

    @pytest.mark.spec("GR-007")
    def test_acquired_token_is_written_through_to_disk(self, tmp_path: Any) -> None:
        # BK-291: an MSAL token acquisition routes through PersistedTokenCache's
        # lock-coordinated modify(), which writes the cache through to disk
        # immediately — no separate flush. The directory is created lazily by
        # FilePersistence, mirroring the old auto-mkdir behaviour.
        import json

        target = tmp_path / "nested" / "c.json"
        cache = GraphAuth("consumers", "c", cache_path=str(target))._load_cache()
        cache.add(
            {
                "client_id": "c",
                "scope": ["s1"],
                "token_endpoint": "https://login.microsoftonline.com/consumers/oauth2/v2.0/token",
                "response": {"access_token": "atoken", "token_type": "Bearer", "expires_in": 3600},
            }
        )
        assert "AccessToken" in json.loads(target.read_text(encoding="utf-8"))

    @pytest.mark.spec("GR-051")
    def test_flush_cache_is_noop_and_never_raises(self, tmp_path: Any) -> None:
        # The close() hook (GR-051) calls flush_cache duck-typed; with
        # PersistedTokenCache persistence is continuous, so flush is a no-op
        # that must never raise and must not write a separate file.
        target = tmp_path / "c.json"
        auth = GraphAuth("t", "c", client_secret="s", cache_path=str(target))
        auth.flush_cache()  # no cache loaded yet
        auth._cache = auth._load_cache()
        auth.flush_cache()  # cache loaded — still a no-op
        assert not target.exists()
