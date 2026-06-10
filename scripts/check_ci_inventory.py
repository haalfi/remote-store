"""PR-time gate: every scheduled/automated workflow is inventoried in the
CI-operations handbook.

`sdd/CI-OPERATIONS.md` is the single authority that inventories the
scheduled/automated workflow family and states the durable-TODO principle.
Hand-maintained prose rots the moment a tenth workflow lands, so this gate
parses every workflow file under `.github/workflows/` (`*.yml` and `*.yaml` —
GitHub Actions honours both) for the family triggers
(`on.schedule` / `on.pull_request_review`) and fails if a family workflow is
not named in the handbook. That is the high-value direction: it makes adding a
guard without documenting it a lint failure.

What this gate does NOT check: that a workflow's documented surface (rolling
issue / triage skill / Security-tab exception) is correct or even present.
That is human prose the workflow YAML cannot express, and is reviewer-enforced
(handbook Rule 2). `codeql.yml` passes because the handbook names it under its
_Exceptions_ section, not because of any allowlist here — the handbook is the
single source of which guards are exceptions, so this script does not duplicate
that list.

Scope note: the gate judges files under `.github/workflows/` only. The
dependabot update streams (`.github/dependabot.yml`) are documented in the
handbook as prose but not parsed here; enforcing their inventory would mean
parsing a second config format, which is deferred until it earns its keep.

Exit 0 when all checks pass. Non-zero on failure; one line per violation to
stderr, sorted for stable diffs.

Run with:
    hatch run lint                       # bundled
    python scripts/check_ci_inventory.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS_DIR = ROOT / ".github" / "workflows"
HANDBOOK = ROOT / "sdd" / "CI-OPERATIONS.md"

# Triggers that define the "scheduled / automated maintenance" family: a guard
# that runs without a contributor present to read a red X. Keep in step with the
# handbook's principle (sdd/CI-OPERATIONS.md Rule 1).
FAMILY_TRIGGERS = frozenset({"schedule", "pull_request_review"})

# `on` is a YAML 1.1 boolean keyword, so PyYAML's safe_load parses the top-level
# `on:` mapping key as the Python bool ``True`` rather than the string "on".
# Accept both so the trigger set is read correctly regardless.
_ON_KEYS: tuple[object, ...] = ("on", True)


def _on_node(path: Path) -> object:
    """Return the value of a workflow's top-level ``on:`` key, or None."""
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return None
    for key in _ON_KEYS:
        if key in data:
            return data[key]
    return None


def _triggers(on: object) -> set[str]:
    """Normalise an ``on:`` node to the set of trigger names it declares."""
    if isinstance(on, str):
        return {on}
    if isinstance(on, list):
        return {t for t in on if isinstance(t, str)}
    if isinstance(on, dict):
        return {str(k) for k in on}
    return set()


def _workflow_files(workflows_dir: Path) -> list[Path]:
    """Every workflow file in *workflows_dir*, sorted by name.

    GitHub Actions honours both ``.yml`` and ``.yaml`` for workflow files, so a
    guard committed as ``foo.yaml`` must be judged too — otherwise it would slip
    past the gate, which is exactly the "added a guard without documenting it"
    case the gate exists to catch.
    """
    return sorted(
        (*workflows_dir.glob("*.yml"), *workflows_dir.glob("*.yaml")),
        key=lambda p: p.name,
    )


def family_workflows(workflows_dir: Path) -> list[str]:
    """Workflow basenames that run on a family trigger, sorted."""
    return [wf.name for wf in _workflow_files(workflows_dir) if _triggers(_on_node(wf)) & FAMILY_TRIGGERS]


def check(workflows_dir: Path, handbook: Path) -> list[str]:
    """Return sorted violation strings; empty list means the inventory is honest."""
    if not handbook.exists():
        return [f"CI-inventory: handbook not found at {handbook}"]

    text = handbook.read_text(encoding="utf-8")
    triggers = "/".join(sorted(FAMILY_TRIGGERS))
    errors = [
        f"CI-inventory: {name} runs on a family trigger ({triggers}) but is "
        f"not documented in {handbook.name} — add it to the inventory table or "
        f"the Exceptions section"
        for name in family_workflows(workflows_dir)
        if name not in text
    ]
    return sorted(errors)


def main() -> int:
    errors = check(WORKFLOWS_DIR, HANDBOOK)
    if errors:
        for line in errors:
            print(line, file=sys.stderr)
        return 1
    print("ci-inventory check passed (every scheduled/automated workflow is documented).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
