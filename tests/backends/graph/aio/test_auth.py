"""GraphAuth construction, flow selection, masking, and token acquisition.

MSAL is faked via ``monkeypatch`` (real fake classes, not ``Mock`` — see
``check_mock_spec``) so the GR-006/007/008 control flow is exercised without a
network handshake. The live device-code path is reality-checked separately in
the GR-CORE PR.
"""

from __future__ import annotations

import asyncio
import threading
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
    def test_second_instance_reads_first_instances_write(self, tmp_path: Any) -> None:
        # BK-291: the multi-process-safety guarantee, exercised behaviourally
        # (not just isinstance) across two cache instances over the SAME file —
        # the multi-worker shape, in-process and deterministic. Instance A
        # persists a token; instance B, built fresh over the same path,
        # reload-merges from disk and finds it (read-your-writes across the
        # shared lock-coordinated cache).
        path = str(tmp_path / "c.json")
        event = {
            "client_id": "c",
            "scope": ["s1"],
            "token_endpoint": "https://login.microsoftonline.com/consumers/oauth2/v2.0/token",
            "response": {"access_token": "atoken", "token_type": "Bearer", "expires_in": 3600},
        }
        GraphAuth("consumers", "c", cache_path=path)._load_cache().add(event)

        reader = GraphAuth("consumers", "c", cache_path=path)._load_cache()
        found = list(reader.search(reader.CredentialType.ACCESS_TOKEN))
        assert [e.get("secret") for e in found] == ["atoken"]

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


