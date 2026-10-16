"""Fail on three repo traps that cost sessions retries before any other check saw them (BK-444).

Each rule below records an incident a session paid for, and each is cheap to
check mechanically and expensive to notice by reading:

1. **Invisible characters.** A tool parameter decoded a four-digit unicode
   escape into a raw U+2028 inside test source, where nothing flagged it. Ruff's
   ``PLE`` rules miss U+2028, and ``RUF001``–``003`` would fire on every ``×`` in
   prose, so this rule owns the whole set rather than sharing it with a second
   driver (``sdd/backlog/bk-444-repo-traps-lint.md`` § Ruff ``PLE``).
2. **``write_text`` without ``newline=``.** On Windows, text mode writes each
   ``\\n`` as ``\\r\\n``, so a generator rewriting a tracked LF file leaves a
   tree that reads dirty with no diff.
3. **A hatch alias without ``{args}``.** ``hatch run X --flag`` drops ``--flag``
   silently when ``X`` does not spell ``{args}``, and the run looks like a pass.

Wired into ``hatch run lint`` and, as ``check-repo-traps``, into ``docs-gate``.
Run with:
    python scripts/check_repo_traps.py

What the rules do not catch (``sdd/DRIFT-RULES.md`` Rule 7):

- In CI, a diff matching neither ``CODE_PAT`` nor ``DOCS_PAT`` in ``ci.yml``
  (``.claude/hooks/``, for one) runs neither job, so rule 1 reaches it only
  through a local ``hatch run fast`` or ``all``.
- Rule 1 reads the files ``git ls-files --cached --others --exclude-standard``
  lists, so an ignored file is out of reach. It skips a file that does not
  decode as UTF-8, every path ``git check-attr`` reports ``binary`` for from
  the repo's own attributes (so a path marked only ``-text`` is still read),
  and the decision logs under ``sdd/decisions/`` (``_RECORD_DIRS``),
  which store dialog payloads as received. It has no per-file exemption list: in a Python file, a character the code
  needs is spelled as a named escape, which reads the same to Python and is
  visible to a reviewer. In any other file the only remedy it offers is
  removing the character, because ``\\N{…}`` is not an escape there.
- Rule 2 reads ``scripts/**/*.py`` only (widening ruff's scope to ``sdd/*.py``
  is BUG-327's decision). It checks calls of an attribute named
  ``write_text``; ``open(..., "w")`` and ``Path.open("w")`` are not checked.
  A ``newline`` keyword or fourth positional argument passes when it is
  ``"\\n"`` or ``""``, or when it is not a constant (its value is not
  inspected); ``None``, the default, and any other constant fail. A call that
  passes ``**kwargs`` is taken to pass ``newline``. A file that is not UTF-8 or
  does not parse (a raw invisible character between tokens, which rule 1
  reports) is reported as such, and rules 2 and 3 check nothing in it. It requires the keyword on every call, also on an
  untracked target or one-line content, so it never has to guess what a path
  resolves to.
- Rule 3 reads string entries of ``[tool.hatch.envs.*.scripts]`` whose whole
  value is ``python scripts/X.py``, with or without `` {args}``. An entry with
  pinned arguments, several commands, another interpreter or array form is
  exempt by its shape. A script "takes options" when its AST holds a call to
  ``add_argument`` or a subscript of ``sys.argv``; a script reading
  ``sys.argv`` whole, or parsing options another way, is missed. A bare alias
  whose script does not exist is reported.

Authority for rule 3's pair: the script governs, the alias follows. A script
that accepts options is the decision; an alias that cannot pass them on is the
defect, fixed by adding `` {args}`` to the alias.

Drift-gate::

    kind:       rule
    rule: no UTF-8 file git lists for the working tree, outside the decision logs
        in _RECORD_DIRS and the paths git marks binary, holds one of the invisible
        or bidirectional-control code points in _INVISIBLE
    domain:     realization

Drift-gate::

    kind:       rule
    rule: every write_text call under scripts/ passes newline= as LF or the empty
        string, never the CRLF-writing default None
    domain:     realization

Drift-gate::

    kind:       pair
    compares: the options a scripts/ Python file accepts ↔ the {args} passthrough
        of each bare hatch alias that runs it
    domain:     process
"""

from __future__ import annotations

