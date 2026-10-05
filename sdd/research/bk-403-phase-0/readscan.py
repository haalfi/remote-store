"""pytest plugin: which repo files each test file reads other than by import.

RFC-0019 Phase 0, D5 layer 4, runtime half; throwaway research, not a gate.
Extends ../bk-403-testmon-poc/srcreads.py from ``src/**/*.py`` to every file
under the repository root, and adds two event kinds that scan cannot see:

- ``open`` of a repo file, except opens made by the import machinery
  (``importlib._bootstrap_external`` ``get_data``) or by pytest's assertion
  rewriter, which reads every test module it rewrites;
- ``os.scandir`` / ``os.listdir`` / ``glob.glob`` of a repo directory: a test
  that lists a directory reads every file later added to it;
- ``subprocess.Popen`` whose arguments name a repo path: the child's own reads
  are invisible, so the named target is recorded instead.

Each hit is attributed to the test file active at the time (collection or
setup/call/teardown) and tagged with the innermost frame inside the repo
(``via``): a frame in ``tests/`` or ``scripts/`` is a direct read; ``lib``
means only library code was on the stack (``linecache``, ``inspect``), whose
attribution depends on test order.

Run (bounded parallel, as ``hatch run test``; see plan.md):
  RS_READSCAN_OUT=tmp/readscan/default PYTHONPATH=sdd/research/bk-403-phase-0 \
    .venv/Scripts/python scripts/run_tests.py -p no:benchmark --stage=1 -p readscan
Writes one JSON per xdist worker: {test_file: {target: [kind, via]}}.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

_ROOT_RAW = os.path.abspath(os.environ.get("RS_READSCAN_ROOT", os.getcwd())) + os.sep
ROOT = os.path.normcase(_ROOT_RAW)
_SKIP_TOP = {".git", ".venv", "tmp", ".pytest_cache", ".hypothesis", ".mypy_cache", ".ruff_cache", "site"}
_current: list[str] = []
_hits: dict[str, dict[str, tuple[str, str]]] = {}
_in_hook = False
# Library frames whose file reads are the import system or pytest itself.
_IMPORT_FRAMES = ("importlib._bootstrap_external", "<frozen importlib", "/importlib/")
_PYTEST_FRAMES = ("/_pytest/", "/pluggy/", "/xdist/")


def _rel(p: object) -> str | None:
    """Repo-relative path with its on-disk spelling (normcase only to compare)."""
    try:
        raw = os.path.abspath(os.fsdecode(os.fspath(p)))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if not os.path.normcase(raw).startswith(ROOT):
        return None
    rel = raw[len(_ROOT_RAW) :].replace(os.sep, "/")
    top = rel.split("/", 1)[0]
    if top in _SKIP_TOP or "__pycache__" in rel or rel.endswith((".pyc", ".pyo")):
        return None
    return rel


def _via(depth: int, kind: str) -> str | None:
    """Innermost repo frame, or ``lib:<innermost library file>``.

    None when the event belongs to the import system or to pytest's own
    machinery (assertion rewriting, collection), which are not test reads.
    """
    f = sys._getframe(depth)
    via = None
    lib = None
    first = True
    while f is not None:
        fn = f.f_code.co_filename
        norm = fn.replace("\\", "/")
        if first:
            if f.f_code.co_name == "get_data" and "importlib._bootstrap_external" in fn:
                return None
            first = False
        if via is None:
            r = _rel(fn)
            if r is not None and r.startswith(("tests/", "scripts/", "src/", "examples/")):
                via = f"{r}:{f.f_lineno}"
                break  # frames above (e.g. the rewriter's exec_module) do not matter
            else:
                # The assertion rewriter reading a test's source has no repo frame
                # below it; a module-level read in a test module does (checked
                # only before the first repo frame, so those reads are kept).
                if "/_pytest/assertion/rewrite.py" in norm:
                    return None
                if lib is None:  # innermost library frame decides the exclusions
                    if any(m in norm for m in _IMPORT_FRAMES):
                        return None
                    if kind == "scan" and any(m in norm for m in _PYTEST_FRAMES):
                        return None
                # keep overwriting: the label is the outermost library frame below the repo frame
                lib = (
                    norm.split("site-packages/", 1)[-1]
                    if "site-packages/" in norm
                    else "/".join(norm.rsplit("/", 2)[-2:])
                )
        f = f.f_back
    if via is None:
        return f"lib:{lib}"
    return via if lib is None else f"{via} (lib:{lib})"


def _record(kind: str, target: str, via: str) -> None:
    per = _hits.setdefault(_current[0], {})
    if target not in per or per[target][1].startswith("lib:"):
        per[target] = (kind, via)


def _hook(event: str, args: tuple) -> None:
    global _in_hook
    if _in_hook or not _current:
        return
    if event not in ("open", "os.scandir", "os.listdir", "glob.glob", "subprocess.Popen"):
        return
    _in_hook = True
    try:
        if event == "open":
            path, mode = args[0], args[1] if len(args) > 1 else None
            if isinstance(mode, str) and any(c in mode for c in "wax+"):
                return
            if isinstance(path, int):
                return
            rel = _rel(path)
            if rel is None:
                return
            via = _via(2, "read")
            if via is not None:
                _record("read", rel, via)
        elif event in ("os.scandir", "os.listdir"):
            rel = _rel(args[0] if args[0] is not None else ".")
            via = _via(2, "scan")
            if rel is not None and via is not None:
                _record("scan", rel or ".", via)
        elif event == "glob.glob":
            rel = _rel(os.path.dirname(os.fsdecode(args[0])) or ".")
            via = _via(2, "scan")
            if rel is not None and via is not None:
                _record("scan", rel or ".", via)
        else:  # subprocess.Popen: (executable, args, cwd, env)
            argv = args[1]
            if isinstance(argv, (str, bytes, os.PathLike)):
                argv = [argv]
            for a in argv or ():
                try:
                    a = os.fsdecode(a)
                except TypeError:
                    continue
                cand = a if os.path.isabs(a) else os.path.join(args[2] or os.getcwd(), a)
                rel = _rel(cand)
                if rel is not None and os.path.exists(cand):
                    _record("subprocess", rel, _via(2, "read") or "lib:subprocess")
    finally:
        _in_hook = False


sys.addaudithook(_hook)


def pytest_collectstart(collector):  # noqa: ANN001, ANN201
    if collector.nodeid.endswith(".py"):
        _current[:] = [collector.nodeid]


def pytest_collectreport(report):  # noqa: ANN001, ANN201
    _current[:] = []


def pytest_runtest_setup(item):  # noqa: ANN001, ANN201
    _current[:] = [item.nodeid.split("::")[0]]


def pytest_runtest_teardown(item):  # noqa: ANN001, ANN201
    _current[:] = [item.nodeid.split("::")[0]]


def pytest_runtest_logfinish(nodeid, location):  # noqa: ANN001, ANN201
    _current[:] = []


def pytest_sessionfinish(session):  # noqa: ANN001, ANN201
    out = Path(os.environ.get("RS_READSCAN_OUT", "tmp/readscan"))
    out.mkdir(parents=True, exist_ok=True)
    worker = os.environ.get("PYTEST_XDIST_WORKER", "main")
    name = f"{worker}-{os.getpid()}.json"
    data = {k: {t: list(v) for t, v in sorted(m.items())} for k, m in sorted(_hits.items())}
    (out / name).write_text(json.dumps(data, indent=0), encoding="utf-8")
