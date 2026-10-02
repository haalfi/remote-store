#!/usr/bin/env python3
"""Check that the committed compiled oracle is what its Dafny sources compile to (ID-263).

``sdd/formal/MemoryBackend-py/`` is generated: ``scripts/dafny_translate.sh``
builds ``MemoryBackend.dfy`` (and the files it includes) to Python, then
``scripts/_dafny_classorder.py`` reorders ``module_.py``.  A non-ghost edit to
any of those sources that is not regenerated passes ``dafny verify``, and every
test that drives the oracle then exercises stale code.  This gate rebuilds the
oracle the same way, with the build arguments read from the wrapper rather than
restated here, and compares it with the committed tree, file by file.

Authority: the ``.dfy`` sources govern; ``MemoryBackend-py/`` is derived and is
fixed by regenerating, never by hand-editing (declared in
``sdd/formal/README.md`` § Compiled oracle).  ``DAFNY_VERSION`` in
``dafny_translate.sh`` is the toolchain pin: a different ``dafny`` on ``PATH``
is reported as skew and nothing is compared, since its output would differ for
reasons unrelated to the sources.

The source set is what the wrapper's ``cp /work/<glob> /build/`` copies from
``sdd/formal/`` (today every ``*.dfy``), read from the wrapper rather than a list
of what ``MemoryBackend.dfy`` includes: the include closure
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

Exit 2: no ``dafny`` executable, no readable pin, or a wrapper this check cannot
reproduce exactly: not exactly one source-copy line and one build line, or either
carrying a shell variable other than ``$f`` / ``$stem``, quoting, or a brace
expansion.  Those are setup errors, never reported as drift.

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
import shlex
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
DIFF_LINES = 40
_PIN_RE = re.compile(r"^DAFNY_VERSION=(\S+)\s*$", re.MULTILINE)
# The wrapper's one build invocation, e.g. `/opt/dafny/dafny build -t py $f --output:$stem 2>&1`.
_BUILD_RE = re.compile(r"/dafny (build\b[^|\n]*?)\s+2>&1")
# The wrapper's source copy into the build dir, e.g. `cp /work/*.dfy /build/`.
_COPY_RE = re.compile(r"\bcp /work/(\S+) /build/")
# `$f` / `$stem` as whole names only: `$file` or `$stem_out` must stay unbound and be rejected.
_VAR_RE = re.compile(r"\$(f|stem)(?![A-Za-z0-9_])")
_BINDINGS = {"f": ENTRY, "stem": STEM}
# Left after binding, any of these means the wrapper's shell would read the text differently than this
# check does (another variable, quoting bash strips twice and shlex once, brace expansion glob lacks).
_UNREPRODUCIBLE = set("$\"'\\{}")


def _read(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return None


def read_pin(translate_script: Path) -> str | None:
    text = _read(translate_script)
    match = _PIN_RE.search(text) if text is not None else None
    return match.group(1) if match else None


def read_source_glob(translate_script: Path) -> str | None:
    """The glob the wrapper copies from ``sdd/formal/`` into its build dir; ``None`` unless exactly one."""
    text = _read(translate_script)
    matches = _COPY_RE.findall(text) if text is not None else []
    if len(matches) != 1 or _UNREPRODUCIBLE & set(matches[0]):
        return None
    return matches[0]


def read_build_args(translate_script: Path) -> list[str] | None:
    """The wrapper's build arguments with its loop variables bound to the oracle.

    Read rather than restated, so a flag the wrapper gains reaches this check
    (``sdd/DRIFT-RULES.md`` Rule 3).  ``None`` unless there is exactly one build
    line and every shell variable in it is ``$f`` or ``$stem``.
    """
    text = _read(translate_script)
    matches = _BUILD_RE.findall(text) if text is not None else []
    if len(matches) != 1:
        return None
    try:
        tokens = shlex.split(matches[0])
    except ValueError:
        return None
    args = [_VAR_RE.sub(lambda m: _BINDINGS[m.group(1)], tok) for tok in tokens]
    return None if any(_UNREPRODUCIBLE & set(tok) for tok in args) else args


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
    build_args = read_build_args(args.translate_script)
    if build_args is None:
        print(
            f"error: no single `dafny build ... 2>&1` line using only $f/$stem in {args.translate_script}",
            file=sys.stderr,
        )
        return 2
    source_glob = read_source_glob(args.translate_script)
    if source_glob is None:
        print(f"error: no single `cp /work/<glob> /build/` line in {args.translate_script}", file=sys.stderr)
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
        for src in sorted(args.formal_dir.glob(source_glob)):
            shutil.copy2(src, work / src.name)
        build = subprocess.run([dafny, *build_args], cwd=work, capture_output=True, text=True, check=False)
        rebuilt = work / OUT_DIR
        if build.returncode != 0 or not rebuilt.is_dir():
            print(
                f"FAIL: `dafny {' '.join(build_args)}` exited {build.returncode}"
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