import ast
import os
import re
import subprocess
import sys
import tomllib
import unicodedata
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Code points rule 1 refuses, as integers so this file holds none of them. The
# four C0 controls have no `unicodedata.name`, so their `\N{…}` alias is given
# here; every other name comes from `unicodedata`.
_INVISIBLE: dict[int, str | None] = {
    0x0000: "NULL",
    0x0008: "BACKSPACE",
    0x001A: "SUBSTITUTE",
    0x001B: "ESCAPE",
    0x00A0: None,
    0x061C: None,
    0x200B: None,
    0x200C: None,
    0x200D: None,
    0x200E: None,
    0x200F: None,
    0x2028: None,
    0x2029: None,
    0x202A: None,
    0x202B: None,
    0x202C: None,
    0x202D: None,
    0x202E: None,
    0x2060: None,
    0x2066: None,
    0x2067: None,
    0x2068: None,
    0x2069: None,
    0xFEFF: None,
}
# Built from the integers above, so this file still holds none of the characters.
_INVISIBLE_RE = re.compile("[" + "".join(re.escape(chr(c)) for c in _INVISIBLE) + "]")

# Records rule 1 does not read: scripts/record_decision.py stores each dialog
# payload as received, with ensure_ascii=False, so a recorded question may carry
# a raw U+2028 that no author typed and no edit may remove.
_RECORD_DIRS: tuple[str, ...] = ("sdd/decisions/",)

# A bare alias: the whole entry runs one scripts/ file, optionally forwarding argv.
_BARE_ALIAS_RE = re.compile(r"^python (scripts/[\w/]+\.py)( \{args\})?$")


@dataclass(frozen=True)
class Violation:
    """One trap found: where it is, and what to do about it."""

    location: str
    message: str

    def __str__(self) -> str:
        return f"{self.location}: {self.message}"


def _name(code_point: int) -> str:
    return _INVISIBLE[code_point] or unicodedata.name(chr(code_point))


# --- Rule 1: invisible characters -------------------------------------------


def scan_invisible(text: str, rel: str) -> list[Violation]:
    """Return one violation per refused code point in *text*, by line and column."""
    found: list[Violation] = []
    # Nearly every file is clean, so one C-level search decides most of them.
    if not _INVISIBLE_RE.search(text):
        return found
    python = rel.endswith(".py")
    # Split on "\n" alone: `str.splitlines` also breaks on U+2028 and U+2029,
    # which would shift every line number after the character being reported.
    for lineno, line in enumerate(text.split("\n"), 1):
        for match in _INVISIBLE_RE.finditer(line):
            code_point = ord(match.group())
            name = _name(code_point)
            # `\N{…}` is an escape only inside a Python string literal.
            remedy = f"write it as \\N{{{name}}} in a Python string, or remove it" if python else "remove it"
            found.append(Violation(f"{rel}:{lineno}:{match.start() + 1}", f"U+{code_point:04X} {name}; {remedy}"))
    return found


def listed_files(root: Path) -> list[str]:
    """Return the repo-relative paths git lists for the working tree, tracked or new."""
    out = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=root,
        capture_output=True,
        check=True,
    ).stdout
    return sorted({p for p in out.decode("utf-8").split("\0") if p})


def binary_files(root: Path, files: list[str]) -> set[str]:
    """Return the members of *files* git marks ``binary``, asking git itself.

    One ``git check-attr`` call, so nested ``.gitattributes`` files,
    ``core.ignorecase`` and the full pattern syntax all match exactly as git
    applies them. A re-implementation would have to track all three, and any
    gap in it skips a file rule 1 should read. The per-user and system-wide
    attributes files are switched off; ``$GIT_DIR/info/attributes``, which is
    local to one clone, is still read.
    """
    if not files:
        return set()
    # Only the repo's own attributes count: the per-user file (default
    # ~/.config/git/attributes) points at a path that does not exist, and
    # GIT_ATTR_NOSYSTEM drops the system-wide one, so a machine's own `binary`
    # line cannot shrink what rule 1 reads locally while CI still reads it.
    no_user_attributes = root / ".check-repo-traps-no-user-attributes"
    out = subprocess.run(
        ["git", "-c", f"core.attributesFile={no_user_attributes}", "check-attr", "-z", "--stdin", "binary"],
        cwd=root,
        env={**os.environ, "GIT_ATTR_NOSYSTEM": "1"},
        input="\0".join(files).encode("utf-8"),
        capture_output=True,
        check=True,
    ).stdout
    # -z output is path NUL attribute NUL value NUL, per path.
    fields = out.decode("utf-8").split("\0")
    return {fields[i] for i in range(0, len(fields) - 2, 3) if fields[i + 2] == "set"}


