"""BE-031: the kernel's ``delete_folder`` sequence, in both runtimes.

Two halves. The first runs the real kernel and the decided model of
``sdd/rfcs/rfc-0017-delete-folder-measure.py`` (its ``Kernel`` under P1 D1 W1
R1 M1 F1 Q1, the options BK-396 decided) side by side over the model's own
drivers, and requires the same answer and post-state in every cell,
including the 88-cell ``enum`` product over refusal, ``stat`` outcome,
listing outcome and ``missing_ok`` that enumerates the probe rule. So the
port is checked against the model, not re-typed by hand. The second half
covers, over the fake driver, the cases the model measures only through
drivers that need a live wire or filesystem (its ``S3Driver``, ``SQLDriver``,
``AzureFlatDriver`` and ``LocalDriver``): ``parents == "none"``, links,
concurrent writers and deleters, and refusals that pass unprobed. Its
``parents == "none"`` table departs from the model in one place on purpose:
the model's ``_none`` lets a raising listing propagate, while the kernel
reads a ``NotFound`` on the listing's first page as an empty listing (BE-031).
"""

from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from remote_store._capabilities import Capability, CapabilitySet
from remote_store._errors import DirectoryNotEmpty, InvalidPath, NotFound, PermissionDenied, RemoteStoreError
from remote_store._kernel._model import Entry, Op, Page
from remote_store._kernel.aio_backend import AsyncDriverBackend
from remote_store._kernel.backend import DriverBackend
from tests._kernel._fake import RUNTIMES, FakeContainerGone, FakeDenied, FakeOdd, FakeStore, make_kernel

if TYPE_CHECKING:
    from types import ModuleType

pytestmark = [pytest.mark.parametrize("runtime", RUNTIMES), pytest.mark.spec("BE-031")]

_MODEL_PATH = Path(__file__).resolve().parents[2] / "sdd" / "rfcs" / "rfc-0017-delete-folder-measure.py"


