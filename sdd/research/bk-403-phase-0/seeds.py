"""Seed run for RFC-0019 Phase 0, through the PoC driver's seeds and edit logic.

Throwaway research. The 13 PoC seeds come from
``../bk-403-testmon-poc/driver.py`` (``SEEDS``, unchanged); D7's additions
and the D6 job seeds are below. Each seed pins, per variant, its mode
(``SELECTED`` or ``FULL``), and may pin jobs that must or must not run and
tests the selection must also hold.

Per seed, three steps (the PoC driver's, with the selector in place of
testmon):

1. **Select** (static, seconds): apply the edit to an overlay of ``HEAD`` and
   run both variants. Assert the known test is contained, the pinned mode is
   met, and the pinned jobs and extra tests.
2. **Confirm** (``--confirm``): apply the edit in the seed worktree
   ``tmp/p0-seed-wt`` and run the known test alone; confirmed means pytest
   exited 1 and the known test's own JUnit case failed (PoC definition).
3. **Selected run** (``--confirm``, SELECTED results only): run pytest over the
   selection's target files in the seed worktree and record whether the known
   test ran and failed. Allowlists are not applied at run time (the registry
   allowlist is Phase 1 work), so this run is a superset of the selection.

Run under the hatch env so pytest is the project's:
  hatch run python sdd/research/bk-403-phase-0/seeds.py [--confirm] [--only id,...] --out <jsonl>
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

from metrics import contains
from p0tree import ROOT, OverlayTree, Tree
from selector import Readers, select

HERE = Path(__file__).resolve().parent
WT = ROOT / "tmp" / "p0-seed-wt"
OUT = ROOT / "tmp" / "p0-seeds"

_spec = importlib.util.spec_from_file_location("poc_driver", HERE.parent / "bk-403-testmon-poc" / "driver.py")
assert _spec
assert _spec.loader
_poc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_poc)


@dataclass
class Seed:
    sid: str
    edits: list[tuple[str, str, str]]  # (file, old line, new line); old "" appends; old None creates
    known: str | None  # known failing test (file::name-fragment), or None for mode/job-only seeds
    modes: dict[str, str]  # variant -> "SELECTED" | "FULL"
    jobs_present: dict[str, list[str]] = field(default_factory=dict)
    jobs_absent: dict[str, list[str]] = field(default_factory=dict)
    also_contains: dict[str, list[str]] = field(default_factory=dict)
    origin: str = "D7"


BOTH_FULL = {"pilot": "FULL", "precision": "FULL"}
BOTH_SEL = {"pilot": "SELECTED", "precision": "SELECTED"}
PREC_SEL = {"pilot": "FULL", "precision": "SELECTED"}

# Pinned modes of the PoC seeds: the RFC's hand mapping for the pilot (D7, 11
# FULL / 2 SELECTED), and the precision rows of D5 for the precision variant.
POC_MODES = {
    "conftest-fixture": BOTH_FULL,
    "conftest-hypothesis": BOTH_FULL,
    "fixture-factory": PREC_SEL,
    "fixture-toml": PREC_SEL,
    "core-path": BOTH_FULL,
    "init-reexport": BOTH_FULL,
    "registry-text": PREC_SEL,
    "placement-ast": PREC_SEL,
    "cassette-yaml": BOTH_SEL,
    "pyproject-pin": BOTH_FULL,
    "generated-features": BOTH_SEL,
    "backend-sftp-const": PREC_SEL,
    "backend-sftp": PREC_SEL,
}

SEEDS: list[Seed] = [
    Seed(sid, [(f, old, new)], known, POC_MODES[sid], origin="PoC") for sid, (f, old, new, known) in _poc.SEEDS.items()
]
SEEDS[[s.sid for s in SEEDS].index("cassette-yaml")].jobs_present = {
    "pilot": ["test-cassette-pii"],
    "precision": ["test-cassette-pii"],
}
SEEDS[[s.sid for s in SEEDS].index("cassette-yaml")].jobs_absent = {
    "pilot": ["test-primary-sftp", "tooling-tests"],
    "precision": ["test-primary-sftp", "tooling-tests"],
}

SEEDS += [
    Seed(
        "strict-fixture",
        [
            (
                "tests/backends/fixtures/s3_moto.py",
                "            factory=_make_factory(_meta.rejects_write_under_file_ancestor),",
                "            factory=_make_factory(False),",
            )
        ],
        "tests/backends/conformance/test_errors.py::test_open_atomic_under_file_ancestor_raises_invalid_path[s3_moto_strict]",  # noqa: E501
        PREC_SEL,
    ),
    Seed(
        "test-module-imported",
        [
            (
                "tests/backends/conformance/test_atomic.py",
                '    "path": None,',
                '    "path": Capability.GLOB,',
            )
        ],
        "tests/backends/conformance/test_async_extended.py::test_populated_field_implies_declared_capability",
        PREC_SEL,
    ),
    Seed(
        "string-import",
        [
            (
                "src/remote_store/backends/_http.py",
                "_CAPABILITIES = CapabilitySet({Capability.READ, Capability.METADATA, Capability.LAZY_READ})",
                "_CAPABILITIES = CapabilitySet(set())",
            )
        ],
        "tests/test_capabilities.py::test_class_attr_no_instantiation[remote_store.backends._http-ReadOnlyHttpBackend-None]",  # noqa: E501
        PREC_SEL,
    ),
    Seed(
        "example-assertion",
        [
            (
                "examples/getting_started/quickstart.py",
                "    store = Store(LocalBackend(root=root))",
                '    store = Store(LocalBackend(root=root + "-moved"))',
            )
        ],
        "tests/test_examples.py::test_demo[direct]",
        BOTH_SEL,
        jobs_present={"pilot": ["examples"], "precision": ["examples"]},
    ),
    Seed(
        "pii-sweep-edit",
        [
            (
                "tests/backends/fixtures/test_cassettes.py",
                '        assert files, f"no committed cassettes under {profile.cassette_dir}; sweep would be vacuous"',
                '        assert not files, f"no committed cassettes under {profile.cassette_dir}; sweep would be vacuous"',  # noqa: E501
            )
        ],
        "tests/backends/fixtures/test_cassettes.py::test_committed_cassettes_carry_no_forbidden_pii",
        BOTH_SEL,
        jobs_present={"pilot": ["test-cassette-pii"], "precision": ["test-cassette-pii"]},
    ),
    Seed(
        "conftest-session-hook",
        [
            (
                "tests/backends/azure/conftest.py",
                "    install_missing_cassette_guard(config)",
                "    pass  # poc-seed: guard no longer armed here",
            )
        ],
        None,
        BOTH_FULL,
    ),
    Seed(
        "script-own-test",
        [
            (
                "scripts/check_hatch_python.py",
                '        return f"pyproject.toml [tool.hatch.envs.default] sets no python; .python-version is {primary!r}"',  # noqa: E501
                '        return f"pyproject.toml [tool.hatch.envs.default] sets no pin; .python-version is {primary!r}"',  # noqa: E501
            )
        ],
        "tests/scripts/test_check_hatch_python.py::test_missing_pin_is_reported",
        BOTH_SEL,
        also_contains={
            "pilot": ["tests/scripts/test_check_traces.py"],
            "precision": ["tests/scripts/test_check_traces.py"],
        },
    ),
    Seed(
        "registry-consumer",
        [
            (
                "tests/backends/fixtures/azure_replay_hns.py",
                "    return AzureBackend(container=FAKE_FILESYSTEM, hns=True, connection_string=FAKE_CONN_STR)",
                "    return AzureBackend(container=FAKE_FILESYSTEM, hns=False, connection_string=FAKE_CONN_STR)",
            )
        ],
        "tests/backends/azure/test_live_hns.py::azure_replay_hns",
        PREC_SEL,
    ),
    # ---- D6 job seeds: one empty-survival case per test job, and the path rules
    Seed(
        "job-e2e-os-sensitive",
        [("tests/e2e/test_async_streaming_integrity.py", "", "# poc-seed")],
        None,
        BOTH_SEL,
        jobs_present={v: ["e2e"] for v in ("pilot", "precision")},
        # tooling-tests is not pinned absent: test_check_rst_roles and two other
        # tests/scripts linters read every tests/ module (layer 4). Its
        # empty-survival case is pinned by cassette-yaml.
        jobs_absent={v: ["test-cross-platform", "test", "test-primary"] for v in ("pilot", "precision")},
    ),
    Seed(
        "job-scripts-only",
        [("tests/scripts/test_check_hatch_python.py", "", "# poc-seed")],
        None,
        BOTH_SEL,
        jobs_present={v: ["tooling-tests"] for v in ("pilot", "precision")},
        jobs_absent={v: ["test", "test-primary", "e2e", "test-cassette-pii"] for v in ("pilot", "precision")},
    ),
    Seed(
        "job-core-test",
        [("tests/test_path.py", "", "# poc-seed")],
        None,
        BOTH_SEL,
        jobs_present={v: ["test", "test-primary", "test-cross-platform"] for v in ("pilot", "precision")},
        jobs_absent={
            v: ["test-cassette-pii", "pyarrow-major-check", "test-primary-sftp", "e2e"] for v in ("pilot", "precision")
        },
    ),
    Seed(
        "job-notebook",
        [("examples/notebooks/01_getting_started.ipynb", "", " ")],
        None,
        BOTH_SEL,
        jobs_present={v: ["notebooks"] for v in ("pilot", "precision")},
        jobs_absent={v: ["test", "examples"] for v in ("pilot", "precision")},
    ),
    Seed(
        "job-package",
        [
            ("src/remote_store/ext/_p0seed.py", None, "VALUE = 1"),
            (
                "src/remote_store/ext/batch.py",
                "",
                "def _p0seed() -> int:\n    from remote_store.ext._p0seed import VALUE\n\n    return VALUE",
            ),
        ],
        None,
        PREC_SEL,
        jobs_present={"precision": ["package"]},
    ),
]


def apply_overlay(base: Tree, seed: Seed) -> tuple[OverlayTree, list[tuple[str, str]]]:
    over: dict[str, bytes | None] = {}
    changes = []
    for f, old, new in seed.edits:
        if old is None:
            over[f] = (new + "\n").encode()
            changes.append(("A", f))
            continue
        orig = (base.read(f) or b"").decode("utf-8")
        if old == "":
            text = orig.rstrip("\n") + "\n" + new + "\n"
        else:
            assert orig.count(old + "\n") == 1, f"{f}: anchor not unique: {old!r}"
            text = orig.replace(old + "\n", new + "\n")
        over[f] = text.encode("utf-8")
        changes.append(("M", f))
    return OverlayTree(base, over), changes


def run_pytest(args: list[str], junit: Path, workers: str = "0") -> tuple[int, list[tuple[str, str]], str]:
    env = {**os.environ, "PYTHONPATH": str(WT / "src")}
    r = subprocess.run(
        [sys.executable, "-m", "pytest", "--stage=1", "-p", "no:benchmark", "-q", "--no-header", "-n", workers,
         f"--junitxml={junit}", *args],
        cwd=WT, env=env, capture_output=True, text=True,
    )  # fmt: skip
    cases = []
    if junit.exists():
        for tc in ET.parse(junit).getroot().iter("testcase"):
            ident = f"{tc.get('classname', '').replace('.', '/')}::{tc.get('name')}"
            outcome = "passed"
            for child in tc:
                if child.tag in ("failure", "error"):
                    outcome = "failed"
                elif child.tag == "skipped":
                    outcome = "skipped"
            cases.append((ident, outcome))
    return r.returncode, cases, (r.stdout[-1500:] + r.stderr[-800:])


def edit_worktree(seed: Seed) -> dict[Path, str | None]:
    saved: dict[Path, str | None] = {}
    for f, old, new in seed.edits:
        p = WT / f
        saved[p] = p.read_text(encoding="utf-8") if p.exists() else None
        if old is None:
            p.write_text(new + "\n", encoding="utf-8")
        elif old == "":
            p.write_text((saved[p] or "").rstrip("\n") + "\n" + new + "\n", encoding="utf-8")
        else:
            p.write_text((saved[p] or "").replace(old + "\n", new + "\n"), encoding="utf-8")
    return saved


def restore(saved: dict[Path, str | None]) -> None:
    for p, text in saved.items():
        if text is None:
            p.unlink(missing_ok=True)
        else:
            p.write_text(text, encoding="utf-8")


def known_matches(known: str, ident: str) -> bool:
    kfile, kname = known.split("::", 1)
    return ident.startswith(kfile.removesuffix(".py")) and kname in ident


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--confirm", action="store_true")
    ap.add_argument("--only")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    base = Tree("HEAD")
    readers = Readers.load()
    only = set(a.only.split(",")) if a.only else None
    with open(a.out, "w", encoding="utf-8") as fh:
        for seed in SEEDS:
            if only and seed.sid not in only:
                continue
            head, changes = apply_overlay(base, seed)
            rec: dict = {
                "seed": seed.sid,
                "origin": seed.origin,
                "edits": [e[0] for e in seed.edits],
                "known": seed.known,
            }
            results = {}
            for v in ("pilot", "precision"):
                res = select(base, head, changes, v, readers=readers)
                results[v] = res
                ok_mode = res.mode == seed.modes[v]
                ok_known = seed.known is None or contains(res, seed.known)
                missing_present = [j for j in seed.jobs_present.get(v, []) if j not in res.jobs]
                wrong_absent = [j for j in seed.jobs_absent.get(v, []) if j in res.jobs and res.mode != "FULL"]
                missing_also = [t for t in seed.also_contains.get(v, []) if not contains(res, t)]
                rec[v] = {
                    "mode": res.mode,
                    "pinned": seed.modes[v],
                    "mode_ok": ok_mode,
                    "known_contained": ok_known,
                    "jobs": sorted(res.jobs),
                    "jobs_ok": not missing_present and not wrong_absent,
                    "jobs_missing": missing_present,
                    "jobs_unexpected": wrong_absent,
                    "also_ok": not missing_also,
                    "full_reasons": res.full_reasons,
                    "targets": sorted(res.targets),
                    "pass": ok_mode and ok_known and not missing_present and not wrong_absent and not missing_also,
                }
            if a.confirm and seed.known:
                saved = edit_worktree(seed)
                try:
                    kfile, kname = seed.known.split("::", 1)
                    k = kname.replace("[", " ").replace("]", " ").replace("::", " ").split()
                    kexpr = " and ".join(x for x in k if x.isidentifier() or "_" in x)
                    rc, cases, tail = run_pytest(
                        [kfile, "-k", kexpr] if kexpr else [kfile], OUT / f"confirm-{seed.sid}.xml"
                    )
                    rec["confirm_rc"] = rc
                    rec["confirmed"] = rc == 1 and any(o == "failed" and known_matches(seed.known, i) for i, o in cases)
                    if not rec["confirmed"]:
                        rec["confirm_tail"] = tail.strip().splitlines()[-3:]
                    for v in ("pilot", "precision"):
                        res = results[v]
                        if res.mode != "SELECTED":
                            rec[v]["selected_run"] = "FULL: whole suite, containment by construction"
                            continue
                        targets = sorted(
                            t for t in res.targets if t.startswith("tests/") and not t.startswith("tests/e2e/")
                        )
                        if not targets:
                            rec[v]["selected_run"] = "no pytest targets"
                            continue
                        rc2, cases2, tail2 = run_pytest(targets, OUT / f"sel-{seed.sid}-{v}.xml", workers="6")
                        hits = [o for i, o in cases2 if known_matches(seed.known, i)]
                        rec[v]["selected_run"] = {
                            "rc": rc2,
                            "tests_run": len(cases2),
                            "known_ran": bool(hits),
                            "known_failed": "failed" in hits,
                        }
                finally:
                    restore(saved)
            fh.write(json.dumps(rec) + "\n")
            print(
                seed.sid,
                *(f"{v}:{rec[v]['mode']}{'' if rec[v]['pass'] else '!FAIL'}" for v in ("pilot", "precision")),
                f"confirmed={rec.get('confirmed', '-')}",
                flush=True,
            )


if __name__ == "__main__":
    main()
