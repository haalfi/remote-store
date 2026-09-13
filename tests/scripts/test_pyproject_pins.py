"""Every version boundary an extra in `pyproject.toml` has had to defend, in one table.

A pin in `[project.optional-dependencies]` is a claim about the range the code
actually runs across, and it has gone wrong in both directions: `httpx` needed a
ceiling it did not have (BUG-225), `paramiko` and `tenacity` had floors below the
API they call (BUG-283, BUG-284). Each incident arrived with its own test module
and its own copy of the same fixture, so this is the one driver
(`sdd/DRIFT-RULES.md` Rule 1) and a fourth pin costs a row rather than a file.

The extras a row applies to are **derived, not listed**: every extra declaring
the package is asserted, so a new extra picking up `httpx` at a weaker pin is
covered the day it is written. That is the half the superseded
`test_pyproject_httpx_cap.py` hard-coded.

Each row names the derivation its boundary came from — an upstream changelog
entry or a recorded run — checked when the row was written rather than recalled
(`CLAUDE.md` principle 9).

Bounds
======

* A row asserts the **measured** boundary, not the margin a floor may carry for
  policy. `tenacity` is pinned at 8.0.1 because that is the first release
  declaring `requires_python`; 6.1.0 is where the API works. Lowering the floor
  to 6.1.0 would still pass this test, and the reason to hold 8.0.1 lives in the
  `pyproject.toml` comment, not here.
* Boundaries are fixed strings. Nothing re-derives them at run time, so a *new*
  API the code starts calling needs a new row; this cannot notice one.
* It reads declarations only. That the installed package behaves as its version
  promises is the conformance suite's claim, not this file's.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

try:
    import tomllib
except ImportError:  # pragma: no cover — py3.10 fallback
    import tomli as tomllib  # type: ignore[no-redef]

from packaging.requirements import Requirement

ROOT = Path(__file__).resolve().parent.parent.parent


@dataclass(frozen=True)
class Pin:
    package: str
    must_reject: tuple[str, ...]
    must_keep: tuple[str, ...]
    why: str


_PINS: tuple[Pin, ...] = (
    Pin(
        package="httpx",
        # The 1.0 pre-release line is a wholesale client-API rewrite: it drops
        # AsyncClient, TransportError and DecodingError, the surface the async
        # graph backend and the [httpx] adapter are built on. An unbounded >=
        # let the drift guard's --pre resolution pull 1.0.dev3 and break the
        # graph import at module load. Derivation: BUG-225, from that run.
        # Lifting the cap to a real 1.0 port is ID-229.
        must_reject=("1.0.dev3", "1.0rc1", "1.0", "1.1"),
        must_keep=("0.24.0", "0.28.1"),
        why="the httpx 1.0 line rewrites the client API we use (BUG-225)",
    ),
    Pin(
        package="paramiko",
        # SFTPBackend._connect passes channel_timeout= to SSHClient.connect.
        # Derivation: paramiko's changelog puts that keyword under 3.1.0
        # (2023-03-10) — "Add an explicit ``channel_timeout`` keyword argument
        # to paramiko.client.SSHClient.connect". BUG-204 read it as 3.0 and set
        # the floor there; BUG-283 corrected it. No ceiling by design (BK-198).
        must_reject=("2.12.0", "3.0.0"),
        must_keep=("3.1.0", "4.0.0", "5.0.0"),
        why="channel_timeout= starts at paramiko 3.1.0 (BUG-283)",
    ),
    Pin(
        package="tenacity",
        # SFTPBackend._connect builds before_sleep_log(...) and
        # wait_exponential(min=...). Derivation: BUG-284 ran that exact
        # construction against each release in a clean venv, on Python 3.10 and
        # 3.11. Each rejected version failed on at least one supported Python:
        #   4.0.0  tenacity/async.py is a SyntaxError on any Python >= 3.7
        #   5.0.1  wait_exponential has no min= (it lands in 5.0.2)
        #   6.0.0  @asyncio.coroutine, removed in Python 3.11 (works on 3.10)
        # 6.1.0 is the first release that works on every supported Python; the
        # floor sits at 8.0.1 for the reason in pyproject.toml.
        must_reject=("4.0.0", "5.0.1", "6.0.0"),
        must_keep=("8.0.1", "9.1.2"),
        why="the connect retry needs before_sleep_log and wait_exponential(min=) (BUG-284)",
    ),
    Pin(
        package="sqlalchemy",
        # Derivation: BUG-285 installed each 2.0.x into a clean venv on Python
        # 3.10 and 3.13 and imported it. Every release through 2.0.30 installs on
        # 3.13 (the wheel is universal) and then dies at import — 2.0.0-2.0.29 on
        # `Class SQLCoreOperations directly inherits TypingOnly but has
        # additional attributes {'__static_attributes__', '__firstlineno__'}`,
        # 2.0.30 on `Can't replace canonical symbol for '__firstlineno__'`. Both
        # are 3.13's new class attributes; 2.0.31 is the first release that knows
        # about them. All of 2.0.x is fine on 3.10, which is why nothing here saw it.
        must_reject=("2.0.0", "2.0.30"),
        must_keep=("2.0.31", "2.1.0"),
        why="SQLAlchemy below 2.0.31 fails at import on Python 3.13 (BUG-285)",
    ),
    Pin(
        package="urllib3",
        # Same derivation. 1.26.0-1.26.4 install on 3.13 and then raise
        # `ModuleNotFoundError: No module named 'urllib3.packages.six.moves'` —
        # the vendored six shim's meta-path importer, which stopped working in
        # the 3.12 line. 1.26.5 is the first release that imports.
        must_reject=("1.26.0", "1.26.4"),
        must_keep=("1.26.5", "2.0.0"),
        why="urllib3 below 1.26.5 fails at import on Python 3.13 (BUG-285)",
    ),
    Pin(
        package="dagster",
        # ext/dagster.py imports TruncatingCloudStorageComputeLogManager from
        # dagster._core.storage.cloud_storage_compute_log_manager. Derivation:
        # BUG-285 walked every 1.9.x and 1.10.x release; the symbol first appears
        # in 1.10.18. Everything below installs on 3.10-3.12 and raises
        # ImportError at `import remote_store.ext.dagster`. This one is not
        # Python-dependent — the declared >=1.9 was wrong on every interpreter.
        must_reject=("1.9.0", "1.10.17"),
        must_keep=("1.10.18", "1.12.0"),
        why="TruncatingCloudStorageComputeLogManager starts at dagster 1.10.18 (BUG-285)",
    ),
)


@pytest.fixture(scope="module")
def extras() -> dict[str, list[Requirement]]:
    """Every extra's parsed requirements, from `pyproject.toml`."""
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return {name: [Requirement(r) for r in reqs] for name, reqs in data["project"]["optional-dependencies"].items()}


