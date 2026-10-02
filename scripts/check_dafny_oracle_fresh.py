#!/usr/bin/env python3
"""Check that the committed compiled oracle is what its Dafny sources compile to (ID-263).

``sdd/formal/MemoryBackend-py/`` is generated: ``scripts/dafny_translate.sh``
builds ``MemoryBackend.dfy`` (and the files it includes) to Python, then
``scripts/_dafny_classorder.py`` reorders ``module_.py``.  A non-ghost edit to
any of those sources that is not regenerated passes ``dafny verify``, and every
test that drives the oracle then exercises stale code.  This gate rebuilds the
oracle the same way and compares it with the committed tree, file by file.

Authority: the ``.dfy`` sources govern; ``MemoryBackend-py/`` is derived and is
fixed by regenerating, never by hand-editing (declared in
``sdd/formal/README.md`` § Compiled oracle).  ``DAFNY_VERSION`` in
``dafny_translate.sh`` is the toolchain pin: a different ``dafny`` on ``PATH``
is reported as skew and nothing is compared, since its output would differ for
reasons unrelated to the sources.

The source set is every ``sdd/formal/*.dfy``, copied as the wrapper copies it,
rather than a list of what ``MemoryBackend.dfy`` includes: the include closure
(``BackendContract.dfy``, ``RootPath.dfy``, and ``ResourceSafety.dfy`` through
``BackendContract.dfy``) is Dafny's to resolve, and a list here would be a
second copy of it to go stale.

The build verifies.  ``--no-verify`` is not an equivalent shortcut: measured on
dafny 4.11.0 it numbers loop labels differently (``_dafny.label("1")`` where the
verified build emits ``"0"``), so a non-verifying build reports drift on a
fresh tree.

Fails on (exit 1), each named rather than summarised (``sdd/DRIFT-RULES.md``
Rule 2):

  * a file whose bytes differ, with a unified diff of the first lines,
  * a file present only in the committed tree, or only in the rebuilt one,
  * ``dafny --version`` disagreeing with the pin,
  * a build that exits non-zero or writes no ``MemoryBackend-py/``.

Exit 2: no ``dafny`` executable, or no readable pin.

Bounds (Rule 7):

  * **Only ``MemoryBackend.dfy``'s oracle.**  It is the one compiled artifact
    committed; the proof-only files compile to nothing anything consumes.
  * **Freshness, not correctness.**  A regenerated oracle that is wrong is
    the conformance suite's to catch, which ``verify-formal`` runs after this.
  * **Working tree, not the index.**  The committed side is read from disk, so
    locally an uncommitted regeneration reads as fresh.  ``__pycache__`` is
    ignored on both sides.
  * **An include outside ``sdd/formal/`` is not copied.**  Dafny then fails to
    resolve it and the build-failure branch fires; it is loud, not silent.
  * **Runs where ``dafny`` is installed.**  CI's ``verify-formal`` job; not in
    ``hatch run all``.  Locally without native Dafny, run
    ``bash scripts/dafny_translate.sh`` and ``git status sdd/formal/``.

Usage::

    python scripts/check_dafny_oracle_fresh.py
    hatch run check-dafny-oracle-fresh

Drift-gate::

    kind:       pair
    compares:   sdd/formal/*.dfy (built by the pinned Dafny) ↔ sdd/formal/MemoryBackend-py/
    domain:     intent-formalized
"""

from __future__ import annotations

import argparse
import difflib
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from _dafny_classorder import reorder  # noqa: E402

ENTRY = "MemoryBackend.dfy"
STEM = "MemoryBackend"
OUT_DIR = f"{STEM}-py"
# The wrapper's own command (scripts/dafny_translate.sh), minus Docker.
BUILD_ARGS = ("build", "-t", "py", ENTRY, f"--output:{STEM}")
DIFF_LINES = 40
_PIN_RE = re.compile(r"^DAFNY_VERSION=(\S+)\s*$", re.MULTILINE)


