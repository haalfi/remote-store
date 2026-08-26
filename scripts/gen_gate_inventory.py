#!/usr/bin/env python3
"""Wired drift mechanisms → sdd/GATE-INVENTORY.md (ID-245).

The repo's checking layer had the defect it diagnoses in the specification
layer: no enumeration of *which artifact pairs are checked* existed, so the
hand-built inventory in
``sdd/research/research-inconsistency-detection-multi-artifact.md`` § 4b could
drift with nothing to notice. This script derives that inventory instead.

Run with:
    hatch run gen-gate-inventory
    hatch run gen-gate-inventory-check      # read-only; exit 1 on drift
    python scripts/gen_gate_inventory.py [--check]

What a mechanism declares, and what is derived
----------------------------------------------
Authority is answered **per column, not per table** (``sdd/DRIFT-RULES.md``
Rule 4). No cell of the rendered document is authored in the rendered document:

* *Mechanism path*, *Runs in*, *Enforcement* — derived here from
  ``pyproject.toml``'s script table and ``.github/workflows/*.yml``. A
  declaration cannot lie about where it runs or whether it gates.
* *Kind*, *Compares* / *Rule*, *Domain* — read from the mechanism's own module
  docstring, which is next to the code whose change invalidates them
  (Rule 8: the derivation path is recorded rather than assumed).

A declaration is a line reading ``Drift-gate::`` on its own, followed by an
indented field list::

    kind:       pair
    compares:   docs-src/reference/FEATURES.md <-> graph.json
    domain:     explanation <-> realization

The header line is the whole trigger, so prose *about* the format must never
reproduce it alone on a line -- the example above deliberately omits it. This
file is the one place that documents the format and so the one place that could
have declared a mechanism by describing one; it did, on the first run, and the
row it displaced was this generator's own.

``kind: pair`` states the two artifacts compared. ``kind: rule`` is for the
single-artifact rule checks — assertion presence, mock discipline, forbidden
RST roles, em dashes in TLA+ — which guard no pair and would otherwise yield no
row at all. ``entrypoint:`` disambiguates a script carrying more than one
mechanism (``drift_check.py``); it is matched against the argv that the wiring
actually passes, and may be omitted when a script declares exactly one block.

The claim space (Rule 3)
------------------------
Derived from what the repo actually runs, never from a glob over
``scripts/check_*.py`` — that glob under-reaches, and
``scripts/docs/check_links.py`` is the standing proof.

* ``pyproject.toml`` ``[tool.hatch.envs.default.scripts]``, with composed
  targets expanded transitively (``docs-gate`` -> ``check-links`` ->
  ``python scripts/docs/check_links.py``).
* ``.github/workflows/*.yml`` ``run:`` steps, for both ``hatch run <target>``
  and direct ``python scripts/<name>.py`` invocations. Four gates are wired a
  second time in ``ci.yml``'s ``verify-formal`` job so a ``sdd/``-only change
  still runs them; both homes show in the output.

A wired script whose basename matches ``check_*``, ``gen_*``, ``drift_*`` or
``report_*`` and which carries no declaration block is a **failure**, not a
skip. An unknown that a gate silently drops is the parallel-list defect one
level up; ``check_dafny_twin_parity.py`` takes the same line for the same
reason.

Bounds -- what this gate does not catch (``sdd/DRIFT-RULES.md`` Rule 7):

* A drift mechanism named outside that basename heuristic **and** carrying no
  declaration block is invisible. The heuristic is a backstop for a forgotten
  block on a conventionally-named script, not a detector of unconventional
  ones; a mechanism that wants to be found either declares or is named like its
  siblings.
* A mechanism wired nowhere -- no hatch target, no workflow step -- is not
  listed. The inventory answers "what watches what *in this repo's gates*",
  and an unwired script watches nothing.
* A mechanism that is not a *script invocation* is out of range entirely. The
  conformance suite is the standing example: it drives every backend from one
  shared suite, which is the strongest cross-artifact check the repo has
  (``sdd/DRIFT-RULES.md`` Rule 1 prefers exactly that shape), and it is pytest
  collection rather than a ``scripts/`` entry point. Reading this inventory as
  the whole checking layer therefore understates it.
* The declaration's *content* is unverified. Nothing here confirms that a
  ``compares:`` line names the artifacts the code actually reads; a gate
  rewritten to compare something else, with its block left alone, renders a
  truthful-looking wrong row. That is the residue of declaring rather than
  inferring, and inferring compared artifacts from arbitrary Python is the
  problem this design declines to solve.
* Enforcement is derived from *wiring*, not from exit codes. A script wired
  into a gate bundle that always exits 0 is reported as gating.
* Once a script declares at least one block, a wired invocation matching no
  ``entrypoint:`` is treated as an operational subcommand rather than a
  mechanism -- ``drift_check.py extras`` lists extras and compares nothing.
  A genuinely forgotten *second* mechanism on an already-declaring script is
  therefore silent. The backstop catches the file that declared nothing, which
  is the case that has an obvious right answer; distinguishing a forgotten
  mechanism from an operational subcommand needs a judgement about what the
  subcommand does, and a gate that guesses it would fail on correct code.

This gate inventories itself, which is the point: § 4b's finding was that the
checking layer had no enumeration of its own coverage, and an inventory that
exempted its own generator would reproduce that hole one level further in.

Drift-gate::

    kind:       pair
    compares:   the Drift-gate declarations and gate wiring across scripts/, pyproject.toml
        and .github/workflows/ ↔ sdd/GATE-INVENTORY.md
    domain:     process
"""