def _declaring(extras: dict[str, list[Requirement]], package: str) -> list[tuple[str, Requirement]]:
    """(extra, requirement) for every extra declaring *package*. Derived, not listed."""
    return [(name, req) for name, reqs in extras.items() for req in reqs if req.name == package]


@pytest.mark.parametrize("pin", _PINS, ids=lambda p: p.package)
def test_some_extra_declares_the_pinned_package(pin, extras):
    """A row for a package nothing declares is a row that silently tests nothing."""
    assert _declaring(extras, pin.package), f"no extra declares {pin.package!r}; the {pin.package} row is dead"


@pytest.mark.parametrize("pin", _PINS, ids=lambda p: p.package)
def test_every_declaring_extra_rejects_the_unsupported_versions(pin, extras):
    for extra, req in _declaring(extras, pin.package):
        for bad in pin.must_reject:
            # prereleases=True mirrors the drift guard's --pre resolution: a
            # bound must exclude 1.0.dev* even when pre-releases are eligible.
            assert not req.specifier.contains(bad, prereleases=True), (
                f"extra {extra!r}: {pin.package} specifier {str(req.specifier)!r} must reject {bad} — {pin.why}"
            )


@pytest.mark.parametrize("pin", _PINS, ids=lambda p: p.package)
def test_every_declaring_extra_keeps_the_supported_versions(pin, extras):
    for extra, req in _declaring(extras, pin.package):
        for good in pin.must_keep:
            assert req.specifier.contains(good, prereleases=True), (
                f"extra {extra!r}: {pin.package} specifier {str(req.specifier)!r} must keep {good} — {pin.why}"
            )
