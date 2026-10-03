"""pytest plugin: record the src/ files each test file opens other than by import.

Evidence for research-bk-403-testmon-poc.md, Appendix D; not a gate.
An audit hook on ``open`` records every ``src/**/*.py`` opened during
collection or a test, skipping opens made by the import machinery. Reads by a
subprocess are not seen.

Run from the PoC worktree (see research-bk-403-testmon-poc.py):
  cp sdd/research/research-bk-403-srcreads.py tmp/poc/srcreads.py
  cd tmp/poc-wt
  PYTHONPATH=../poc ../venv313/bin/python -m pytest --stage=1 -p no:benchmark -p srcreads -p no:xdist
Writes tmp/poc/srcreads.json: {test_file: [src paths]}.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "tmp" / "poc-wt"
SRC = str(ROOT / "src") + os.sep
_current: list[str] = []
_hits: dict[str, set[str]] = {}


def _by_import() -> bool:
    # Only the loader's own get_data opens counts as import. Checking any frame
    # higher up would also swallow reads by module-level code run under
    # exec_module, e.g. an AST walk of src/ at import time.
    f = sys._getframe(2)  # 0 = here, 1 = _hook, 2 = the caller of open/open_code
    return f.f_code.co_name == "get_data" and "importlib._bootstrap_external" in f.f_code.co_filename


def _hook(event: str, args: tuple) -> None:
    if event != "open" or not _current:
        return
    try:
        path = os.path.abspath(os.fsdecode(os.fspath(args[0])))
    except TypeError:
        return
    if not path.startswith(SRC) or not path.endswith(".py"):
        return
    if _by_import():
        return
    _hits.setdefault(_current[0], set()).add(path[len(str(ROOT)) + 1 :])


sys.addaudithook(_hook)


def pytest_collectstart(collector):  # noqa: ANN001, ANN201
    if collector.nodeid.endswith(".py"):
        _current[:] = [collector.nodeid]


def pytest_collectreport(report):  # noqa: ANN001, ANN201
    _current[:] = []


def pytest_runtest_setup(item):  # noqa: ANN001, ANN201
    _current[:] = [item.nodeid.split("::")[0]]


def pytest_runtest_teardown(item):  # noqa: ANN001, ANN201
    _current[:] = []


def pytest_sessionfinish(session):  # noqa: ANN001, ANN201
    out = Path(__file__).with_name("srcreads.json")
    out.write_text(json.dumps({k: sorted(v) for k, v in sorted(_hits.items())}, indent=1))
