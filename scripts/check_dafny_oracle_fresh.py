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
  * ``dafny --version`` printing a version other than the pin,
  * a build that exits non-zero, writes no ``MemoryBackend-py/``, or writes a
    ``module_.py`` that is not UTF-8.

Exit 2, setup errors never reported as drift: no ``dafny`` executable, or one
whose ``--version`` cannot be run or exits non-zero (its output is printed); a
wrapper that cannot be read as UTF-8, has no pin, or falls outside the grammar
below; a non-file (a directory, a dangling link) matching the wrapper's glob,
on which the wrapper's ``cp`` would fail; or any other OS error while copying,
building or comparing.

The grammar is an allowlist over two spans of the wrapper, not a shell parser
(the text passes two shell levels: the ``CMDS="..."`` assignment, then
``bash -c``).  It constrains only these spans; beyond the pin line, the UTF-8
decode and the one-match count, the rest of the wrapper is not checked (see
Bounds):

  * exactly one ``cp [-p|-f|-v]... /work/<glob> /build[/]`` line, followed only
    by ``&&``, ``;``, ``|``, ``)``, ``"`` or the line end, whose glob is
    ``[A-Za-z0-9_*?[]-]*.dfy`` without ``**``;
  * exactly one ``CMDS="$CMDS`` line in which only ``&& echo '...'`` steps
    precede ``&& (/opt/dafny/dafny build <tokens> 2>&1 |``, whose tokens, split
    on space and tab and after binding ``$f`` / ``${f}`` / ``$stem`` /
    ``${stem}``, use only ``[A-Za-z0-9_./:=,+-]``.

The offending token, or the shape and how often it was found, is named.

Bounds (Rule 7):

  * **Only ``MemoryBackend.dfy``'s oracle.**  It is the one compiled artifact
    committed; the other ``.dfy`` files have no oracle of their own, and those
    ``MemoryBackend.dfy`` includes are covered through its build.
  * **Freshness, not correctness.**  A regenerated oracle that is wrong is
    the conformance suite's to catch, which ``verify-formal`` runs after this.
  * **Working tree, not the index.**  The committed side is read from disk, so
    locally an uncommitted regeneration reads as fresh.  ``__pycache__`` is
    ignored on both sides.
  * **The wrapper grammar is narrower than bash inside its spans.**  A spelling
    bash reads the same way but the grammar does not list (a quoted argument,
    say) is exit 2, never a silent pass; widen the grammar with a guard cell
    when one is needed.
  * **Outside its spans the wrapper is not checked.**  Other ``CMDS`` lines not
    in either shape, the text after the build's ``|``, the body of an
    ``echo '...'`` step (which the outer double quotes still evaluate) and what
    precedes ``cp`` can change what the wrapper produces (a post-build edit, a
    build appended after the pipe, a ``cd`` step) while this check builds as
    before.  That never lets a stale oracle pass, since the check rebuilds from
    the sources itself; it surfaces as exit-1 drift on a fresh regeneration,
    which rerunning the wrapper cannot clear.  Pinned by
    ``test_wrapper_steps_outside_the_two_spans_are_not_checked``.  Keep such
    steps out of the wrapper, or extend the grammar to cover them.
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
DIFF_LINES = 40
_PIN_RE = re.compile(r"^DAFNY_VERSION=(\S+)\s*$", re.MULTILINE)
# Reading the wrapper is an allowlist grammar over two spans, not a shell parser: within the build
# span and the cp span, anything whose meaning depends on quoting, expansion or an operator is
# rejected rather than interpreted. Outside them only the pin line, the UTF-8 decode and the
# exactly-one-match count are checked (docstring, Bounds).
# Build: a double-quoted `CMDS="$CMDS ...` line in which only `&& echo '...'` steps precede
# `&& (/opt/dafny/dafny build <tokens> 2>&1 |`. An env prefix, `cd`, `timeout` or a single-quoted
# CMDS piece before the `(` does not match; nothing after the `|` is checked. Tokens split on space
# and tab only, as bash does.
_BUILD_RE = re.compile(
    r"^[ \t]*CMDS=\"\$CMDS(?: && echo '[^'\n]*')* && \(/opt/dafny/dafny (build\b[^|\n]*?)[ \t]+2>&1[ \t]*\|",
    re.MULTILINE,
)
# Copy: `cp [-p|-f|-v]... /work/<glob> /build[/]`, then only `&&`, `;`, `|`, `)`, `"` or the line end;
# those flags take no operand and never recurse, and a further word would become cp's target.
_COPY_RE = re.compile(r"\bcp((?:[ \t]+-[pfv]+)*)[ \t]+/work/(\S+)[ \t]+/build/?[ \t]*(?=&&|;|\||\)|\"|$)", re.MULTILINE)
# `$f`, `${f}`, `$stem`, `${stem}` as whole names: `$file` or `$stem_out` stay unbound and are rejected.
_VAR_RE = re.compile(r"\$(?:\{(f|stem)\}|(f|stem)(?![A-Za-z0-9_]))")
_BINDINGS = {"f": ENTRY, "stem": STEM}
_TOKEN_RE = re.compile(r"[A-Za-z0-9_./:=,+-]+")  # a build token after binding
# A `.dfy` glob in one directory, without `**`: bash and Path.glob read it alike, dotfiles aside.
_GLOB_RE = re.compile(r"(?!.*\*\*)[A-Za-z0-9_*?\[\]-]*\.dfy")


class WrapperError(ValueError):
    """The wrapper says something this check cannot reproduce exactly (exit 2)."""


def _read(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, ValueError):  # ValueError: UnicodeDecodeError; main() reports it first
        return None


def read_pin(translate_script: Path) -> str | None:
    text = _read(translate_script)
    match = _PIN_RE.search(text) if text is not None else None
    return match.group(1) if match else None


def _single(regex: re.Pattern[str], translate_script: Path, shape: str) -> re.Match[str]:
    text = _read(translate_script) or ""
    matches = list(regex.finditer(text))
    if len(matches) != 1:
        raise WrapperError(f"{translate_script}: expected one `{shape}` line, found {len(matches)}")
    return matches[0]


def read_source_glob(translate_script: Path) -> str:
    """The glob the wrapper copies from ``sdd/formal/`` into its build dir."""
    glob = _single(_COPY_RE, translate_script, "cp [-p|-f|-v] /work/<glob>.dfy /build/").group(2)
    if not _GLOB_RE.fullmatch(glob):
        raise WrapperError(f"{translate_script}: copy glob `{glob}` is outside the grammar this check reproduces")
    return glob


def read_build_args(translate_script: Path) -> list[str]:
    """The wrapper's build arguments with its loop variables bound to the oracle.

    Read rather than restated, so a flag the wrapper gains reaches this check
    (``sdd/DRIFT-RULES.md`` Rule 3).
    """
    raw = _single(_BUILD_RE, translate_script, "dafny build ... 2>&1").group(1)
    args = []
    for tok in re.split(r"[ \t]+", raw.strip(" \t")):
        bound = _VAR_RE.sub(lambda m: _BINDINGS[m.group(1) or m.group(2)], tok)
        if not _TOKEN_RE.fullmatch(bound):
            raise WrapperError(f"{translate_script}: build token `{tok}` is outside the grammar this check reproduces")
        args.append(bound)
    return args


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

    try:
        args.translate_script.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        print(f"error: cannot read {args.translate_script}: {exc}", file=sys.stderr)
        return 2
    pin = read_pin(args.translate_script)
    if pin is None:
        print(f"error: no DAFNY_VERSION= line in {args.translate_script}", file=sys.stderr)
        return 2
    try:
        build_args = read_build_args(args.translate_script)
        source_glob = read_source_glob(args.translate_script)
    except WrapperError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    dafny = shutil.which(args.dafny)
    if dafny is None:
        print(
            f"error: `{args.dafny}` not found. Without native Dafny, run "
            "`bash scripts/dafny_translate.sh` and `git status sdd/formal/` instead.",
            file=sys.stderr,
        )
        return 2

    try:
        version = subprocess.run(
            [dafny, "--version"], capture_output=True, encoding="utf-8", errors="replace", check=False
        )
    except OSError as exc:
        print(f"error: could not run `{dafny} --version`: {exc}", file=sys.stderr)
        return 2
    if version.returncode != 0:
        print(f"error: `{dafny} --version` exited {version.returncode}:", file=sys.stderr)
        print((version.stdout + version.stderr).strip()[-2000:], file=sys.stderr)
        return 2
    found = version.stdout.strip().split("+", 1)[0]
    if found != pin:
        print(
            f"FAIL: dafny on PATH is {found or '<unknown>'}, the pin in "
            f"{args.translate_script.name} is {pin}. Output is not comparable; nothing checked."
        )
        return 1

    # bash's `*` skips dotfiles (the grammar admits no leading dot); Path.glob does not.
    sources = [src for src in sorted(args.formal_dir.glob(source_glob)) if not src.name.startswith(".")]
    not_files = [src for src in sources if not src.is_file()]
    if not_files:
        # The wrapper's cp, without -r, exits 1 on these and aborts its `&&` chain: nothing to compare.
        print(
            f"error: {', '.join(str(p) for p in not_files)} match the wrapper's glob `{source_glob}` "
            "but are not regular files, so the wrapper's cp would fail",
            file=sys.stderr,
        )
        return 2

    committed = args.formal_dir / OUT_DIR
    try:
        with tempfile.TemporaryDirectory(prefix="oracle-fresh-") as tmp:
            work = Path(tmp)
            for src in sources:
                shutil.copy2(src, work / src.name)
            build = subprocess.run(
                [dafny, *build_args], cwd=work, capture_output=True, encoding="utf-8", errors="replace", check=False
            )
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
                try:
                    module.write_text(reorder(module.read_text(encoding="utf-8")), encoding="utf-8")
                except UnicodeDecodeError as exc:
                    print(f"FAIL: the rebuilt {OUT_DIR}/module_.py is not UTF-8 ({exc}); the build is broken")
                    return 1
            report = compare_trees(committed, rebuilt)
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

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