def check_invisible(root: Path, files: list[str]) -> list[Violation]:
    """Rule 1 over *files* (repo-relative), skipping records, binary and non-UTF-8 ones."""
    binary = binary_files(root, files)
    found: list[Violation] = []
    for rel in files:
        if rel.startswith(_RECORD_DIRS) or rel in binary:
            continue
        try:
            text = (root / rel).read_bytes().decode("utf-8")
        except (OSError, UnicodeDecodeError):
            # Deleted from the tree but still in the index, or not text.
            continue
        found.extend(scan_invisible(text, rel))
    return found


# --- Rule 2: write_text without newline= -------------------------------------


def scan_write_text(source: str, rel: str) -> list[Violation]:
    """Return one violation per ``.write_text(`` call in *source* whose ``newline`` can write CRLF."""
    found: list[Violation] = []
    try:
        tree = ast.parse(source, filename=rel)
    except (SyntaxError, ValueError) as exc:
        # A raw invisible character between tokens lands here; rule 1 reports
        # the character itself, so this rule only says why it read nothing.
        return [Violation(f"{rel}:{getattr(exc, 'lineno', None) or 1}", f"does not parse ({exc}); rule 2 skipped it")]
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
            continue
        if node.func.attr != "write_text":
            continue
        # `newline` is Path.write_text's fourth parameter; `**kw` may carry it.
        if any(k.arg is None for k in node.keywords):
            continue
        given = [k.value for k in node.keywords if k.arg == "newline"] + node.args[3:4]
        # None is the default and translates "\n" to os.linesep; only "\n" and ""
        # write LF. A non-constant value is not inspected.
        if given and not (isinstance(given[0], ast.Constant) and given[0].value not in ("\n", "")):
            continue
        found.append(
            Violation(
                f"{rel}:{node.lineno}",
                'write_text without newline="\\n"; pass it so Windows does not write CRLF',
            )
        )
    return found


def check_write_text(root: Path) -> list[Violation]:
    """Rule 2 over every Python file under ``scripts/``."""
    found: list[Violation] = []
    for path in sorted((root / "scripts").rglob("*.py")):
        rel = path.relative_to(root).as_posix()
        try:
            source = path.read_bytes().decode("utf-8")
        except UnicodeDecodeError as exc:
            found.append(Violation(rel, f"not UTF-8 ({exc.reason} at byte {exc.start}); rule 2 skipped it"))
            continue
        found.extend(scan_write_text(source, rel))
    return found


# --- Rule 3: hatch alias without {args} --------------------------------------


def takes_options(source: str) -> bool:
    """True when *source* calls ``add_argument`` or subscripts ``sys.argv``.

    Raises ``SyntaxError`` or ``ValueError`` when *source* does not parse.
    """
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Call):
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
            if name == "add_argument":
                return True
        if (
            isinstance(node, ast.Subscript)
            and isinstance(node.value, ast.Attribute)
            and node.value.attr == "argv"
            and isinstance(node.value.value, ast.Name)
            and node.value.value.id == "sys"
        ):
            return True
    return False


def check_hatch_args(root: Path) -> list[Violation]:
    """Rule 3: each bare alias whose script takes options must spell ``{args}``."""
    config = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    envs = config.get("tool", {}).get("hatch", {}).get("envs", {})
    found: list[Violation] = []
    for env_name, env in sorted(envs.items()):
        for alias, command in sorted(env.get("scripts", {}).items()):
            match = _BARE_ALIAS_RE.match(command) if isinstance(command, str) else None
            if match is None or match.group(2):
                continue
            script = root / match.group(1)
            location = f"pyproject.toml [tool.hatch.envs.{env_name}.scripts] {alias}"
            if not script.is_file():
                # A typo or a rename; the alias fails whenever it is run.
                found.append(Violation(location, f"{match.group(1)} does not exist"))
                continue
            try:
                options = takes_options(script.read_text(encoding="utf-8"))
            except (SyntaxError, ValueError) as exc:
                found.append(Violation(location, f"{match.group(1)} does not parse ({exc}); rule 3 skipped it"))
                continue
            if options:
                found.append(
                    Violation(location, f"{match.group(1)} takes options but the alias drops them; append ' {{args}}'")
                )
    return found


def main(root: Path = ROOT) -> int:
    """Run the three rules; return 0 when clean, 1 when any fails."""
    rules = (
        ("invisible characters", check_invisible(root, listed_files(root))),
        ("write_text that can write CRLF", check_write_text(root)),
        ("hatch alias without {args}", check_hatch_args(root)),
    )
    failed = False
    for title, violations in rules:
        for v in violations:
            sys.stderr.write(f"error: {v}\n")
        if violations:
            sys.stderr.write(f"{len(violations)} {title} found\n\n")
            failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
