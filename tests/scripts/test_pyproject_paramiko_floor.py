"""BUG-283: the `[sftp]` extra's paramiko floor must be where the API it uses starts.

`SFTPBackend._connect` passes `channel_timeout=` to `paramiko.SSHClient.connect`
(`src/remote_store/backends/_sftp.py`). Paramiko's own changelog puts that keyword
in **3.1.0** (2023-03-10): "Add an explicit ``channel_timeout`` keyword argument to
`paramiko.client.SSHClient.connect`". BUG-204 read it as 3.0 and set the floor
there, so `paramiko==3.0.0` resolved and then raised `TypeError: connect() got an
unexpected keyword argument 'channel_timeout'` on the first connect.

Why the existing guard could not catch it: `tests/backends/sftp/test_config.py`
introspects the *installed* paramiko, which is the latest release in every
environment that runs it. That proves the keyword exists somewhere at or above the
floor, never that the floor is where it starts. This test reads the declared
specifier instead, so the two together bracket the range.

Bound: this asserts the floor against versions named here, derived once from the
upstream changelog. It does not re-derive the introduction version at run time and
will not notice a *second* keyword the backend starts using.
"""

from __future__ import annotations

from pathlib import Path

import pytest

try:
    import tomllib
except ImportError:  # pragma: no cover — py3.10 fallback
    import tomli as tomllib  # type: ignore[no-redef]

from packaging.requirements import Requirement

ROOT = Path(__file__).resolve().parent.parent.parent

# The last release without `channel_timeout` (3.0.0) and the first with it (3.1.0).
_MUST_REJECT = ("2.12.0", "3.0.0")
_MUST_KEEP = ("3.1.0", "4.0.0", "5.0.0")


@pytest.fixture(scope="module")
def paramiko_requirement() -> Requirement:
    """The paramiko `Requirement` declared by the `[sftp]` extra."""
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    reqs = [Requirement(r) for r in data["project"]["optional-dependencies"]["sftp"]]
    paramiko_reqs = [r for r in reqs if r.name == "paramiko"]
    assert paramiko_reqs, "extra 'sftp' must declare a paramiko requirement"
    return paramiko_reqs[0]


@pytest.mark.parametrize("bad", _MUST_REJECT)
def test_sftp_extra_rejects_paramiko_without_channel_timeout(bad, paramiko_requirement):
    spec = paramiko_requirement.specifier
    assert not spec.contains(bad, prereleases=True), (
        f"[sftp] paramiko specifier {str(spec)!r} must reject {bad}: "
        f"channel_timeout= landed in paramiko 3.1.0 (BUG-283)"
    )


@pytest.mark.parametrize("good", _MUST_KEEP)
def test_sftp_extra_keeps_paramiko_with_channel_timeout(good, paramiko_requirement):
    spec = paramiko_requirement.specifier
    assert spec.contains(good, prereleases=True), (
        f"[sftp] paramiko specifier {str(spec)!r} must keep {good}: the extra carries no upper bound by design (BK-198)"
    )