class TestAsyncAcquisition:
    """GR-008 async acquisition path — `aget_token` offloads MSAL to a worker
    thread and single-flights concurrent callers (BK-292).

    These tests fake `get_token` directly (the sync acquisition is already
    covered by `TestGetToken`); the point under test is the async wrapper's
    off-loop offload and single-flight dedup, not the MSAL control flow.
    """

    @pytest.mark.spec("GR-008")
    async def test_aget_token_returns_token(self, fake_msal: None, tmp_path: Any) -> None:
        auth = GraphAuth("t", "c", client_secret="s", cache_path=str(tmp_path / "c.json"))
        assert await auth.aget_token() == "tok-cc"

    @pytest.mark.spec("GR-008")
    async def test_single_flight_dedups_concurrent_acquisitions(
        self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # N concurrent aget_token() callers must share ONE acquisition: the
        # underlying get_token runs exactly once and every caller gets its token.
        # A threading.Event gate holds the single in-flight worker open until all
        # callers have piled onto it, so the dedup is observed deterministically
        # (not won by the first call finishing before the others schedule).
        auth = GraphAuth("t", "c", client_secret="s", cache_path=str(tmp_path / "c.json"))
        calls = 0
        gate = threading.Event()

        def _fake_get_token() -> str:
            nonlocal calls
            calls += 1
            gate.wait(timeout=5)
            return "tok-shared"

        monkeypatch.setattr(auth, "get_token", _fake_get_token)

        tasks = [asyncio.ensure_future(auth.aget_token()) for _ in range(8)]
        await asyncio.sleep(0)  # let all callers schedule and join the in-flight task
        gate.set()  # release the single worker thread
        results = await asyncio.gather(*tasks)

        assert calls == 1
        assert results == ["tok-shared"] * 8

    @pytest.mark.spec("GR-008")
    async def test_acquisition_runs_off_the_event_loop(self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
        # The sync MSAL work must run on a worker thread, never the loop thread.
        # Deterministic (thread-identity), not timing-based.
        auth = GraphAuth("t", "c", client_secret="s", cache_path=str(tmp_path / "c.json"))
        loop_thread = threading.get_ident()
        worker_thread: list[int] = []

        def _fake_get_token() -> str:
            worker_thread.append(threading.get_ident())
            return "tok"

        monkeypatch.setattr(auth, "get_token", _fake_get_token)
        await auth.aget_token()
        assert worker_thread == [worker_thread[0]]
        assert worker_thread[0] != loop_thread

    @pytest.mark.spec("GR-008")
    async def test_exception_fans_out_to_all_joiners_then_retries(
        self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # An acquisition failure propagates to the owner and every joiner sharing
        # the in-flight task; a later call starts a fresh acquisition (retry).
        auth = GraphAuth("t", "c", client_secret="s", cache_path=str(tmp_path / "c.json"))
        calls = 0
        gate = threading.Event()

        def _boom() -> str:
            nonlocal calls
            calls += 1
            gate.wait(timeout=5)
            raise PermissionDenied("nope", backend="graph")

        monkeypatch.setattr(auth, "get_token", _boom)

        tasks = [asyncio.ensure_future(auth.aget_token()) for _ in range(4)]
        await asyncio.sleep(0)
        gate.set()
        results = await asyncio.gather(*tasks, return_exceptions=True)
        assert calls == 1  # single-flight: one shared acquisition
        assert all(isinstance(r, PermissionDenied) for r in results)

        # The in-flight window is closed, so a subsequent call retries afresh.
        gate.set()
        with pytest.raises(PermissionDenied):
            await auth.aget_token()
        assert calls == 2

    @pytest.mark.spec("GR-008")
    async def test_caller_cancellation_does_not_fan_out_to_siblings(
        self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Cancelling one caller (e.g. a gather sibling timing out) must NOT cancel
        # the shared acquisition or fan CancelledError out to the other joiners.
        auth = GraphAuth("t", "c", client_secret="s", cache_path=str(tmp_path / "c.json"))
        calls = 0
        gate = threading.Event()

        def _fake_get_token() -> str:
            nonlocal calls
            calls += 1
            gate.wait(timeout=5)
            return "tok"

        monkeypatch.setattr(auth, "get_token", _fake_get_token)

        tasks = [asyncio.ensure_future(auth.aget_token()) for _ in range(6)]
        await asyncio.sleep(0)  # all callers join the one in-flight acquisition
        tasks[0].cancel()  # the owner is cancelled mid-acquisition
        gate.set()
        results = await asyncio.gather(*tasks, return_exceptions=True)

        assert isinstance(results[0], asyncio.CancelledError)
        assert results[1:] == ["tok"] * 5  # siblings unaffected by the cancellation
        assert calls == 1  # still one shared acquisition

    @pytest.mark.spec("GR-008")
    async def test_cancelled_owner_does_not_trigger_second_acquisition(
        self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # A cancelled owner must not orphan the worker thread into a second
        # concurrent acquisition: a new caller arriving while the worker is still
        # in flight joins the existing acquisition rather than starting another
        # (two MSAL acquisitions would touch the not-thread-safe app/cache at once).
        auth = GraphAuth("t", "c", client_secret="s", cache_path=str(tmp_path / "c.json"))
        calls = 0
        started = threading.Event()
        gate = threading.Event()

        def _fake_get_token() -> str:
            nonlocal calls
            calls += 1
            started.set()
            gate.wait(timeout=5)
            return "tok"

        monkeypatch.setattr(auth, "get_token", _fake_get_token)

        owner = asyncio.ensure_future(auth.aget_token())
        for _ in range(5000):  # wait until the worker thread is actually running
            if started.is_set():
                break
            await asyncio.sleep(0.001)
        assert started.is_set()
        owner.cancel()
        await asyncio.sleep(0)  # let the cancellation settle
        joiner = asyncio.ensure_future(auth.aget_token())  # arrives mid-flight
        await asyncio.sleep(0)
        gate.set()
        owner_result = (await asyncio.gather(owner, return_exceptions=True))[0]
        joiner_result = await joiner

        assert isinstance(owner_result, asyncio.CancelledError)
        assert joiner_result == "tok"
        assert calls == 1  # the joiner reused the in-flight acquisition
