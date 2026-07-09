"""BUG-225: the httpx-using extras must cap out httpx's 1.0 pre-release rewrite.

httpx's experimental `1.0.dev*` line is a wholesale client-API rewrite — it
drops `AsyncClient`, `TransportError`, `DecodingError`, and the rest of the
surface the async graph backend (`remote_store.aio.backends._graph`) and the
`[httpx]` HTTP adapter are built on. An unbounded `httpx>=0.24.0` let the drift
guard's `--pre` resolution pull `1.0.dev3` and break the graph import at module
load. The `graph` and `httpx` extras must therefore carry an upper bound that
excludes the whole 1.0 line (dev / rc / final) until ID-229 evaluates a real
1.0 port. This test pins that intent so a careless `>=`-only bump reintroduces
the break loudly instead of at the next drift run.
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

# Versions the cap must reject (the httpx 1.0 pre-release rewrite and 1.0 GA,
# which we have not ported to) and keep (the supported 0.2x stable line).
_MUST_REJECT = ("1.0.dev3", "1.0rc1", "1.0", "1.1")
_MUST_KEEP = ("0.24.0", "0.28.1")


@pytest.fixture(scope="module")
def httpx_requirements() -> dict[str, Requirement]:
    """The httpx `Requirement` from each extra that declares one."""
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    extras = data["project"]["optional-dependencies"]
    out: dict[str, Requirement] = {}
    for extra in ("graph", "httpx"):
        reqs = [Requirement(r) for r in extras[extra]]
        httpx_reqs = [r for r in reqs if r.name == "httpx"]
        assert httpx_reqs, f"extra {extra!r} must declare an httpx requirement"
        out[extra] = httpx_reqs[0]
    return out


@pytest.mark.parametrize("extra", ["graph", "httpx"])
def test_extra_caps_out_httpx_1_0(extra, httpx_requirements):
    spec = httpx_requirements[extra].specifier
    # prereleases=True mirrors the drift guard's `--pre` resolution: the cap
    # must exclude 1.0.dev* even when pre-releases are eligible.
    for bad in _MUST_REJECT:
        assert not spec.contains(bad, prereleases=True), (
            f"extra {extra!r} httpx specifier {str(spec)!r} must reject {bad} (BUG-225)"
        )
    for good in _MUST_KEEP:
        assert spec.contains(good, prereleases=True), f"extra {extra!r} httpx specifier {str(spec)!r} must keep {good}"