from __future__ import annotations

import argparse
import re
import shlex
import sys
from dataclasses import dataclass
from pathlib import Path

import yaml

try:
    import tomllib
except ImportError:  # pragma: no cover - Python 3.10 fallback
    import tomli as tomllib  # type: ignore[no-redef]

ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = ROOT / "pyproject.toml"
WORKFLOWS = ROOT / ".github" / "workflows"
OUTPUT = ROOT / "sdd" / "GATE-INVENTORY.md"

# The one local entry point not derivable from CI: `hatch run all` is the
# pre-commit gate named in CLAUDE.md § Dev commands. Every other reported
# target is discovered from a workflow's `hatch run <target>` step.
LOCAL_GATE_TARGET = "all"

# Basenames that must carry a declaration block once wired. The backstop, not
# the claim space -- see the module docstring's bounds.
_MECHANISM_STEM_RE = re.compile(r"^(check|gen|drift|report)_")

# A `scripts/...py` path anywhere in a shell command, plus whatever follows it
# on that command line (the argv used to match `entrypoint:`).
_SCRIPT_INVOCATION_RE = re.compile(r"(scripts/[\w/]+\.py)([^\n|&;]*)")

# `hatch run <target>` / `uvx hatch run <target>` inside a workflow run step.
_HATCH_RUN_RE = re.compile(r"hatch run ([a-z0-9][\w-]*)")

_BLOCK_HEADER = "Drift-gate::"
_FIELD_RE = re.compile(r"^(\w+):\s*(.*)$")
_VALID_KINDS = frozenset({"pair", "rule"})
_VALID_FIELDS = frozenset({"kind", "entrypoint", "compares", "rule", "domain"})


class DeclarationError(ValueError):
    """A malformed or incomplete ``Drift-gate::`` block."""


@dataclass(frozen=True)
class Declaration:
    """One declared mechanism, as read from a module docstring."""

    kind: str
    domain: str
    compares: str | None = None
    rule: str | None = None
    entrypoint: str | None = None

    @property
    def subject(self) -> str:
        """The compared pair or the asserted rule, whichever this kind carries."""
        return self.compares if self.kind == "pair" else self.rule  # type: ignore[return-value]


@dataclass(frozen=True)
class Mechanism:
    """A declared mechanism together with the wiring that reaches it."""

    path: str
    declaration: Declaration
    homes: tuple[str, ...]

    @property
    def enforcement(self) -> str:
        """gating | scheduled | advisory, derived from *homes* alone."""
        if any(h in _GATE_HOMES or h.startswith("ci.yml:") for h in self.homes):
            return "gating"
        if any(":" in h for h in self.homes):
            return "scheduled"
        return "advisory"


# Hatch targets whose failure blocks a commit or a PR. `all` is the local
# pre-commit gate; the rest are discovered from workflow steps at run time and
# merged into this set by `collect`.
_GATE_HOMES: set[str] = {LOCAL_GATE_TARGET}


# ---------------------------------------------------------------------------
# Declaration blocks
# ---------------------------------------------------------------------------


def _module_docstring(text: str) -> str:
    """Return the module docstring of *text*, or "" when there is none."""
    match = re.match(r'\s*(?:#![^\n]*\n)?\s*(?:"""|\'\'\')', text)
    if match is None:
        return ""
    quote = text[match.end() - 3 : match.end()]
    end = text.find(quote, match.end())
    return text[match.end() : end] if end != -1 else ""