def read_pin(translate_script: Path) -> str | None:
    try:
        match = _PIN_RE.search(translate_script.read_text(encoding="utf-8"))
    except OSError:
        return None
    return match.group(1) if match else None


def _files(tree: Path) -> dict[str, Path]:
    return {
        p.relative_to(tree).as_posix(): p
        for p in tree.rglob("*")
        if p.is_file() and "__pycache__" not in p.relative_to(tree).parts
    }


def compare_trees(committed: Path, rebuilt: Path) -> list[str]:
    """Return one report entry per differing path; empty means fresh."""
    ours, theirs = _files(committed), _files(rebuilt)
    report: list[str] = []
    for rel in sorted(ours.keys() | theirs.keys()):
        if rel not in theirs:
            report.append(f"only in committed tree: {rel}")
        elif rel not in ours:
            report.append(f"only in rebuilt tree: {rel}")
        else:
            old, new = ours[rel].read_bytes(), theirs[rel].read_bytes()
            if old != new:
                diff = list(
                    difflib.unified_diff(
                        old.decode("utf-8", "replace").splitlines(),
                        new.decode("utf-8", "replace").splitlines(),
                        f"committed/{rel}",
                        f"rebuilt/{rel}",
                        lineterm="",
                    )
                )
                shown = "\n".join(diff[:DIFF_LINES])
                more = f"\n... ({len(diff) - DIFF_LINES} more diff lines)" if len(diff) > DIFF_LINES else ""
                report.append(f"differs: {rel}\n{shown}{more}")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--formal-dir", type=Path, default=ROOT / "sdd" / "formal")
    parser.add_argument("--translate-script", type=Path, default=ROOT / "scripts" / "dafny_translate.sh")
    parser.add_argument("--dafny", default="dafny", help="Dafny executable (default: dafny on PATH)")
    args = parser.parse_args(argv)

    pin = read_pin(args.translate_script)
    if pin is None:
        print(f"error: no DAFNY_VERSION= line in {args.translate_script}", file=sys.stderr)
        return 2
    dafny = shutil.which(args.dafny)
    if dafny is None:
        print(
            f"error: `{args.dafny}` not found. Without native Dafny, run "
            "`bash scripts/dafny_translate.sh` and `git status sdd/formal/` instead.",
            file=sys.stderr,
        )
        return 2

    version = subprocess.run([dafny, "--version"], capture_output=True, text=True, check=False)
    found = version.stdout.strip().split("+", 1)[0]
    if version.returncode != 0 or found != pin:
        print(
            f"FAIL: dafny on PATH is {found or '<unknown>'}, the pin in "
            f"{args.translate_script.name} is {pin}. Output is not comparable; nothing checked."
        )
        return 1

    committed = args.formal_dir / OUT_DIR
    with tempfile.TemporaryDirectory(prefix="oracle-fresh-") as tmp:
        work = Path(tmp)
        for src in sorted(args.formal_dir.glob("*.dfy")):
            shutil.copy2(src, work / src.name)
        build = subprocess.run([dafny, *BUILD_ARGS], cwd=work, capture_output=True, text=True, check=False)
        rebuilt = work / OUT_DIR
        if build.returncode != 0 or not rebuilt.is_dir():
            print(
                f"FAIL: `dafny {' '.join(BUILD_ARGS)}` exited {build.returncode}"
                + ("" if rebuilt.is_dir() else f" and wrote no {OUT_DIR}/")
            )
            print((build.stdout + build.stderr).strip()[-4000:])
            return 1
        module = rebuilt / "module_.py"
        if module.is_file():
            module.write_text(reorder(module.read_text(encoding="utf-8")), encoding="utf-8")
        report = compare_trees(committed, rebuilt)

    if report:
        print(f"FAIL: {committed} is not what its sources compile to ({len(report)} path(s)):")
        for entry in report:
            print(f"  {entry}")
        print("Fix: bash scripts/dafny_translate.sh, then commit sdd/formal/MemoryBackend-py/.")
        return 1
    print(f"OK: {committed} matches a fresh dafny {pin} build of {ENTRY}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
