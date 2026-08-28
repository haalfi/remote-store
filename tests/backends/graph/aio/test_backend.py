"""GraphBackend public surface (GR-001..005, GR-009/010, GR-036/036a, GR-037, GR-051).

Construction/validation, capability declaration, path addressing and encoding,
the unwrap escape hatch, the close baseline, and credential-safe repr. The
data-plane operations themselves are exercised in the read / write / mutate
test modules; this module covers the construction-time and addressing surface.
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx
import pytest
import respx

from remote_store._capabilities import Capability
from remote_store._config import RetryPolicy
from remote_store._errors import BackendUnavailable, CapabilityNotSupported, InvalidPath
from remote_store.aio.backends._graph.backend import GraphBackend, _encode_segment, _split_parent

_DRIVE = "b!driveid123"
_UPLOAD_URL = "https://up.example.com/session/abc?tempauth=secret"


def _make(**kwargs: Any) -> GraphBackend:
    return GraphBackend(_DRIVE, token_provider=lambda: "tok", **kwargs)


class TestConstruction:
    """GR-001 / GR-005 construction and validation."""

    @pytest.mark.spec("GR-001")
    @pytest.mark.spec("GR-004")
    def test_valid_construction_does_no_io(self) -> None:
        backend = _make()
        assert backend.drive_id == _DRIVE
        assert backend._owned_client is None  # GR-004: no client until first use

    @pytest.mark.spec("GR-005")
    @pytest.mark.parametrize("bad", ["", "   "])
    def test_empty_drive_id_rejected(self, bad: str) -> None:
        with pytest.raises(ValueError, match="drive_id"):
            GraphBackend(bad, token_provider=lambda: "t")

    @pytest.mark.spec("GR-005")
    def test_non_callable_token_provider_rejected(self) -> None:
        with pytest.raises(ValueError, match="token_provider"):
            GraphBackend(_DRIVE, token_provider="not-callable")  # type: ignore[arg-type]

    @pytest.mark.spec("GR-005")
    @pytest.mark.parametrize("bad", [0, -320 * 1024, 320 * 1024 + 1, 500_000])
    def test_misaligned_upload_chunk_size_rejected(self, bad: int) -> None:
        with pytest.raises(ValueError, match="320 KiB"):
            _make(upload_chunk_size=bad)

    @pytest.mark.spec("GR-005")
    def test_aligned_upload_chunk_size_accepted(self) -> None:
        backend = _make(upload_chunk_size=320 * 1024 * 3)
        assert backend._upload_chunk_size == 320 * 1024 * 3

    @pytest.mark.spec("GR-005")
    @pytest.mark.parametrize("bad", [60 * 1024 * 1024, 200 * 320 * 1024])
    def test_oversized_upload_chunk_size_rejected(self, bad: int) -> None:
        # Aligned 320 KiB multiples at/above Graph's 60 MiB per-request ceiling
        # (60 MiB == 192 x 320 KiB exactly; 200 x 320 KiB == 62.5 MiB).
        with pytest.raises(ValueError, match="60 MiB"):
            _make(upload_chunk_size=bad)

    @pytest.mark.spec("GR-005")
    def test_upload_chunk_size_just_below_ceiling_accepted(self) -> None:
        size = 191 * 320 * 1024  # largest aligned multiple strictly below 60 MiB
        backend = _make(upload_chunk_size=size)
        assert backend._upload_chunk_size == size

    @pytest.mark.spec("GR-005")
    @pytest.mark.parametrize("bad", [0, -1.0])
    def test_non_positive_copy_timeout_rejected(self, bad: float) -> None:
        with pytest.raises(ValueError, match="copy_timeout"):
            _make(copy_timeout=bad)

    @pytest.mark.spec("GR-026")
    def test_copy_timeout_none_is_allowed(self) -> None:
        assert _make(copy_timeout=None)._copy_timeout is None

    @pytest.mark.spec("GR-053")
    def test_retry_none_uses_default_profile(self) -> None:
        # retry=None -> the backend's default RetryPolicy() profile (RET-015).
        assert _make()._retry == RetryPolicy()

    @pytest.mark.spec("GR-053")
    def test_explicit_retry_replaces_default(self) -> None:
        policy = RetryPolicy(max_attempts=7)
        assert _make(retry=policy)._retry is policy


class TestIdentity:
    """GR-002 name, GR-003 capabilities."""

    @pytest.mark.spec("GR-002")
    def test_name(self) -> None:
        assert _make().name == "graph"

    @pytest.mark.spec("GR-003")
    def test_capability_set_is_exact(self) -> None:
        expected = {
            Capability.READ,
            Capability.WRITE,
            Capability.DELETE,
            Capability.LIST,
            Capability.MOVE,
            Capability.COPY,
            Capability.METADATA,
            Capability.ATOMIC_WRITE,
            Capability.LAZY_READ,
            Capability.WRITE_RESULT_NATIVE,
        }
        assert set(_make().capabilities) == expected

    @pytest.mark.spec("GR-003")
    @pytest.mark.parametrize(
        "withheld",
        [Capability.GLOB, Capability.ATOMIC_MOVE, Capability.SEEKABLE_READ, Capability.USER_METADATA],
    )
    def test_withheld_capabilities(self, withheld: Capability) -> None:
        assert not _make().capabilities.supports(withheld)

    @pytest.mark.spec("GR-050")
    def test_drive_id_is_immutable(self) -> None:
        # drive_id is a read-only property: changing the target drive requires a
        # new backend. Reserved as a future identity component (GR-050).
        backend = _make()
        assert backend.drive_id == _DRIVE
        with pytest.raises(AttributeError):
            backend.drive_id = "b!other"  # type: ignore[misc]


class TestAddressing:
    """GR-009/010 path resolution and segment encoding; GR-036/036a round-trip."""

    @pytest.mark.spec("GR-036a")
    def test_native_path_empty_key_is_drive_root(self) -> None:
        assert _make().native_path("") == f"/drives/{_DRIVE}/root:"

    @pytest.mark.spec("GR-009")
    def test_native_path_simple(self) -> None:
        assert _make().native_path("a/b.txt") == f"/drives/{_DRIVE}/root:/a/b.txt:"

    @pytest.mark.spec("GR-010")
    def test_native_path_encodes_special_chars(self) -> None:
        # Spaces and ``#`` per the GR-010 example.
        assert _make().native_path("My Folder/file #1.txt") == f"/drives/{_DRIVE}/root:/My%20Folder/file%20%231.txt:"

    @pytest.mark.spec("GR-010")
    @pytest.mark.parametrize(
        ("raw", "encoded"),
        [(" ", "%20"), ("#", "%23"), ("?", "%3F"), ("+", "%2B")],
    )
    def test_encode_segment_special(self, raw: str, encoded: str) -> None:
        assert _encode_segment(f"x{raw}y") == f"x{encoded}y"

    @pytest.mark.spec("GR-010")
    def test_encode_segment_trailing_dot(self) -> None:
        assert _encode_segment("name.") == "name%2E"
        assert _encode_segment("a.b.") == "a.b%2E"  # only the trailing dot

    @pytest.mark.spec("GR-036")
    def test_to_key_strips_prefix_and_decodes(self) -> None:
        backend = _make()
        native = f"/drives/{_DRIVE}/root:/My%20Folder/file%20%231.txt:"
        assert backend.to_key(native) == "My Folder/file #1.txt"

    @pytest.mark.spec("GR-036")
    def test_to_key_passthrough_without_prefix(self) -> None:
        assert _make().to_key("/some/other/path") == "/some/other/path"

    @pytest.mark.spec("GR-036")
    def test_to_key_root_is_empty(self) -> None:
        assert _make().to_key(f"/drives/{_DRIVE}/root:") == ""

    @pytest.mark.spec("GR-036")
    @pytest.mark.parametrize("key", ["", "a", "a/b/c", "My Folder/file #1.txt", "weird+name", "trail."])
    def test_round_trip_identity(self, key: str) -> None:
        backend = _make()
        assert backend.to_key(backend.native_path(key)) == key

    @pytest.mark.spec("BE-029")
    @pytest.mark.spec("GR-036a")
    def test_native_path_agrees_on_both_root_spellings(self) -> None:
        """``""`` and ``"."`` name one path, so they address one item.

        Splitting on ``/`` and keeping every truthy segment kept ``"."``,
        producing an address for an item literally named ``.`` under the drive
        root. This cell was written because nothing in the conformance suite
        executed against this backend — the async addressing cells there were
        skipped for want of a cassette they never needed, which ID-241 fixed.
        They now run on ``graph_replay``, so this is no longer the only cover;
        it is kept because the conformance fixture is rooted under a
        ``base_path`` and this one is not, and the bare-root arm is where the
        defect was. The root-*refusal* cells below are still conformance-
        unreachable: rejecting a root write costs Graph an HTTP round trip
        first, so those cells do need a cassette.
        """
        backend = _make()
        assert backend.native_path(".") == backend.native_path("")

    @pytest.mark.spec("BE-029")
    @pytest.mark.spec("BE-025")
    def test_to_key_of_root_is_the_canonical_spelling(self) -> None:
        backend = _make()
        assert backend.to_key(backend.native_path(".")) == ""

    @pytest.mark.spec("BE-029")
    @pytest.mark.spec("GR-058")
    def test_native_path_root_spellings_agree_under_base_path(self) -> None:
        """The base_path scoping does not reintroduce the divergence."""
        backend = _make(base_path="root/sub")
        assert backend.native_path(".") == backend.native_path("")

    @pytest.mark.spec("BE-029")
    @pytest.mark.spec("GR-017")
    @pytest.mark.parametrize("root", ["", "/", ".", "./", "/./"], ids=range(5))
    def test_write_to_drive_root_is_rejected(self, root: str) -> None:
        """Every spelling that addresses the root is unwritable.

        A ``strip("/")`` test accepted ``"."``, so ``write(".", ...)`` created
        an item named ``.`` instead of being refused.
        """
        with pytest.raises(InvalidPath, match="drive root"):
            _make()._require_writable_key(root)

    @pytest.mark.spec("BE-029")
    @pytest.mark.spec("BE-008")
    @pytest.mark.parametrize("root", ["", "/", ".", "./", "/./"], ids=range(5))
    @pytest.mark.parametrize("op", ["move", "copy"], ids=["move", "copy"])
    async def test_root_as_move_or_copy_destination_is_refused(self, root: str, op: str) -> None:
        """The destination half, exercised through ``move``/``copy`` themselves.

        The sibling above calls ``_require_writable_key`` directly, so it pins
        the helper and not either call site — it passes with both destination
        guards deleted. This drives the real methods, which is what makes it a
        fence rather than a measurement.

        No ``respx.mock``: the guard is a pure string test that runs before any
        request, so an ``InvalidPath`` here *is* the proof it precedes the
        transport. A call that reached the network would fail this cell with a
        connection error instead, which is the discrimination it needs.

        Conformance cannot supply this. Its destination cell seeds through
        ``write``, so the Graph lane skips it for want of a cassette — measured,
        the whole Graph suite passed with the destination guard reverted.
        """
        backend = _make()
        with pytest.raises(InvalidPath, match="drive root") as exc_info:
            await getattr(backend, op)("a.txt", root)
        assert exc_info.value.path == root
        assert exc_info.value.backend == "graph"
        await backend.aclose()

    @pytest.mark.spec("BE-029")
    @pytest.mark.spec("BE-008")
    @pytest.mark.parametrize("root", ["", "/", ".", "./", "/./"], ids=range(5))
    @pytest.mark.parametrize("op", ["move", "copy"], ids=["move", "copy"])
    async def test_root_as_move_or_copy_source_is_refused_from_the_key(self, root: str, op: str) -> None:
        """The source half, and the assertion is about *when* rather than what.

        Graph reaches every other file-shaped root verdict by observation — it
        fetches the item and inspects the response — which satisfies the error
        class and not the precondition order BE-008 step (0) now binds. Before
        the guard, a root source cost a round trip and answered from the
        response; measured against an unreachable endpoint it raised
        ``BackendUnavailable``, not ``InvalidPath``.

        So this cell is written with no mock and no reachable endpoint on
        purpose: reverting the guard turns the raise into a connection failure,
        which is exactly the property under test. Asserting the class alone
        against a live drive would pass either way.
        """
        backend = _make()
        with pytest.raises(InvalidPath, match="folder, not a file") as exc_info:
            await getattr(backend, op)(root, "z.txt")
        assert exc_info.value.path == root
        assert exc_info.value.backend == "graph"
        await backend.aclose()

    @pytest.mark.spec("BE-020")
    @pytest.mark.spec("BE-029")
    @pytest.mark.parametrize("metadata", [None, {"k": "v"}], ids=["no-metadata", "with-metadata"])
    @pytest.mark.parametrize("path", ["", "a.txt"], ids=["root-key", "ordinary-key"])
    async def test_closed_backend_answers_before_every_other_precondition(
        self, path: str, metadata: dict[str, str] | None
    ) -> None:
        """A closed backend says so whatever *else* is wrong with the call.

        The four cells are the cross product of the two pre-checks ``write``
        runs ahead of its first client touch, and the point is the pair that
        carries ``metadata=``: the user-metadata gate sat above the root check,
        so moving the closed guard into ``_require_writable_key`` fixed the
        no-metadata column and left the other answering
        ``CapabilityNotSupported`` on a store that cannot honour any answer.

        Written as a cross product rather than one closed-write cell because
        that is the shape that fails: a single cell pins whichever pre-check
        happens to run first and stays green when a new one is added above it.
        Both columns must be ``BackendUnavailable`` or the caller's diagnosis
        depends on which guard was written first.
        """
        backend = _make()
        await backend.aclose()
        with pytest.raises(BackendUnavailable, match="closed"):
            await backend.write(path, b"x", metadata=metadata)

    @pytest.mark.spec("GR-009")
    def test_resolve_carries_drive_id(self) -> None:
        plan = _make().resolve("a.txt")
        assert plan.backend == "graph"
        assert plan.details["drive_id"] == _DRIVE
        assert plan.details["base_url"] == "https://graph.microsoft.com/v1.0"


class TestBasePath:
    """GR-058 base_path scoping."""

    @pytest.mark.spec("GR-058")
    def test_native_path_prepends_base_path(self) -> None:
        assert _make(base_path="root/sub").native_path("a/b.txt") == f"/drives/{_DRIVE}/root:/root/sub/a/b.txt:"

    @pytest.mark.spec("GR-058")
    def test_native_path_empty_key_is_base_folder(self) -> None:
        assert _make(base_path="root/sub").native_path("") == f"/drives/{_DRIVE}/root:/root/sub:"

    @pytest.mark.spec("GR-058")
    def test_to_key_round_trips_under_base_path(self) -> None:
        backend = _make(base_path="root/sub")
        assert backend.to_key(backend.native_path("a/b.txt")) == "a/b.txt"
        assert backend.to_key(backend.native_path("")) == ""

    @pytest.mark.spec("GR-058")
    def test_parent_ref_path_includes_base_path(self) -> None:
        # The move/copy parentReference must also be scoped (GR-058 + GR-027/025).
        backend = _make(base_path="root/sub")
        assert backend._parent_ref_path("dir") == f"/drives/{_DRIVE}/root:/root/sub/dir"

    @pytest.mark.spec("BE-029")
    @pytest.mark.spec("GR-027")
    @pytest.mark.parametrize(
        "dst",
        ["./x.txt", "././x.txt", ".//x.txt", "/x.txt", "x.txt"],
        ids=["dot", "dot-dot", "dot-slash", "slash", "bare"],
    )
    def test_move_destination_addresses_the_root_under_every_spelling(self, dst: str) -> None:
        """The destination *address* must agree with the destination *guard*.

        ``_parent_ref_path`` had its own ``if s`` split while the guard used the
        ``"."``-dropping one, so these spellings passed the guard and then named
        a folder literally called ``.`` on the wire (``%2E``) — the same defect
        the root check itself was written for, one function along, and reachable
        because the guard's tolerance is what lets the spelling get this far.

        The second assertion is what makes this a fence rather than a literal:
        the property is that the two predicates agree, so a change moving both
        keeps it green and a change moving either alone does not.
        """
        backend = _make()
        parent, _name = _split_parent(dst)
        assert backend._parent_ref_path(parent) == f"/drives/{_DRIVE}/root:"
        assert backend.native_path(dst) == backend.native_path("x.txt")

    @pytest.mark.spec("GR-058")
    def test_base_path_slashes_normalised(self) -> None:
        assert _make(base_path="/root/sub/").native_path("x") == f"/drives/{_DRIVE}/root:/root/sub/x:"

    @pytest.mark.spec("GR-058")
    def test_non_string_base_path_rejected(self) -> None:
        with pytest.raises(ValueError, match="base_path"):
            _make(base_path=123)  # type: ignore[arg-type]

    @pytest.mark.spec("GR-058")
    def test_default_base_path_targets_drive_root(self) -> None:
        assert _make().native_path("a") == f"/drives/{_DRIVE}/root:/a:"


class TestUnwrapAndClose:
    """GR-037 escape hatch and GR-051 close baseline."""

    @pytest.mark.spec("GR-037")
    def test_unwrap_returns_httpx_client(self) -> None:
        backend = _make()
        assert isinstance(backend.unwrap(httpx.AsyncClient), httpx.AsyncClient)

    @pytest.mark.spec("GR-037")
    def test_unwrap_wrong_type_raises(self) -> None:
        with pytest.raises(CapabilityNotSupported):
            _make().unwrap(str)

    @pytest.mark.spec("GR-051")
    async def test_aclose_closes_owned_client(self) -> None:
        backend = _make()
        client = backend._client  # force lazy creation
        await backend.aclose()
        assert client.is_closed
        assert backend._owned_client is None

    @pytest.mark.spec("GR-051")
    async def test_aclose_is_idempotent(self) -> None:
        backend = _make()
        _ = backend._client
        await backend.aclose()
        await backend.aclose()  # second call must not raise
        assert backend._owned_client is None

    @pytest.mark.spec("GR-051")
    async def test_aclose_leaves_user_supplied_client_open(self) -> None:
        async with httpx.AsyncClient() as user_client:
            backend = _make(http_client=user_client)
            assert backend.unwrap(httpx.AsyncClient) is user_client
            await backend.aclose()
            assert not user_client.is_closed  # caller owns it

    @pytest.mark.spec("GR-051")
    async def test_aclose_flushes_auth_cache(self) -> None:
        class _AuthProvider:
            def __init__(self) -> None:
                self.flushed = False

            def __call__(self) -> str:
                return "tok"

            def flush_cache(self) -> None:
                self.flushed = True

        provider = _AuthProvider()
        backend = GraphBackend(_DRIVE, token_provider=provider)
        await backend.aclose()
        assert provider.flushed

    @respx.mock
    @pytest.mark.spec("GR-051")
    async def test_aclose_cancels_pollers_and_aborts_sessions_together(self) -> None:
        # The combined close() assertion no single op-step owns end-to-end:
        # GR-WRITE landed the upload-session-abort half (TestCloseAbortsSessions
        # in test_write.py) and GR-MUTATE the poller-cancel half
        # (TestClosePollerCancel in test_mutate.py), but only here are BOTH
        # exercised at once on one fully-assembled backend that holds a pending
        # poller AND an in-flight upload session. close() must cancel the poller,
        # fire DELETE {sessionUrl}, empty both registries, and never raise.
        delete = respx.delete(_UPLOAD_URL).mock(return_value=httpx.Response(204))
        backend = _make()

        async def _never() -> None:
            await asyncio.Event().wait()

        task: asyncio.Task[None] = asyncio.ensure_future(_never())
        backend._pending_pollers.add(task)
        backend._active_upload_sessions.add(_UPLOAD_URL)

        await backend.aclose()  # must not raise on cleanup

        assert task.cancelled()
        assert delete.called
        assert backend._pending_pollers == set()
        assert backend._active_upload_sessions == set()

    @pytest.mark.spec("GR-052")
    def test_client_options_passed_through(self) -> None:
        backend = _make(client_options={"timeout": 5.0})
        assert backend._client.timeout.read == 5.0

    @pytest.mark.spec("GR-035")
    def test_repr_has_no_token(self) -> None:
        r = repr(_make())
        assert _DRIVE in r
        assert "tok" not in r
