"""Mutation-scope manifest invariants.

Pin the contract that ``scripts/mutate_scopes.py`` and the fixture
registry stay in sync: every async fixture in the registry must be
matched by at least one ``conformance-async-extended-*`` scope's ``-k``
filter. Without this guard, adding a new async fixture (e.g. async S3,
async Azure) would silently get zero coverage from the per-topic
mutation scopes.

The manifest is loaded via ``importlib.util.spec_from_file_location``
rather than ``sys.path`` manipulation; ``check_test_placement.py``
flags the latter pattern outside ``tests/scripts/``.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from tests.backends.fixtures import _load_all, all_fixtures

_load_all()

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = _REPO_ROOT / "scripts" / "mutate_scopes.py"
_RUN_MUTATE = _REPO_ROOT / "scripts" / "run_mutate.py"

# Subprocess wrapper that simulates the bare ``actions/setup-python``
# environment used by the ``mutation.yml`` setup job: pytest and
# remote_store are blocked at import time via a ``sys.meta_path`` finder,
# then the target script is exec'd with forwarded CLI args. Lives at
# module scope so the parametrised test below shares one source string.
_BLOCK_WRAPPER = textwrap.dedent(
    """\
    import runpy
    import sys


    _BLOCKED = ("pytest", "remote_store")


    class _Block:
        def find_spec(self, name, path, target=None):
            if name.split(".", 1)[0] in _BLOCKED:
                raise ModuleNotFoundError(f"{name}: blocked by regression test for BUG-206")
            return None


    for _mod in list(sys.modules):
        if _mod.split(".", 1)[0] in _BLOCKED:
            sys.modules.pop(_mod, None)
    sys.meta_path.insert(0, _Block())

    script_path, *script_args = sys.argv[1:]
    sys.argv = [script_path, *script_args]
    runpy.run_path(script_path, run_name="__main__")
    """
)


def _load_manifest():
    spec = importlib.util.spec_from_file_location("mutate_scopes", _SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # Register before exec so dataclass forward-reference resolution works.
    sys.modules.setdefault("mutate_scopes", module)
    spec.loader.exec_module(module)
    return module


def _kfilter_matches(name: str, kfilter: str) -> bool:
    """Cheap pytest ``-k`` substring check for the syntax mutate scopes use.

    Splits on the boolean ``or`` keyword (the only operator currently used
    in ``scripts/mutate_scopes.py``) and substring-matches each term. The
    assertion below will fail loudly the moment a scope adopts unsupported
    syntax, which is the right tripwire.
    """
    return any(term.strip() and term.strip() in name for term in kfilter.split(" or "))


@pytest.mark.spec("TEST-004")
def test_async_extended_scopes_use_explicit_filter() -> None:
    """Every async-extended scope must declare an explicit ``-k`` filter.

    The completeness check below assumes per-fixture verification via
    ``-k`` substring match. A scope with ``filter is None`` would
    short-circuit that check to "covered" for every fixture without
    actually parametrising over them — defeating the guard. If a filter-
    less scope is genuinely required in the future, extend the predicate
    in ``test_every_async_fixture_matches_an_async_extended_scope`` with
    explicit fixture-list verification before lifting this assertion.
    """
    scopes = _load_manifest().SCOPES
    filterless = [
        name
        for name, scope in scopes.items()
        if any("test_async_extended.py" in t for t in scope.tests) and scope.filter is None
    ]
    assert not filterless, (
        f"async-extended scopes without an explicit `-k` filter: {filterless}. "
        "See the docstring for why this breaks the coverage guard."
    )


@pytest.mark.spec("TEST-004")
def test_every_async_fixture_matches_an_async_extended_scope() -> None:
    manifest = _load_manifest()
    scopes = manifest.SCOPES

    async_extended_scopes = [
        (name, scope) for name, scope in scopes.items() if any("test_async_extended.py" in t for t in scope.tests)
    ]
    assert async_extended_scopes, (
        "no scope in scripts/mutate_scopes.py runs test_async_extended.py; async fixtures cannot be mutation-tested"
    )

    uncovered: list[str] = []
    for f in all_fixtures():
        if not f.is_async:
            continue
        # Stage 3 (real-live cloud) fixtures are exempt: mutation testing
        # against a real cloud account is too slow and too costly to run in
        # CI, and the fixture skips in default-stage runs anyway. The guard
        # still catches any new Stage 1/Stage 2 async fixture that lacks a
        # mutation scope, which is its actual intent.
        if f.stage >= 3:
            continue
        # Replay fixtures whose cassettes have not been recorded yet skip
        # every test, so they are intentionally excluded from the
        # async-extended scopes (a scope built around them aborts the gremlins
        # baseline with 'No data was collected', exit 3). Exempt them here in
        # lockstep with ``mutate_scopes._async_extended_runnable``; the
        # exemption self-lifts once cassettes land (graph: BK-260).
        if f.kind == "replay" and not manifest._cassettes_recorded(f.backend):
            continue
        # The companion test above asserts every async-extended scope has a
        # non-None filter, so the substring match is the only path that
        # counts as coverage. Do not relax this without revisiting that test.
        if not any(
            scope.filter is not None and _kfilter_matches(f.name, scope.filter) for _, scope in async_extended_scopes
        ):
            uncovered.append(f.name)

    assert not uncovered, (
        "async fixtures missing from any conformance-async-extended-* scope: "
        f"{uncovered}. Add a scope in scripts/mutate_scopes.py whose `-k` "
        "filter substring-matches the fixture name."
    )


@pytest.mark.spec("TEST-004")
def test_async_extended_scopes_select_a_runnable_fixture() -> None:
    """Every async-extended scope must select at least one fixture that
    actually executes.

    A scope whose ``-k`` filter matches only fixtures that skip — e.g. a
    ``kind="replay"`` fixture whose cassettes have not been recorded yet —
    leaves the pytest-gremlins baseline pass with no coverage, which aborts
    the shard (``CoverageWarning: No data was collected``, exit 3). This is
    how the weekly ``conformance-async-extended-graph`` shard failed while
    ``graph_replay`` had no cassettes (BK-260).

    The check is derived, so it self-heals: once a backend's cassettes land,
    ``_cassettes_recorded`` flips and the scope is expected to reappear (the
    companion completeness guard then requires it).
    """
    manifest = _load_manifest()
    scopes = manifest.SCOPES

    offenders: list[str] = []
    for name, scope in scopes.items():
        if not any("test_async_extended.py" in t for t in scope.tests):
            continue
        if scope.filter is None:
            continue
        matched = [f for f in all_fixtures() if f.is_async and f.stage <= 2 and _kfilter_matches(f.name, scope.filter)]
        runnable = [f for f in matched if f.kind != "replay" or manifest._cassettes_recorded(f.backend)]
        if not runnable:
            offenders.append(name)

    assert not offenders, (
        "async-extended scopes whose fixtures all skip (no runnable fixture): "
        f"{offenders}. A replay backend with no recorded cassettes must be excluded "
        "from scripts/mutate_scopes.py until its cassettes land, or the shard aborts "
        "with 'No data was collected' (exit 3)."
    )


# ---------------------------------------------------------------------------
# Bare-Python introspection contract (BUG-206 regression guard)
# ---------------------------------------------------------------------------
#
# The ``mutation.yml`` setup job runs ``python scripts/run_mutate.py
# --list-scopes`` (and ``--container-needs <name>``) on a vanilla
# ``actions/setup-python@v6`` runner — no project install, no pytest, no
# uv pip. The import chain ``run_mutate → mutate_scopes →
# tests.backends.fixtures._loader`` must therefore not pull in pytest or
# remote_store transitively, even though ``tests.backends.fixtures`` as a
# package depends on both at test time.


@pytest.mark.spec("TEST-004")
@pytest.mark.parametrize(
    "introspect_args",
    [
        pytest.param(["--list-scopes"], id="list-scopes"),
        pytest.param(["--container-needs", "minio"], id="needs-minio"),
        pytest.param(["--container-needs", "azurite"], id="needs-azurite"),
        pytest.param(["--container-needs", "sftp"], id="needs-sftp"),
    ],
)
def test_run_mutate_introspection_runs_without_pytest_or_remote_store(
    tmp_path: Path,
    introspect_args: list[str],
) -> None:
    wrapper = tmp_path / "block_and_run.py"
    wrapper.write_text(_BLOCK_WRAPPER)

    result = subprocess.run(
        [sys.executable, str(wrapper), str(_RUN_MUTATE), *introspect_args],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, (
        f"run_mutate.py {' '.join(introspect_args)} failed under the bare-Python env\n"
        f"--- stdout ---\n{result.stdout}\n"
        f"--- stderr ---\n{result.stderr}"
    )
    payload = json.loads(result.stdout)
    assert isinstance(payload, list)
    # An empty ``--list-scopes`` JSON array would feed an empty matrix to
    # ``mutation.yml`` and silently skip every mutation shard without CI
    # failure — the same class of silent skip this test exists to catch.
    # ``--container-needs`` is permissive: an empty list is the correct
    # answer when no scope needs that container (e.g., a future no-cloud
    # build).
    if introspect_args == ["--list-scopes"]:
        assert payload, "scope introspection returned an empty list; mutation matrix would be silently empty"
