"""Unit tests for scripts/check_process_budget.py.

Each test builds a small tree and budget under ``tmp_path``. The two failure
directions are pinned separately because each guards a different leak: growth
without a recorded raise, and a cut left unlocked as credit.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "check_process_budget.py"


def _load():
    spec = importlib.util.spec_from_file_location("check_process_budget", _SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("check_process_budget", mod)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


_mod = _load()


def _tree(root: Path, files: dict[str, bytes], total: int | None = None, slack: float = 0.02) -> None:
    for rel, body in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)
    sizes = {rel: len(body) for rel, body in files.items()}
    budget = {
        "globs": ["CLAUDE.md", ".claude/skills/*/SKILL.md"],
        "slack": slack,
        "total": sum(sizes.values()) if total is None else total,
        "files": sizes,
        "raises": [],
    }
    (root / "sdd").mkdir(exist_ok=True)
    (root / "sdd" / "process-budget.json").write_text(json.dumps(budget), encoding="utf-8")


def _budget(root: Path) -> dict:
    return json.loads((root / "sdd" / "process-budget.json").read_text(encoding="utf-8"))


_BASE = {"CLAUDE.md": b"a" * 100, ".claude/skills/ship/SKILL.md": b"b" * 100}


class TestCheck:
    def test_exact_total_passes(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        _tree(tmp_path, _BASE)
        assert _mod.main([], root=tmp_path) == 0
        assert "200 of 200 bytes (2 files)" in capsys.readouterr().out

    def test_growth_fails_and_names_the_file(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        _tree(tmp_path, _BASE)
        (tmp_path / ".claude/skills/ship/SKILL.md").write_bytes(b"b" * 130)
        assert _mod.main([], root=tmp_path) == 1
        err = capsys.readouterr().err
        assert "+30" in err
        assert ".claude/skills/ship/SKILL.md (100 -> 130)" in err
        assert "--raise" in err

    def test_growth_offset_by_a_cut_elsewhere_passes(self, tmp_path: Path) -> None:
        _tree(tmp_path, _BASE)
        (tmp_path / "CLAUDE.md").write_bytes(b"a" * 70)
        (tmp_path / ".claude/skills/ship/SKILL.md").write_bytes(b"b" * 130)
        assert _mod.main([], root=tmp_path) == 0

    def test_new_skill_counts_against_the_total(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        _tree(tmp_path, _BASE)
        (tmp_path / ".claude/skills/new/").mkdir(parents=True)
        (tmp_path / ".claude/skills/new/SKILL.md").write_bytes(b"c" * 5)
        assert _mod.main([], root=tmp_path) == 1
        assert ".claude/skills/new/SKILL.md (new)" in capsys.readouterr().err

    def test_shrink_within_slack_passes(self, tmp_path: Path) -> None:
        _tree(tmp_path, _BASE, slack=0.02)
        (tmp_path / "CLAUDE.md").write_bytes(b"a" * 96)  # 196 >= floor 196
        assert _mod.main([], root=tmp_path) == 0

    def test_shrink_past_slack_fails_and_asks_for_update(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _tree(tmp_path, _BASE, slack=0.02)
        (tmp_path / "CLAUDE.md").write_bytes(b"a" * 95)  # 195 < floor 196
        assert _mod.main([], root=tmp_path) == 1
        err = capsys.readouterr().err
        assert "--update" in err
        assert "CLAUDE.md (100 -> 95)" in err
        assert "If this PR made no cut" in err

    def test_crlf_measures_as_lf(self, tmp_path: Path) -> None:
        _tree(tmp_path, {"CLAUDE.md": b"x\n" * 50, ".claude/skills/ship/SKILL.md": b"y" * 100})
        (tmp_path / "CLAUDE.md").write_bytes(b"x\r\n" * 50)
        assert _mod.main([], root=tmp_path) == 0

    def test_dead_glob_fails(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        _tree(tmp_path, {"CLAUDE.md": b"a" * 10})
        assert _mod.main([], root=tmp_path) == 1
        assert ".claude/skills/*/SKILL.md" in capsys.readouterr().err


class TestUnreadableBudget:
    """A broken budget file is exit 2 with an instruction, never a traceback or exit 1."""

    _PREFIX = "budget file unreadable: sdd/process-budget.json: "

    def test_conflict_markers(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        _tree(tmp_path, _BASE)
        path = tmp_path / "sdd" / "process-budget.json"
        path.write_text("<<<<<<< HEAD\n" + path.read_text(encoding="utf-8") + "=======\n", encoding="utf-8")
        assert _mod.main([], root=tmp_path) == 2
        assert self._PREFIX + "JSONDecodeError" in capsys.readouterr().err

    def test_missing_key(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        _tree(tmp_path, _BASE)
        budget = _budget(tmp_path)
        del budget["slack"]
        (tmp_path / "sdd" / "process-budget.json").write_text(json.dumps(budget), encoding="utf-8")
        assert _mod.main([], root=tmp_path) == 2
        assert self._PREFIX + "KeyError: 'slack'" in capsys.readouterr().err

    def test_missing_file(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        _tree(tmp_path, _BASE)
        (tmp_path / "sdd" / "process-budget.json").unlink()
        assert _mod.main([], root=tmp_path) == 2
        assert self._PREFIX + "FileNotFoundError" in capsys.readouterr().err


class TestUpdate:
    def test_update_locks_a_cut_in(self, tmp_path: Path) -> None:
        _tree(tmp_path, _BASE)
        (tmp_path / "CLAUDE.md").write_bytes(b"a" * 40)
        assert _mod.main(["--update"], root=tmp_path) == 0
        budget = _budget(tmp_path)
        assert budget["total"] == 140
        assert budget["files"]["CLAUDE.md"] == 40
        assert _mod.main([], root=tmp_path) == 0

    def test_update_refuses_growth(self, tmp_path: Path) -> None:
        _tree(tmp_path, _BASE)
        (tmp_path / "CLAUDE.md").write_bytes(b"a" * 101)
        assert _mod.main(["--update"], root=tmp_path) == 2
        assert _budget(tmp_path)["total"] == 200


class TestRaise:
    def test_raise_records_item_and_reason(self, tmp_path: Path) -> None:
        _tree(tmp_path, _BASE)
        (tmp_path / "CLAUDE.md").write_bytes(b"a" * 150)
        assert _mod.main(["--raise", "--item", "BK-422", "--reason", " new rule "], root=tmp_path) == 0
        budget = _budget(tmp_path)
        assert budget["total"] == 250
        assert budget["raises"] == [{"item": "BK-422", "from": 200, "to": 250, "reason": "new rule"}]
        assert _mod.main([], root=tmp_path) == 0

    @pytest.mark.parametrize(
        "args",
        [
            ["--raise", "--reason", "x"],
            ["--raise", "--item", "BK-422"],
            ["--raise", "--item", "BK-422", "--reason", "  "],
            ["--raise", "--item", "bk422", "--reason", "x"],
        ],
    )
    def test_raise_without_owner_or_reason_is_refused(self, tmp_path: Path, args: list[str]) -> None:
        _tree(tmp_path, _BASE)
        (tmp_path / "CLAUDE.md").write_bytes(b"a" * 150)
        assert _mod.main(args, root=tmp_path) == 2
        assert _budget(tmp_path)["raises"] == []

    def test_raise_within_budget_is_refused(self, tmp_path: Path) -> None:
        _tree(tmp_path, _BASE)
        assert _mod.main(["--raise", "--item", "BK-422", "--reason", "x"], root=tmp_path) == 2
        assert _budget(tmp_path)["total"] == 200
