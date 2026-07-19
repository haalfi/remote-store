"""Unit tests for scripts/check_ripple_parity.py.

The gate exists because the ripple-check's two presentations drifted by hand:
the Detailed checklist silently dropped a trigger (`Local-machine reference`)
that the Pre-work index carried, and no reader of either table alone could see
it. The regression cases below reproduce that class of drift -- omission,
reorder, and an unanchored new trigger -- and one case proves the *legitimate*
sync/async expansion still passes, so the gate does not over-fire on the very
shape the header note blesses.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "check_ripple_parity.py"
_REPO_ROOT = Path(__file__).resolve().parents[2]


def _load():
    spec = importlib.util.spec_from_file_location("check_ripple_parity", _SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("check_ripple_parity", mod)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


_mod = _load()


def _reference(pre_rows: str, det_rows: str) -> str:
    """A minimal CLAUDE-REFERENCE.md carrying just the two ripple-check tables.

    ``pre_rows`` / ``det_rows`` are the Markdown lines between the section
    headers, so a test states only the triggers it cares about.
    """
    return (
        "## Ripple-check table\n\n"
        '<a id="pre-work-index"></a>\n'
        "### Pre-work index\n\n"
        f"{pre_rows}\n"
        '<a id="detailed-checklist"></a>\n'
        "### Detailed checklist\n\n"
        f"{det_rows}\n"
        "---\n\n"
        "## Next section\n"
    )


def _violations(tmp_path: Path, pre_rows: str, det_rows: str) -> list:
    ref = tmp_path / "CLAUDE-REFERENCE.md"
    ref.write_text(_reference(pre_rows, det_rows), encoding="utf-8")
    return _mod.collect_violations(ref)


# A faithful two-trigger fixture with a real sync/async expansion in the
# Detailed checklist. Reused as the "clean" baseline the mutation cases bend.
_PRE = (
    "#### Code surface\n\n"
    "| Trigger        | Ripples |\n"
    "|----------------|---------|\n"
    "| Backend        | README backends table |\n"
    "| `_GATING` dict | sync in `_store.py`, async in `aio/` |\n"
)
_DET = (
    "#### Code surface\n\n"
    "| Trigger            | Also check |\n"
    "|--------------------|------------|\n"
    "| **Backend**        | README backends table, extras |\n"
    "|                    | docs nav, examples |\n"
    "| **`_GATING` dict** | `001-store-api.md`, `test_store.py` |\n"
    "| (in `_store.py`)   | store.md admonitions |\n"
    "| **`_GATING` dict** (async) | mirrors the sync constant |\n"
    "| (in `aio/`)        | consumed by AsyncStore._gate() |\n"
)


class TestParsing:
    def test_pre_work_one_trigger_per_row(self, tmp_path: Path) -> None:
        text = _reference(_PRE, _DET)
        pre_block, _ = _mod._blocks(text)
        names = [t.name for t in _mod._parse_pre_work(pre_block)]
        assert names == ["Backend", "`_GATING` dict"]

    def test_detailed_bold_cells_are_triggers(self, tmp_path: Path) -> None:
        text = _reference(_PRE, _DET)
        _, det_block = _mod._blocks(text)
        names = [t.name for t in _mod._parse_detailed(det_block)]
        # Continuation rows (empty / `(qualifier)` leading cell) are not triggers;
        # the async split is a distinct trigger, not a duplicate of the sync one.
        assert names == ["Backend", "`_GATING` dict", "`_GATING` dict (async)"]

    def test_section_travels_with_the_trigger(self, tmp_path: Path) -> None:
        text = _reference(_PRE, _DET)
        pre_block, _ = _mod._blocks(text)
        assert all(t.section == "Code surface" for t in _mod._parse_pre_work(pre_block))


class TestInvariant:
    def test_expansion_baseline_passes(self, tmp_path: Path) -> None:
        """The sync/async split the header note blesses must not fire the gate."""
        assert _violations(tmp_path, _PRE, _DET) == []

    def test_omitted_trigger_fails(self, tmp_path: Path) -> None:
        """The exact drift the gate exists to stop: a Pre-work trigger dropped
        from the Detailed checklist (the live `Local-machine reference` bug)."""
        det = (
            "#### Code surface\n\n"
            "| Trigger     | Also check |\n"
            "|-------------|------------|\n"
            "| **Backend** | README backends table |\n"
        )
        violations = _violations(tmp_path, _PRE, det)
        assert len(violations) == 1
        assert "`_GATING` dict" in violations[0].message
        assert "missing" in violations[0].message

    def test_reordered_shared_trigger_fails(self, tmp_path: Path) -> None:
        det = (
            "#### Code surface\n\n"
            "| Trigger            | Also check |\n"
            "|--------------------|------------|\n"
            "| **`_GATING` dict** | spec |\n"
            "| **Backend**        | README backends table |\n"
        )
        violations = _violations(tmp_path, _PRE, det)
        assert len(violations) == 1
        assert "out of order" in violations[0].message

    def test_section_leading_unanchored_expansion_fails(self, tmp_path: Path) -> None:
        """A Detailed-only trigger that *leads* its section is flagged: no shared
        trigger precedes it, so it cannot be a legitimate expansion."""
        pre = "#### Code surface\n\n| Trigger  | Ripples |\n|----------|---------|\n| Backend  | table |\n"
        det = (
            "#### Code surface\n\n"
            "| Trigger           | Also check |\n"
            "|-------------------|------------|\n"
            "| **Brand new only** | invented here |\n"
            "| **Backend**       | table |\n"
        )
        violations = _violations(tmp_path, pre, det)
        assert any("Brand new only" in v.message for v in violations)

    def test_unanchored_expansion_after_shared_trigger_passes(self, tmp_path: Path) -> None:
        """Documents the gate's known blind spot (PR #921 review): a Detailed-only
        trigger placed *after* a shared trigger is indistinguishable from a
        legitimate sync/async expansion, so it passes. The docstring and header
        note state this scope; this test locks it so a future change that tightens
        the gate updates the prose too."""
        pre = "#### Code surface\n\n| Trigger  | Ripples |\n|----------|---------|\n| Backend  | table |\n"
        det = (
            "#### Code surface\n\n"
            "| Trigger              | Also check |\n"
            "|----------------------|------------|\n"
            "| **Backend**          | table |\n"
            "| **Forgotten in pre** | invented here, after a shared trigger |\n"
        )
        assert _violations(tmp_path, pre, det) == []

    def test_empty_blocks_fail_loudly(self, tmp_path: Path) -> None:
        """A structural change that empties a table fails rather than passing
        vacuously."""
        violations = _violations(tmp_path, "#### Code surface\n\nno table here\n", _DET)
        assert violations
        assert any("no triggers parsed" in v.message for v in violations)

    def test_name_wrapped_across_two_bold_cells_fails(self, tmp_path: Path) -> None:
        """Guard the parser contract: a name split across two bold cells reads as
        two unknown triggers and fails, steering the editor to the single-cell
        form."""
        det = (
            "#### Code surface\n\n"
            "| Trigger     | Also check |\n"
            "|-------------|------------|\n"
            "| **Back**    | first half |\n"
            "| **end**     | second half |\n"
            "| **`_GATING` dict** | spec |\n"
            "| **`_GATING` dict** (async) | mirror |\n"
        )
        violations = _violations(tmp_path, _PRE, det)
        assert violations  # "Backend" is not "Back" + "end"


class TestRepository:
    def test_repo_is_in_parity(self) -> None:
        """The invariant the header note asserts actually holds in the tree."""
        violations = _mod.collect_violations()
        assert violations == [], "\n".join(f"line {v.line}: {v.message}" for v in violations)

    def test_gate_reads_the_real_reference(self) -> None:
        text = _mod._REFERENCE.read_text(encoding="utf-8")
        pre_block, det_block = _mod._blocks(text)
        pre = _mod._parse_pre_work(pre_block)
        det = _mod._parse_detailed(det_block)
        # Both presentations parse to a non-trivial, matching trigger spine.
        assert len(pre) >= 20
        assert {t.key for t in pre} <= {t.key for t in det}