def _load_model() -> ModuleType:
    # The model is a record under sdd/rfcs/, not a scripts/ module, so it is
    # loaded by path here, beside the kernel it checks.
    spec = importlib.util.spec_from_file_location("rfc_0017_delete_folder_model", _MODEL_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


MODEL = _load_model()


# --- the model's drivers, presented to the real kernel --------------------------


class _Adapter:
    """A model driver as a kernel driver: same state, same refusals."""

    namespace = "hierarchical"
    put_is_atomic = False
    close_is_terminal = False

    def __init__(self, model: Any) -> None:
        self.model = model
        self.name = "model"
        self.parents = model.parents
        self.capabilities = CapabilitySet({Capability.DELETE, Capability.LIST})

    def _entry(self, key: str) -> Entry:
        folders = getattr(self.model, "dirs", set())
        return Entry(key, "folder" if key in folders else "file")

    def stat(self, key: str, *, follow_links: bool = True) -> Entry | None:
        kind = self.model.stat(key)
        return None if kind is None else Entry(key, kind)

    def list_page(
        self,
        prefix: str,
        *,
        delimiter: str | None,
        cursor: Any = None,
        limit: int | None = None,
        follow_links: bool = True,
    ) -> Page:
        files, folders = self.model.list_page(prefix, delimiter, limit)
        return Page(tuple(self._entry(k) for k in files), tuple(folders), None)

    def delete(self, key: str) -> None:
        self.model.delete(key)

    def remove_folder(self, key: str) -> None:
        self.model.remove_folder(key)

    def classify(self, exc: Exception, *, op: Op, key: str) -> RemoteStoreError:
        raise AssertionError(f"the model raises typed errors only, got {exc!r}")

    def container_absent(self, exc: BaseException, *, op: Op) -> bool:
        return False


class _TreeAdapter(_Adapter):
    def delete_tree(self, key: str) -> None:
        self.model.delete_tree(key)


def _async_face(sync_cls: type[_Adapter]) -> type:
    members: dict[str, Any] = {}
    for name in ("stat", "list_page", "delete", "remove_folder", "delete_tree"):
        if hasattr(sync_cls, name):

            def make(fn: Any) -> Any:
                async def method(self: Any, *args: Any, **kwargs: Any) -> Any:
                    return fn(self, *args, **kwargs)

                return method

            members[name] = make(getattr(sync_cls, name))
    return type(f"Async{sync_cls.__name__}", (sync_cls,), members)


def _real(runtime: str, model_driver: Any, key: str, recursive: bool, missing_ok: bool) -> str:
    cls = _TreeAdapter if model_driver.has_delete_tree else _Adapter
    if runtime == "sync":
        kernel: Any = DriverBackend(cls(model_driver))
        call = lambda: kernel.delete_folder(key, recursive=recursive, missing_ok=missing_ok)  # noqa: E731
    else:
        kernel = AsyncDriverBackend(_async_face(cls)(model_driver))
        call = lambda: asyncio.run(kernel.delete_folder(key, recursive=recursive, missing_ok=missing_ok))  # noqa: E731
    try:
        call()
    except Exception as exc:  # noqa: BLE001 - the answer is the class, leak included
        return str(MODEL.answer(exc))
    return str(MODEL.answer(None))


def _model(model_driver: Any, key: str, recursive: bool, missing_ok: bool) -> str:
    try:
        MODEL.Kernel(model_driver, **MODEL.DECIDED).delete_folder(key, recursive=recursive, missing_ok=missing_ok)
    except Exception as exc:  # noqa: BLE001
        return str(MODEL.answer(exc))
    return str(MODEL.answer(None))


def _hier_cells() -> list[Any]:
    cells = []
    for variant in ("delete_tree", "walk", "implicit"):
        for state, (key, files, dirs) in MODEL.HIER_STATES.items():
            for recursive, missing_ok in MODEL.CALLS:
                cells.append(
                    pytest.param(
                        variant,
                        key,
                        files,
                        dirs,
                        recursive,
                        missing_ok,
                        id=f"{variant}-{state}-r{int(recursive)}-m{int(missing_ok)}",
                    )
                )
    return cells


def _model_driver(variant: str, files: list[str], dirs: list[str]) -> Any:
    if variant == "implicit":
        return MODEL.ImplicitTreeDriver(files, dirs)
    driver = MODEL.MemoryDriver(files, dirs)
    if variant == "walk":
        driver.has_delete_tree = False
    return driver


@pytest.mark.parametrize(("variant", "key", "files", "dirs", "recursive", "missing_ok"), _hier_cells())
def test_the_kernel_matches_the_decided_model_on_every_key_state(
    runtime: str, variant: str, key: str, files: list[str], dirs: list[str], recursive: bool, missing_ok: bool
) -> None:
    expected_driver = _model_driver(variant, files, dirs)
    expected = _model(expected_driver, key, recursive, missing_ok)
    actual_driver = _model_driver(variant, files, dirs)
    actual = _real(runtime, actual_driver, key, recursive, missing_ok)
    assert actual == expected
    assert actual_driver.post() == expected_driver.post()


def _enum_cells() -> list[Any]:
    cells = []
    for ctx in ("remove_folder", "delete_tree", "walk delete", "walk rmdir"):
        for refusal in (NotFound, RemoteStoreError):
            for stat_out in ("raises", None, "file", "folder"):
                lists = ("raises", "empty", "non-empty") if stat_out == "folder" and ctx != "delete_tree" else ("-",)
                for list_out in lists:
                    for missing_ok in (False, True):
                        name = f"{ctx}-{refusal.__name__}-stat_{stat_out}-list_{list_out}-m{int(missing_ok)}"
                        cells.append(pytest.param(ctx, refusal, stat_out, list_out, missing_ok, id=name))
    return cells


ENUM_CELLS = _enum_cells()


def test_the_enumeration_is_the_models_88_cells(runtime: str) -> None:
    assert len(ENUM_CELLS) == len(MODEL.enum_rows("Q1")) == 88


@pytest.mark.parametrize(("ctx", "refusal", "stat_out", "list_out", "missing_ok"), ENUM_CELLS)
def test_the_probe_rule_matches_the_model_over_its_enumerated_space(
    runtime: str, ctx: str, refusal: type[RemoteStoreError], stat_out: str | None, list_out: str, missing_ok: bool
) -> None:
    recursive = ctx != "remove_folder"
    expected = _model(MODEL.ScriptedDriver(ctx, refusal, stat_out, list_out), "d", recursive, missing_ok)
    actual = _real(runtime, MODEL.ScriptedDriver(ctx, refusal, stat_out, list_out), "d", recursive, missing_ok)
    assert actual == expected


# --- what the model does not cover: over the fake driver ----------------------------

FLAT_TABLE = [
    # key, files, recursive, missing_ok, answer, files left
    ("d", ["d/a", "d/s/c"], False, False, DirectoryNotEmpty, ["d/a", "d/s/c"]),
    ("d", ["d/a", "d/s/c"], True, False, None, []),
    ("f", ["f"], False, False, InvalidPath, ["f"]),
    ("f", ["f"], True, True, InvalidPath, ["f"]),
    ("b", ["b", "b/x"], False, False, DirectoryNotEmpty, ["b", "b/x"]),
    ("b", ["b", "b/x"], True, False, None, ["b"]),
    ("z", [], False, False, NotFound, []),
    ("z", [], True, True, None, []),
    ("f/x", ["f"], True, False, NotFound, ["f"]),
]


@pytest.mark.parametrize("with_tree", [True, False])
@pytest.mark.parametrize(("key", "files", "recursive", "missing_ok", "answer", "left"), FLAT_TABLE)
def test_parents_none_answers_by_its_table(
    runtime: str,
    with_tree: bool,
    key: str,
    files: list[str],
    recursive: bool,
    missing_ok: bool,
    answer: type[Exception] | None,
    left: list[str],
) -> None:
    store = FakeStore(parents="none").add(*files)
    run = make_kernel(runtime, store, protocols=("delete_tree",) if with_tree else ())
    if answer is None:
        run.delete_folder(key, recursive=recursive, missing_ok=missing_ok)
    else:
        with pytest.raises(answer):
            run.delete_folder(key, recursive=recursive, missing_ok=missing_ok)
    assert sorted(store.files) == left
    assert store.called("remove_folder") == []


def test_parents_none_reads_an_absent_container_as_an_empty_listing(runtime: str) -> None:
    store = FakeStore(parents="none").add("d/a")
    store.container = False
    run = make_kernel(runtime, store, protocols=("delete_tree",))
    run.delete_folder("d", recursive=True, missing_ok=True)
    with pytest.raises(NotFound):
        run.delete_folder("d")


@pytest.mark.spec("BE-030")
@pytest.mark.parametrize("with_tree", [False, True])
def test_parents_none_over_an_omitted_key(runtime: str, with_tree: bool) -> None:
    store = FakeStore(parents="none").add("d/a")
    store.files["d/b\\c"] = store.files["d/a"]
    run = make_kernel(runtime, store, protocols=("delete_tree",) if with_tree else ())
    if with_tree:
        # The wire's tree delete removes the whole prefix, the omitted key with it.
        run.delete_folder("d", recursive=True)
        assert store.files == {}
        return
    with pytest.raises(DirectoryNotEmpty):
        run.delete_folder("d", recursive=True)
    assert sorted(store.files) == ["d/b\\c"]
    assert ("delete", "d/b\\c") not in store.calls


@pytest.mark.spec("BE-021")
@pytest.mark.parametrize("missing_ok", [False, True])
def test_parents_none_propagates_a_not_found_after_the_first_page(runtime: str, missing_ok: bool) -> None:
    # BE-021's first-page bound: a later page's NotFound reports a change under the scan.
    store = FakeStore(parents="none", page_size=1).add("d/a", "d/b", "d/c")
    run = make_kernel(runtime, store, protocols=())
    store.fault("list_page", FakeContainerGone("deleted under the scan"), key="d", nth=2)
    with pytest.raises(NotFound):
        run.delete_folder("d", recursive=True, missing_ok=missing_ok)
    assert sorted(store.files) == ["d/a", "d/b", "d/c"]


def test_an_implicit_walk_removes_the_persistent_folders(runtime: str) -> None:
    # Implicit folders persist until removed (Graph, Azure HNS), so the walk's
    # last remove_folder finds the folder it emptied.
    store = FakeStore(parents="implicit").add("k/a", "k/s/b", "k/t/")
    run = make_kernel(runtime, store, protocols=("remove_folder",))
    run.delete_folder("k", recursive=True)
    assert (store.files, sorted(store.folders)) == ({}, [])


def test_parents_none_tolerates_a_file_deleted_under_the_walk(runtime: str) -> None:
    store = FakeStore(parents="none").add("d/a", "d/b")
    run = make_kernel(runtime, store, protocols=())
    store.fault("delete", key="d/a", hook=lambda: store.files.pop("d/a"))
    run.delete_folder("d", recursive=True)
    assert store.files == {}


@pytest.mark.parametrize("protocols", [("remove_folder",), ("remove_folder", "delete_tree")])
@pytest.mark.parametrize("recursive", [False, True])
@pytest.mark.parametrize("target", ["d", "nowhere", "f"])
def test_a_link_at_the_key_is_never_a_folder(
    runtime: str, recursive: bool, target: str, protocols: tuple[str, ...]
) -> None:
    store = FakeStore().add("d/a", "f")
    store.links["l"] = target
    run = make_kernel(runtime, store, protocols=protocols)
    with pytest.raises(InvalidPath):
        run.delete_folder("l", recursive=recursive, missing_ok=True)
    assert "d/a" in store.files
    assert "l" in store.links


def test_a_link_below_the_key_is_deleted_as_an_entry_and_its_target_kept(runtime: str) -> None:
    store = FakeStore().add("t/x", "k/a")
    store.links["k/l"] = "t"
    run = make_kernel(runtime, store, protocols=("remove_folder",))
    run.delete_folder("k", recursive=True)
    assert "t/x" in store.files
    assert "k/l" not in store.links
    assert ("list_page", "k/l") not in store.calls


def test_a_concurrent_writer_mid_walk_answers_directory_not_empty(runtime: str) -> None:
    store = FakeStore().add("d/a", "d/s/b")
    run = make_kernel(runtime, store, protocols=("remove_folder",))
    store.fault("remove_folder", key="d/s", hook=lambda: store.add("d/new"))
    with pytest.raises(DirectoryNotEmpty):
        run.delete_folder("d", recursive=True)
    assert sorted(store.files) == ["d/new"]


def test_a_concurrent_deleter_mid_walk_is_tolerated(runtime: str) -> None:
    store = FakeStore().add("d/a", "d/s/b")
    run = make_kernel(runtime, store, protocols=("remove_folder",))
    store.fault("delete", key="d/s/b", hook=lambda: store.files.pop("d/s/b"))
    run.delete_folder("d", recursive=True)
    assert store.files == {}
    assert "d" not in store.folders


@pytest.mark.parametrize("recursive", [False, True])
def test_a_refusal_that_says_nothing_about_the_key_passes_unprobed(runtime: str, recursive: bool) -> None:
    store = FakeStore().add("d/")
    run = make_kernel(runtime, store, protocols=("remove_folder", "delete_tree"))
    store.fault("remove_folder", FakeDenied("denied"))
    store.fault("delete_tree", FakeDenied("denied"))
    with pytest.raises(PermissionDenied, match="denied"):
        run.delete_folder("d", recursive=recursive, missing_ok=True)
    assert store.called("stat") == []
    assert store.called("list_page") == []


def test_an_untyped_refusal_on_a_non_empty_folder_is_typed_by_the_probes(runtime: str) -> None:
    store = FakeStore().add("d/a")
    run = make_kernel(runtime, store, protocols=("remove_folder",))
    store.fault("remove_folder", FakeOdd("rmdir failed"))
    with pytest.raises(DirectoryNotEmpty) as caught:
        run.delete_folder("d")
    assert type(caught.value.__cause__) is RemoteStoreError
    assert [p for p, _k in store.calls] == ["remove_folder", "stat", "list_page"]


def test_an_empty_folder_is_removed_in_one_driver_call(runtime: str) -> None:
    store = FakeStore().add("e/")
    run = make_kernel(runtime, store, protocols=("remove_folder", "delete_tree"))
    run.delete_folder("e")
    assert store.calls == [("remove_folder", "e")]
    assert "e" not in store.folders