def _block_bodies(docstring: str) -> list[list[str]]:
    """Return the indented body lines of each ``Drift-gate::`` block."""
    lines = docstring.splitlines()
    bodies: list[list[str]] = []
    index = 0
    while index < len(lines):
        if lines[index].strip() != _BLOCK_HEADER:
            index += 1
            continue
        header_indent = len(lines[index]) - len(lines[index].lstrip())
        index += 1
        body: list[str] = []
        while index < len(lines):
            line = lines[index]
            if not line.strip():
                index += 1
                if body:
                    # A blank line ends the block only if the next non-blank
                    # line dedents back to (or past) the header.
                    nxt = next((c for c in lines[index:] if c.strip()), None)
                    if nxt is None or len(nxt) - len(nxt.lstrip()) <= header_indent:
                        break
                continue
            if len(line) - len(line.lstrip()) <= header_indent:
                break
            body.append(line)
            index += 1
        if body:
            bodies.append(body)
    return bodies


def parse_declarations(text: str, path: str) -> list[Declaration]:
    """Parse every ``Drift-gate::`` block in *text*'s module docstring.

    Raises DeclarationError, naming *path*, on any malformed block.
    """
    declarations: list[Declaration] = []
    for body in _block_bodies(_module_docstring(text)):
        fields: dict[str, str] = {}
        for line in body:
            field = _FIELD_RE.match(line.strip())
            if field is None:
                if not fields:
                    raise DeclarationError(f"{path}: Drift-gate block line is not `key: value`: {line.strip()!r}")
                # Continuation of the previous field.
                key = next(reversed(fields))
                fields[key] = f"{fields[key]} {line.strip()}"
                continue
            key, value = field.group(1), field.group(2).strip()
            if key not in _VALID_FIELDS:
                raise DeclarationError(f"{path}: unknown Drift-gate field {key!r}")
            if key in fields:
                raise DeclarationError(f"{path}: duplicate Drift-gate field {key!r}")
            fields[key] = value
        declarations.append(_build(fields, path))
    if len(declarations) > 1 and any(d.entrypoint is None for d in declarations):
        # Without an entrypoint on each, nothing matches an invocation to a
        # block and every row for this script drops in silence.
        raise DeclarationError(
            f"{path}: {len(declarations)} Drift-gate blocks, so each needs an `entrypoint:` to match a wired argv"
        )
    return declarations


def _build(fields: dict[str, str], path: str) -> Declaration:
    """Validate *fields* into a Declaration, or raise DeclarationError."""
    kind = fields.get("kind")
    if kind not in _VALID_KINDS:
        raise DeclarationError(f"{path}: Drift-gate `kind:` must be pair or rule, got {kind!r}")
    if not fields.get("domain"):
        raise DeclarationError(f"{path}: Drift-gate block needs a `domain:`")
    required, forbidden = ("compares", "rule") if kind == "pair" else ("rule", "compares")
    if not fields.get(required):
        raise DeclarationError(f"{path}: Drift-gate `kind: {kind}` needs a `{required}:`")
    if fields.get(forbidden):
        raise DeclarationError(f"{path}: Drift-gate `kind: {kind}` must not carry `{forbidden}:`")
    return Declaration(
        kind=kind,
        domain=fields["domain"],
        compares=fields.get("compares"),
        rule=fields.get("rule"),
        entrypoint=fields.get("entrypoint"),
    )


# ---------------------------------------------------------------------------
# Wiring: pyproject script table
# ---------------------------------------------------------------------------


def _script_table(pyproject: Path) -> dict[str, list[str]]:
    """Return ``[tool.hatch.envs.default.scripts]`` as name → command list."""
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    raw = data["tool"]["hatch"]["envs"]["default"]["scripts"]
    return {name: [value] if isinstance(value, str) else list(value) for name, value in raw.items()}


def _invocations(command: str) -> list[tuple[str, str]]:
    """Return ``(script path, trailing argv)`` for each script call in *command*."""
    return [(m.group(1), m.group(2).strip()) for m in _SCRIPT_INVOCATION_RE.finditer(command)]


def _resolve(target: str, table: dict[str, list[str]], seen: frozenset[str]) -> list[tuple[str, str]]:
    """Expand *target* transitively into the script invocations it reaches."""
    if target in seen:
        return []
    seen = seen | {target}
    found: list[tuple[str, str]] = []
    for command in table.get(target, []):
        tokens = shlex.split(command, posix=True) if command.strip() else []
        if tokens and tokens[0] in table:
            found.extend(_resolve(tokens[0], table, seen))
            continue
        found.extend(_invocations(command))
    return found


# ---------------------------------------------------------------------------
# Wiring: workflows
# ---------------------------------------------------------------------------


