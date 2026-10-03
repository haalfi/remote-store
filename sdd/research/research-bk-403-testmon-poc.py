"""Seeded-change driver for the BK-403 pytest-testmon PoC.

Evidence for research-bk-403-testmon-poc.md; not a gate, not shipped.

Setup (all under the gitignored ./tmp/):
  git worktree add --detach tmp/poc-wt <commit>
  uv venv -p 3.13 tmp/venv313
  VIRTUAL_ENV=tmp/venv313 uv pip install -e "tmp/poc-wt[dev]" pytest-testmon==2.2.0
  TESTMON_DATAFILE=tmp/poc/map.testmondata tmp/venv313/bin/python -m pytest \
      --stage=1 -p no:benchmark --testmon -n 4          # run from tmp/poc-wt

Usage:
  python research-bk-403-testmon-poc.py <py> <pristine-map> <seed>[,<seed>...] | all
  POC_EXTRA="-n 4" adds arguments to the selected run.
  POC_CONFIRM_ONLY=1 runs only step (1) for each seed and prints the result.

Per seed: apply a one-line edit in the worktree, confirm the known test fails
with testmon off, run a ``--testmon-forceselect`` pass against a fresh copy of
the pristine map, record from the JUnit report whether the known test ran,
then revert. One JSON line per seed goes to tmp/poc/results.jsonl.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WT = ROOT / "tmp" / "poc-wt"
POC = ROOT / "tmp" / "poc"

# id -> (file, old line text, new line text, known failing test nodeid)
SEEDS: dict[str, tuple[str, str, str, str]] = {
    "conftest-fixture": (
        "tests/conftest.py",
        "        self._caps = CapabilitySet(set(Capability) - exclude)",
        "        self._caps = CapabilitySet(set(Capability))",
        "tests/test_store.py::test_supports_atomic_move_false_when_backend_lacks_it",
    ),
    "conftest-hypothesis": (
        "tests/conftest.py",
        'settings.register_profile("dev", max_examples=50, deadline=None)',
        'settings.register_profile("dev", max_examples=50, deadline=0.01)',
        "tests/test_pbt_properties.py::test_idempotent",
    ),
    "fixture-factory": (
        "tests/backends/fixtures/memory.py",
        "    return MemoryBackend()",
        "    return None  # type: ignore[return-value]",
        "tests/backends/conformance/::[memory]",
    ),
    "fixture-toml": (
        "tests/backends/fixtures/fixtures.toml",
        '[fixture.memory]\nbackend   = "memory"',
        '[fixture.memory]\nlive_opt_in_env = "RS_POC"\nbackend   = "memory"',
        "tests/backends/fixtures/test_registry.py::test_live_env_fields_parse_on_descriptor",
    ),
    "core-path": (
        "src/remote_store/_path.py",
        '        if "\\0" in raw:',
        '        if "\\0" in raw and False:',
        "tests/test_path.py::test_null_byte_rejected",
    ),
    "init-reexport": (
        "src/remote_store/__init__.py",
        '    "Store",',
        '    "Store2",',
        "tests/test_api_coverage.py::test_",
    ),
    "registry-text": (
        "src/remote_store/_registry.py",
        '        register_backend("memory", MemoryBackend)',
        "        register_backend('memory', MemoryBackend)",
        "tests/scripts/test_gen_features.py::TestRegistryOrder::test_local_and_memory_present",
    ),
    "placement-ast": (
        "src/remote_store/backends/_azure.py",
        "",  # append mode
        "class MemoryBackend: ...",
        "tests/scripts/test_check_test_placement.py::TestDiscoverBannedBackendNames::test_excludes_in_process_backends",
    ),
    "cassette-yaml": (
        "tests/backends/cassettes/azure/TestBackendExists.test_true_after_write[azure].yaml",
        "",  # append mode
        "# poc-seed owner@contoso.com",
        "tests/backends/fixtures/test_cassettes.py::test_committed_cassettes_carry_no_forbidden_pii",
    ),
    "pyproject-pin": (
        "pyproject.toml",
        'httpx = ["httpx>=0.24.0,<1.0"]',
        'httpx = ["httpx>=0.24.0"]',
        "tests/scripts/test_pyproject_pins.py::test_every_declaring_extra_rejects_the_unsupported_versions",
    ),
    "generated-features": (
        "FEATURES.md",
        "| `memory` | `MemoryBackend` | — | All except `GLOB`, `LAZY_READ` |",
        "| `memory` | `MemoryBackendX` | — | All except `GLOB`, `LAZY_READ` |",
        "tests/scripts/test_gen_features.py::test_features_md_is_up_to_date",
    ),
    "backend-sftp-const": (
        "src/remote_store/backends/_sftp.py",
        '_PEM_SEPARATOR = "-----"',
        '_PEM_SEPARATOR = "----"',
        "tests/backends/sftp/test_config.py::test_sanitize_valid_pem",
    ),
    "backend-sftp": (
        "src/remote_store/backends/_sftp.py",
        '    parts[2] = payload.replace(non_base64_chars[0], "\\n")',
        '    parts[2] = payload.replace(non_base64_chars[0], "\\r\\n")',
        "tests/backends/sftp/test_config.py::test_sanitize_valid_pem",
    ),
}


def pytest(py: str, args: list[str], env_extra: dict[str, str]) -> tuple[int, float, str]:
    exe = ROOT / "tmp" / f"venv{py.replace('.', '')}" / "bin" / "python"
    env = {**os.environ, **env_extra}
    t0 = time.monotonic()
    r = subprocess.run(
        [exe, "-m", "pytest", "--stage=1", "-p", "no:benchmark", "-q", "--no-header", *args],
        cwd=WT,
        env=env,
        capture_output=True,
        text=True,
    )
    return r.returncode, time.monotonic() - t0, r.stdout[-3000:] + r.stderr[-2000:]


def junit_ids(path: Path) -> list[tuple[str, str]]:
    """(nodeid-ish, outcome) per testcase."""
    out = []
    for tc in ET.parse(path).getroot().iter("testcase"):
        cls = tc.get("classname", "").replace(".", "/")
        ident = f"{cls}::{tc.get('name')}"
        outcome = "passed"
        for child in tc:
            if child.tag in ("failure", "error"):
                outcome = "failed"
            elif child.tag == "skipped":
                outcome = "skipped"
        out.append((ident, outcome))
    return out


def apply(seed: tuple[str, str, str, str]) -> tuple[Path, str]:
    rel, old, new, _ = seed
    f = WT / rel
    orig = f.read_text(encoding="utf-8")
    if old == "":
        text = orig.rstrip("\n") + "\n" + new + "\n"
    else:
        assert orig.count(old + "\n") == 1, f"{rel}: anchor not unique: {old!r}"
        text = orig.replace(old + "\n", new + "\n")
    f.write_text(text, encoding="utf-8")
    return f, orig


def main() -> None:
    py, pristine, which = sys.argv[1], Path(sys.argv[2]), sys.argv[3]
    ids = list(SEEDS) if which == "all" else which.split(",")
    for sid in ids:
        seed = SEEDS[sid]
        known = seed[3]
        f, orig = apply(seed)
        try:
            # (1) Confirm the known test itself fails with testmon off: exit 1
            # (tests failed) AND a matching JUnit case failed. Exit 2-5
            # (collection/usage/internal error, nothing collected) is not a
            # confirmation; a seed that breaks import tests nothing.
            kpath, ksub = known.split("::")[0], known.split("::")[-1]
            kjunit = POC / f"confirm-{sid}-{py}.xml"
            rc_known, _, out_known = pytest(
                py, ["-p", "no:testmon", kpath, "-k", ksub.strip("[]"), f"--junitxml={kjunit}"], {}
            )
            kcases = junit_ids(kjunit) if kjunit.exists() else []
            confirmed = rc_known == 1 and any(o == "failed" and ksub.strip("[]") in i for i, o in kcases)
            if os.environ.get("POC_CONFIRM_ONLY"):
                rec = {
                    "seed": sid,
                    "py": py,
                    "confirm_rc": rc_known,
                    "confirmed": confirmed,
                    "known_cases_failed": sum(1 for _, o in kcases if o == "failed"),
                }
                print(json.dumps(rec), flush=True)
                continue
            # (2) testmon-selected run on a fresh copy of the pristine map.
            data = POC / f"seed-{sid}-{py}.testmondata"
            for side in ("-wal", "-shm"):  # stale sqlite sidecars corrupt a fresh copy
                Path(f"{data}{side}").unlink(missing_ok=True)
            shutil.copy(pristine, data)
            junit = POC / f"seed-{sid}-{py}.xml"
            rc, wall, out = pytest(
                py,
                [
                    "--testmon-forceselect",
                    f"--junitxml={junit}",
                    *os.environ.get("POC_EXTRA", "").split(),
                ],
                {"TESTMON_DATAFILE": str(data)},
            )
            ran = junit_ids(junit) if junit.exists() else []
            kfile = known.split("::")[0]
            kname = known.split("::")[-1] if "::" in known else None
            hits = [r for r in ran if r[0].startswith(kfile.removesuffix(".py")) and (kname is None or kname in r[0])]
            rec = {
                "seed": sid,
                "py": py,
                "file": seed[0],
                "known": known,
                "known_fails_without_testmon": confirmed,
                "tests_run": len(ran),
                "tests_executed": sum(1 for r in ran if r[1] != "skipped"),
                "failed": sum(1 for r in ran if r[1] == "failed"),
                "known_selected": bool(hits),
                "known_failed_in_selected": any(h[1] == "failed" for h in hits),
                "wall_s": round(wall, 1),
                "rc": rc,
                "tail": out.strip().splitlines()[-1] if out.strip() else "",
            }
            if not confirmed:
                rec["known_tail"] = out_known.strip().splitlines()[-1]
            print(json.dumps(rec), flush=True)
            with (POC / "results.jsonl").open("a") as fh:
                fh.write(json.dumps(rec) + "\n")
        finally:
            f.write_text(orig, encoding="utf-8")


if __name__ == "__main__":
    main()
