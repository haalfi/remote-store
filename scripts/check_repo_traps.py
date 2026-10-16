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
  decode as UTF-8 and every path a ``binary`` pattern in ``.gitattributes``
  matches. It has no exemption list: in a Python file, a character the code
  needs is spelled as a named escape, which reads the same to Python and is
  visible to a reviewer. In any other file the only remedy it offers is
  removing the character, because ``\\N{…}`` is not an escape there.
- Rule 2 reads ``scripts/**/*.py`` only (widening ruff's scope to ``sdd/*.py``
  is BUG-327's decision). It checks calls of an attribute named
  ``write_text``; ``open(..., "w")`` and ``Path.open("w")`` are not checked. A
  call that passes ``**kwargs`` or a fourth positional argument is taken to
  pass ``newline``. It requires the keyword on every call, also on an
  untracked target or one-line content, so it never has to guess what a path
  resolves to.
- Rule 3 reads string entries of ``[tool.hatch.envs.*.scripts]`` whose whole
  value is ``python scripts/X.py``, with or without `` {args}``. An entry with
  pinned arguments, several commands, another interpreter or array form is
  exempt by its shape. A script "takes options" when its AST holds a call to
  ``add_argument`` or a subscript of ``sys.argv``; a script reading
  ``sys.argv`` whole, or parsing options another way, is missed.

Authority for rule 3's pair: the script governs, the alias follows. A script
that accepts options is the decision; an alias that cannot pass them on is the
defect, fixed by adding `` {args}`` to the alias.

Drift-gate::

    kind:       rule
    rule: no file git lists for the working tree holds one of the invisible or
        bidirectional-control code points in _INVISIBLE
    domain:     realization

Drift-gate::

    kind:       rule
    rule: every write_text call under scripts/ passes newline=
    domain:     realization

Drift-gate::

    kind:       pair
    compares: the options a scripts/ Python file accepts ↔ the {args} passthrough
        of each bare hatch alias that runs it
    domain:     process
"""

from __future__ import annotations

import ast
import fnmatch
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
    0x200B: None,
    0x200C: None,
    0x200D: None,
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
    python = rel.endswith(".py")
    # Split on "\n" alone: `str.splitlines` also breaks on U+2028 and U+2029,
    # which would shift every line number after the character being reported.
    for lineno, line in enumerate(text.split("\n"), 1):
        for col, ch in enumerate(line, 1):
            if ord(ch) in _INVISIBLE:
                name = _name(ord(ch))
                # `\N{…}` is an escape only inside a Python string literal.
                remedy = f"write it as \\N{{{name}}} in a Python string, or remove it" if python else "remove it"
                found.append(Violation(f"{rel}:{lineno}:{col}", f"U+{ord(ch):04X} {name}; {remedy}"))
    return found


def binary_patterns(root: Path) -> list[str]:
    """Return the patterns ``.gitattributes`` marks ``binary``."""
    attributes = root / ".gitattributes"
    if not attributes.is_file():
        return []
    patterns = []
    for line in attributes.read_text(encoding="utf-8").splitlines():
        fields = line.split()
        if fields and not fields[0].startswith("#") and "binary" in fields[1:]:
            patterns.append(fields[0])
    return patterns


def _is_binary(rel: str, patterns: list[str]) -> bool:
    # A pattern without a slash matches the basename at any depth, as in git.
    base = rel.rsplit("/", 1)[-1]
    return any(fnmatch.fnmatch(rel if "/" in p else base, p.lstrip("/")) for p in patterns)


def listed_files(root: Path) -> list[str]:
    """Return the repo-relative paths git lists for the working tree, tracked or new."""
    out = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=root,
        capture_output=True,
        check=True,
    ).stdout
    return sorted({p for p in out.decode("utf-8").split("\0") if p})


def check_invisible(root: Path, files: list[str]) -> list[Violation]:
    """Rule 1 over *files* (repo-relative), skipping binary and non-UTF-8 ones."""
    patterns = binary_patterns(root)
    found: list[Violation] = []
    for rel in files:
        if _is_binary(rel, patterns):
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
    """Return one violation per ``.write_text(`` call in *source* that passes no ``newline``."""
    found: list[Violation] = []
    for node in ast.walk(ast.parse(source, filename=rel)):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
            continue
        if node.func.attr != "write_text":
            continue
        # `newline` is Path.write_text's fourth parameter; `**kw` may carry it.
        if len(node.args) >= 4 or any(k.arg in ("newline", None) for k in node.keywords):
            continue
        found.append(
            Violation(
                f"{rel}:{node.lineno}",
                'write_text without newline=; pass newline="\\n" so Windows does not write CRLF',
            )
        )
    return found


def check_write_text(root: Path) -> list[Violation]:
    """Rule 2 over every Python file under ``scripts/``."""
    found: list[Violation] = []
    for path in sorted((root / "scripts").rglob("*.py")):
        rel = path.relative_to(root).as_posix()
        found.extend(scan_write_text(path.read_text(encoding="utf-8"), rel))
    return found


# --- Rule 3: hatch alias without {args} --------------------------------------


def takes_options(source: str) -> bool:
    """True when *source* calls ``add_argument`` or subscripts ``sys.argv``."""
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
            if script.is_file() and takes_options(script.read_text(encoding="utf-8")):
                found.append(
                    Violation(
                        f"pyproject.toml [tool.hatch.envs.{env_name}.scripts] {alias}",
                        f"{match.group(1)} takes options but the alias drops them; append ' {{args}}'",
                    )
                )
    return found


def main(root: Path = ROOT) -> int:
    """Run the three rules; return 0 when clean, 1 when any fails."""
    rules = (
        ("invisible characters", check_invisible(root, listed_files(root))),
        ("write_text without newline=", check_write_text(root)),
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