def _run_steps(workflow: Path) -> list[tuple[str, str]]:
    """Return ``(job id, run body)`` for every ``run:`` step in *workflow*."""
    document = yaml.safe_load(workflow.read_text(encoding="utf-8")) or {}
    steps: list[tuple[str, str]] = []
    for job_id, job in (document.get("jobs") or {}).items():
        for step in (job or {}).get("steps") or []:
            body = (step or {}).get("run")
            if isinstance(body, str):
                steps.append((job_id, body))
    return steps


# ---------------------------------------------------------------------------
# Collection
# ---------------------------------------------------------------------------


def _match(declarations: list[Declaration], argv: str) -> Declaration | None:
    """Pick the declaration whose ``entrypoint:`` matches *argv*."""
    if len(declarations) == 1 and declarations[0].entrypoint is None:
        return declarations[0]
    for declaration in declarations:
        if declaration.entrypoint and argv.startswith(declaration.entrypoint):
            return declaration
    return None


def collect(root: Path = ROOT) -> tuple[list[Mechanism], list[str]]:
    """Derive every wired, declared mechanism plus any backstop violations."""
    table = _script_table(root / "pyproject.toml")
    workflows = sorted((root / ".github" / "workflows").glob("*.y*ml"))

    # Targets a workflow invokes directly are gate homes, same as `all`.
    ci_targets: set[str] = set()
    for workflow in workflows:
        if workflow.name != "ci.yml":
            continue
        for _job, body in _run_steps(workflow):
            ci_targets.update(_HATCH_RUN_RE.findall(body))
    _GATE_HOMES.update(ci_targets)

    # script path → argv → set of homes
    wiring: dict[str, dict[str, set[str]]] = {}

    def record(path: str, argv: str, home: str) -> None:
        wiring.setdefault(path, {}).setdefault(argv, set()).add(home)

    for target in sorted(set(ci_targets) | {LOCAL_GATE_TARGET}):
        for path, argv in _resolve(target, table, frozenset()):
            record(path, argv, target)

    for workflow in workflows:
        for job, body in _run_steps(workflow):
            home = f"{workflow.name}:{job}"
            for target in _HATCH_RUN_RE.findall(body):
                for path, argv in _resolve(target, table, frozenset()):
                    record(path, argv, target if workflow.name == "ci.yml" else home)
            for path, argv in _invocations(body):
                record(path, argv, home)

    # A hatch target that no gate bundle and no workflow reaches is advisory;
    # it still belongs in the inventory, named by its own target.
    for target in table:
        if target in ci_targets or target == LOCAL_GATE_TARGET:
            continue
        for path, argv in _resolve(target, table, frozenset()):
            if path not in wiring:
                record(path, argv, target)

    mechanisms: list[Mechanism] = []
    problems: list[str] = []
    for path in sorted(wiring):
        source = root / path
        if not source.exists():
            continue
        declarations = parse_declarations(source.read_text(encoding="utf-8"), path)
        if not declarations:
            if _MECHANISM_STEM_RE.match(source.stem):
                problems.append(f"{path}: wired but carries no `Drift-gate::` declaration block")
            continue
        for argv, homes in sorted(wiring[path].items()):
            declaration = _match(declarations, argv)
            if declaration is None:
                # The script has declared its mechanisms; this invocation is an
                # operational subcommand (`drift_check.py extras`), not one of
                # them. See the module docstring's bounds for what that costs.
                continue
            mechanisms.append(Mechanism(path=path, declaration=declaration, homes=tuple(sorted(homes))))

    merged = _merge(mechanisms)
    return merged, problems


def _merge(mechanisms: list[Mechanism]) -> list[Mechanism]:
    """Fold rows that resolve to one declaration, unioning their homes."""
    folded: dict[tuple[str, str], Mechanism] = {}
    for mechanism in mechanisms:
        key = (mechanism.path, mechanism.declaration.entrypoint or "")
        existing = folded.get(key)
        homes = set(mechanism.homes) | (set(existing.homes) if existing else set())
        folded[key] = Mechanism(mechanism.path, mechanism.declaration, tuple(sorted(homes)))
    return sorted(folded.values(), key=lambda m: (m.path, m.declaration.entrypoint or ""))


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def _cell(text: str) -> str:
    """Escape *text* for a Markdown table cell."""
    return text.replace("|", "\\|")


def _name(mechanism: Mechanism) -> str:
    """The mechanism's display name: path, plus entrypoint when it carries one."""
    if mechanism.declaration.entrypoint:
        return f"`{mechanism.path} {mechanism.declaration.entrypoint}`"
    return f"`{mechanism.path}`"


