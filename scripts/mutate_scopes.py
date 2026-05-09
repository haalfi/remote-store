"""Single source of truth for pytest-gremlins mutation scopes.

Each scope pairs source-file mutation targets with a test selection
(path, optional ``-k`` filter) and the containers required. The same
definitions feed ``hatch run mutate <scope>`` (via
``scripts/run_mutate.py``) and ``.github/workflows/mutation.yml``.

Every scope is derived. Backend scopes read
``tests/backends/fixtures/backends.toml`` + ``fixtures.toml`` via
``_loader.py``. Non-backend scopes pair each ``src/remote_store/_<x>.py``
or ``src/remote_store/ext/<x>.py`` with the prefix-matching
``tests/test_<x>*.py`` (and ``tests/test_ext_<x>*.py`` for ext); test
files that match no src file roll into a single ``core-misc`` scope.

Cmdline split
=============

pytest-gremlins re-runs pytest with every collected node id as argv. A
single conformance topic file can exceed the ~32 KiB Windows command-line
limit (WinError 206) when it covers all backends. Topics that fit run as
one scope; topics over the limit are split by ``[backend.<x>].transport``.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))

from tests.backends.fixtures._loader import load_backends, load_fixtures  # noqa: E402

_TRANSPORTS = ("fs", "memory", "sql", "http", "ssh")
_SYNC_ADAPTER = "src/remote_store/aio/_sync_adapter.py"
_SRC_ROOT = _REPO_ROOT / "src" / "remote_store"
_TESTS_ROOT = _REPO_ROOT / "tests"


@dataclass(frozen=True)
class Scope:
    targets: list[str]
    tests: list[str]
    filter: str | None = None
    needs: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Registry-driven primitives (backend scopes)
# ---------------------------------------------------------------------------


def _src(b) -> list[str]:
    """Source files of backend ``b`` under ``src/`` (excludes test-only
    backends like ``dafny`` whose source points at a tests/ helper).
    """
    return [s for s in b.sources if s.startswith("src/")]


def _test_dir(backend_name: str) -> str:
    """``tests/backends/<dir>/`` for ``backend_name``. ``s3_pyarrow`` shares
    ``tests/backends/s3/`` with ``S3Backend`` (they share ``_s3_base.py``).
    """
    return "s3" if backend_name == "s3_pyarrow" else backend_name


def _filter_term(backend_name: str) -> str:
    """``-k`` term matching every ``stage <= 2`` fixture of ``backend_name``
    and no other backend's fixtures. Falls back to ``OR`` of fixture names
    when the backend name collides (``s3`` matches ``s3_pyarrow_*``;
    ``azure`` matches ``azure_live*``).
    """
    fxs = load_fixtures().values()
    own = {f.name for f in fxs if f.backend == backend_name and f.stage <= 2}
    if not own:
        return ""
    forbidden = {f.name for f in fxs if f.backend != backend_name or f.stage > 2}
    if all(backend_name in n for n in own) and not any(backend_name in n for n in forbidden):
        return backend_name
    return " or ".join(sorted(own))


def _needs(filter_str: str | None) -> list[str]:
    """Containers required by every fixture matched by ``filter_str``.
    ``None`` matches all fixtures (full-conformance scopes).
    """
    fxs = load_fixtures().values()
    if not filter_str:
        matched = list(fxs)
    else:
        terms = [t.strip() for t in filter_str.split(" or ") if t.strip()]
        matched = [f for f in fxs if any(t in f.name for t in terms)]
    return sorted({f.container for f in matched if f.container != "none"})


# ---------------------------------------------------------------------------
# Filesystem-driven primitives (non-backend scopes)
# ---------------------------------------------------------------------------


def _toplevel_test_files() -> list[Path]:
    """``tests/test_*.py`` (top-level only, no subdirs)."""
    return [p for p in sorted(_TESTS_ROOT.glob("test_*.py")) if p.parent == _TESTS_ROOT]


def _matching_tests(name: str, *, ext_prefix: bool) -> list[str]:
    """Test filenames matching ``test_<name>*.py`` (and ``test_ext_<name>*.py``
    for ext) at the top of ``tests/``.
    """
    matches = set(_TESTS_ROOT.glob(f"test_{name}.py")) | set(_TESTS_ROOT.glob(f"test_{name}_*.py"))
    if ext_prefix:
        matches |= set(_TESTS_ROOT.glob(f"test_ext_{name}.py")) | set(_TESTS_ROOT.glob(f"test_ext_{name}_*.py"))
    return sorted(p.name for p in matches if p.parent == _TESTS_ROOT)


# ---------------------------------------------------------------------------
# SCOPES — every entry derived from the registry or filesystem
# ---------------------------------------------------------------------------


def _build() -> dict[str, Scope]:
    backends = load_backends().values()
    all_src = sorted({s for b in backends for s in _src(b)})
    full_needs = _needs(None)
    out: dict[str, Scope] = {}
    matched_tests: set[str] = set()

    # Per-file non-backend scopes: each src/remote_store/_<x>.py and
    # src/remote_store/ext/<x>.py paired with prefix-matching test files
    # at tests/test_<x>*.py. The ``backends/_<x>.py`` loop currently
    # produces no scopes — every backend src file is claimed by a
    # ``backends-*`` transport scope and any backend-specific top-level
    # test has been migrated under ``tests/backends/<backend>/``.
    def _add_per_file(p: Path, scope_name: str, src_rel: str, *, ext_prefix: bool) -> None:
        stem = p.stem.lstrip("_")
        tests = _matching_tests(stem, ext_prefix=ext_prefix)
        if not tests:
            return
        # Fail loud rather than silently overwrite if a future src layout
        # produces both ``src/remote_store/_<x>.py`` and
        # ``src/remote_store/backends/_<x>.py`` with matching tests — both
        # would land on the same ``core-<x>`` key today.
        if scope_name in out:
            raise ValueError(f"mutate scope name collision: {scope_name!r} (src_rel={src_rel!r})")
        out[scope_name] = Scope(
            targets=[src_rel],
            tests=[f"tests/{t}" for t in tests],
        )
        matched_tests.update(tests)

    for p in sorted(_SRC_ROOT.glob("_*.py")):
        if p.name != "__init__.py":
            _add_per_file(p, f"core-{p.stem.lstrip('_')}", f"src/remote_store/{p.name}", ext_prefix=False)
    for p in sorted((_SRC_ROOT / "ext").glob("*.py")):
        if p.name != "__init__.py":
            _add_per_file(p, f"ext-{p.stem}", f"src/remote_store/ext/{p.name}", ext_prefix=True)
    for p in sorted((_SRC_ROOT / "backends").glob("_*.py")):
        if p.name != "__init__.py":
            _add_per_file(p, f"core-{p.stem.lstrip('_')}", f"src/remote_store/backends/{p.name}", ext_prefix=False)

    # Orphan-catch: top-level test files matching no src by prefix
    # (test_open_atomic, test_ping, test_pbt_*, test_snippets, ...). These
    # exercise the public API and cross-cutting behaviours. Targets are
    # every non-backend src file plus backend-folder *utilities* — files
    # under backends/ that no TOML backend claims as its source (today
    # only ``_fileinfo.py``). Real backend src files belong to
    # ``backends-*`` scopes; including them here would surface mutations
    # that cross-cutting tests can't actually exercise.
    known_backend_src = {s for b in backends for s in b.sources}
    orphan_targets = (
        [f"src/remote_store/{p.name}" for p in sorted(_SRC_ROOT.glob("_*.py")) if p.name != "__init__.py"]
        + [
            f"src/remote_store/ext/{p.name}"
            for p in sorted((_SRC_ROOT / "ext").glob("*.py"))
            if p.name != "__init__.py"
        ]
        + [
            f"src/remote_store/backends/{p.name}"
            for p in sorted((_SRC_ROOT / "backends").glob("_*.py"))
            if p.name != "__init__.py" and f"src/remote_store/backends/{p.name}" not in known_backend_src
        ]
    )
    orphan_tests = [f"tests/{p.name}" for p in _toplevel_test_files() if p.name not in matched_tests]
    if orphan_tests:
        out["core-misc"] = Scope(targets=orphan_targets, tests=orphan_tests)

    # Per-transport backend scopes — collapses old backends-local/cloud.
    for t in _TRANSPORTS:
        ts = [b for b in backends if b.transport == t]
        dirs = sorted({_test_dir(b.name) for b in ts if (_REPO_ROOT / "tests/backends" / _test_dir(b.name)).is_dir()})
        if not dirs:
            continue
        out[f"backends-{t}"] = Scope(
            targets=sorted({s for b in ts for s in _src(b)}),
            tests=[f"tests/backends/{d}/" for d in dirs],
            needs=sorted(
                {
                    f.container
                    for f in load_fixtures().values()
                    if f.backend in {b.name for b in ts} and f.container != "none"
                }
            ),
        )

    # Conformance — sync-adapter + the three unsplit topics walk every backend.
    out["conformance-sync-adapter"] = Scope(
        targets=sorted({*all_src, _SYNC_ADAPTER}),
        tests=["tests/backends/conformance/test_sync_adapter_conformance.py"],
        needs=full_needs,
    )
    for topic in ("listing", "metadata", "streaming"):
        out[f"conformance-{topic}"] = Scope(
            targets=all_src,
            tests=[f"tests/backends/conformance/test_{topic}.py"],
            needs=full_needs,
        )

    # Conformance topics over the cmdline limit — split by transport.
    # Skip transports with no stage-≤2 backends (``_filter_term`` returns
    # empty for them); an empty filter would otherwise materialise as a
    # full-conformance scope with empty targets and ``needs=full_needs``.
    for topic in ("io", "atomic", "errors", "identity"):
        for t in _TRANSPORTS:
            ts = [b for b in backends if b.transport == t]
            f = " or ".join(filter(None, (_filter_term(b.name) for b in ts)))
            if not f:
                continue
            out[f"conformance-{topic}-{t}"] = Scope(
                targets=sorted({s for b in ts for s in _src(b)}),
                tests=[f"tests/backends/conformance/test_{topic}.py"],
                filter=f,
                needs=_needs(f),
            )

    # Async-extended — per backend that wires a native or adapted async
    # implementation today (memory, local). Mirrors the conformance-split
    # ``if not f: continue`` guard so a future backend with only stage-3
    # fixtures does not silently produce a scope with empty filter and
    # ``_needs(f)`` expanding to ``full_needs``.
    for backend_name in ("local", "memory"):
        f = _filter_term(backend_name)
        if not f:
            continue
        b = load_backends()[backend_name]
        out[f"conformance-async-extended-{backend_name}"] = Scope(
            targets=sorted({*_src(b), _SYNC_ADAPTER}),
            tests=["tests/backends/conformance/test_async_extended.py"],
            filter=f,
            needs=_needs(f),
        )

    return out


SCOPES: dict[str, Scope] = _build()