def render(mechanisms: list[Mechanism]) -> str:
    """Render the inventory document."""
    pairs = [m for m in mechanisms if m.declaration.kind == "pair"]
    rules = [m for m in mechanisms if m.declaration.kind == "rule"]

    out: list[str] = [
        "# Cross-artifact gate inventory",
        "",
        "<!-- doc: repo-only -->",
        "",
        f"Derived from {len(mechanisms)} declared mechanism(s) by "
        "`scripts/gen_gate_inventory.py`. Do not edit by hand; run "
        "`hatch run gen-gate-inventory`.",
        "",
        "Which artifact pairs this repo checks, and which single-artifact rules it",
        "asserts. *Kind*, *Compares*, *Rule* and *Domain* come from each mechanism's",
        "`Drift-gate::` docstring block; *Runs in* and *Enforcement* are derived from",
        "`pyproject.toml` and `.github/workflows/`, so no column is maintained here.",
        "The generator's module docstring states what this inventory does not catch.",
        "",
        f"## Pair gates ({len(pairs)})",
        "",
        "| Mechanism | Compares | Domain | Runs in | Enforcement |",
        "|---|---|---|---|---|",
    ]
    for mechanism in pairs:
        out.append(
            f"| {_name(mechanism)} | {_cell(mechanism.declaration.subject)} "
            f"| {_cell(mechanism.declaration.domain)} "
            f"| {', '.join(f'`{h}`' for h in mechanism.homes)} | {mechanism.enforcement} |"
        )

    out += [
        "",
        f"## Rule checks, no pair ({len(rules)})",
        "",
        "Single-artifact checks. They guard no pair, so a derivation over compared",
        "artifacts alone would yield no row for them at all.",
        "",
        "| Mechanism | Rule asserted | Domain | Runs in | Enforcement |",
        "|---|---|---|---|---|",
    ]
    for mechanism in rules:
        out.append(
            f"| {_name(mechanism)} | {_cell(mechanism.declaration.subject)} "
            f"| {_cell(mechanism.declaration.domain)} "
            f"| {', '.join(f'`{h}`' for h in mechanism.homes)} | {mechanism.enforcement} |"
        )
    out.append("")
    return "\n".join(out)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _row_subject(line: str) -> str:
    """The mechanism a rendered table row is about, for localized reporting."""
    return line.split("|")[1].strip() if line.startswith("|") and line.count("|") > 2 else line.strip()


def _differing_rows(current: str, rendered: str) -> list[str]:
    """Name what changed, per DRIFT-RULES Rule 2 -- localize, don't merely fail."""
    was, now = set(current.splitlines()), set(rendered.splitlines())
    stale = {_row_subject(line) for line in was - now if line.strip()}
    fresh = {_row_subject(line) for line in now - was if line.strip()}
    messages = [f"  changed or removed: {subject}" for subject in sorted(stale - fresh)]
    messages += [f"  added or changed:   {subject}" for subject in sorted(fresh - stale)]
    messages += [f"  row differs:        {subject}" for subject in sorted(stale & fresh)]
    return messages or ["  (whitespace or preamble only)"]


def main() -> None:
    parser = argparse.ArgumentParser(description="Wired drift mechanisms → sdd/GATE-INVENTORY.md")
    parser.add_argument("--check", action="store_true", help="Exit 1 if the inventory would change; do not write.")
    args = parser.parse_args()

    try:
        mechanisms, problems = collect()
    except DeclarationError as exc:
        print(f"Drift-gate declaration error: {exc}", file=sys.stderr)
        sys.exit(1)

    if problems:
        for problem in sorted(problems):
            print(problem, file=sys.stderr)
        print(
            "\nEvery wired check_*/gen_*/drift_*/report_* script must declare what it\n"
            "compares. See scripts/gen_gate_inventory.py for the block format.",
            file=sys.stderr,
        )
        sys.exit(1)

    rendered = render(mechanisms)
    current = OUTPUT.read_text(encoding="utf-8") if OUTPUT.exists() else ""

    if args.check:
        if rendered != current:
            for line in _differing_rows(current, rendered):
                print(line, file=sys.stderr)
            print(
                f"\n{OUTPUT.relative_to(ROOT)} is out of date.\nRun:  hatch run gen-gate-inventory",
                file=sys.stderr,
            )
            sys.exit(1)
        print(f"{OUTPUT.relative_to(ROOT)} is up to date ({len(mechanisms)} mechanisms).")
        return

    OUTPUT.write_text(rendered, encoding="utf-8")
    print(f"Wrote {OUTPUT.relative_to(ROOT)} ({len(mechanisms)} mechanisms).")


if __name__ == "__main__":
    main()
