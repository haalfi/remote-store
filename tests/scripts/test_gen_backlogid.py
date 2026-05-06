"""Unit tests for scripts/gen_backlogid.py."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "gen_backlogid.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("gen_backlogid", _SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("gen_backlogid", module)
    spec.loader.exec_module(module)
    return module


_mod = _load_module()
_extract_ids = _mod._extract_ids
_max_numeric = _mod._max_numeric
_PREFIXES = _mod._PREFIXES

# ---------------------------------------------------------------------------
# _max_numeric
# ---------------------------------------------------------------------------

_EM = "—"  # em dash used in backlog header format


class TestMaxNumeric:
    def test_plain_ids(self):
        assert _max_numeric({"BK-174", "BK-120", "BK-001"}) == 174

    def test_suffix_ids_use_numeric_part_only(self):
        assert _max_numeric({"BK-139a", "BK-139b", "BK-139c"}) == 139

    def test_mixed_plain_and_suffix(self):
        assert _max_numeric({"BK-174", "BK-139b"}) == 174

    def test_empty_set_returns_zero(self):
        assert _max_numeric(set()) == 0

    def test_single_item(self):
        assert _max_numeric({"ID-176"}) == 176


# ---------------------------------------------------------------------------
# _extract_ids
# ---------------------------------------------------------------------------

_DONE_BLOCK = f"""\
- [x] **BK-174 {_EM} Document something**
  body text here
- [x] **BUG-194 {_EM} Fix a bug**
- [x] **ID-176 {_EM} Wire context7**
- [x] **BK-167b (partial) {_EM} check_links.py link checker**
- [x] **AF-040 {_EM} guides/migration.md**
- [x] **BL-010 {_EM} Publish docs**
"""

_ACTIVE_BLOCK = f"""\
- [ ] **BK-177 {_EM} Parametrize self-op tests**
- [~] **ID-018 {_EM} conda-forge publishing**
- [ ] **BUG-197 {_EM} read_bytes mishandles HNS**
"""


class TestExtractIds:
    def test_extracts_done_items(self):
        ids = _extract_ids(_DONE_BLOCK, "x")
        assert "BK-174" in ids["BK"]
        assert "BUG-194" in ids["BUG"]
        assert "ID-176" in ids["ID"]
        assert "AF-040" in ids["AF"]
        assert "BL-010" in ids["BL"]

    def test_extracts_suffix_ids(self):
        ids = _extract_ids(_DONE_BLOCK, "x")
        assert "BK-167b" in ids["BK"]

    def test_partial_header_style_captured(self):
        ids = _extract_ids(_DONE_BLOCK, "x")
        assert "BK-167b" in ids["BK"]

    def test_active_items_with_space_and_tilde(self):
        ids = _extract_ids(_ACTIVE_BLOCK, " ~")
        assert "BK-177" in ids["BK"]
        assert "ID-018" in ids["ID"]
        assert "BUG-197" in ids["BUG"]

    def test_status_filter_respected(self):
        ids = _extract_ids(_DONE_BLOCK, " ~")
        assert not any(ids[p] for p in _PREFIXES)

    def test_done_filter_excludes_active(self):
        ids = _extract_ids(_ACTIVE_BLOCK, "x")
        assert not any(ids[p] for p in _PREFIXES)


# ---------------------------------------------------------------------------
# _generate (writes JSON)
# ---------------------------------------------------------------------------


class TestGenerate:
    def test_writes_json_with_correct_maxima(self, tmp_path, monkeypatch):
        done = tmp_path / "BACKLOG-DONE.md"
        done.write_text(_DONE_BLOCK, encoding="utf-8")
        id_file = tmp_path / "backlogid.json"

        monkeypatch.setattr(_mod, "BACKLOG_DONE", done)
        monkeypatch.setattr(_mod, "ID_FILE", id_file)
        monkeypatch.setattr(_mod, "ROOT", tmp_path)

        assert _mod._generate() == 0
        data = json.loads(id_file.read_text(encoding="utf-8"))
        assert data["BK"] == 174
        assert data["BUG"] == 194
        assert data["ID"] == 176
        assert data["AF"] == 40
        assert data["BL"] == 10

    def test_generate_is_idempotent(self, tmp_path, monkeypatch):
        done = tmp_path / "BACKLOG-DONE.md"
        done.write_text(_DONE_BLOCK, encoding="utf-8")
        id_file = tmp_path / "backlogid.json"

        monkeypatch.setattr(_mod, "BACKLOG_DONE", done)
        monkeypatch.setattr(_mod, "ID_FILE", id_file)
        monkeypatch.setattr(_mod, "ROOT", tmp_path)

        _mod._generate()
        first = id_file.read_text(encoding="utf-8")
        _mod._generate()
        assert id_file.read_text(encoding="utf-8") == first


# ---------------------------------------------------------------------------
# _check (read-only validation)
# ---------------------------------------------------------------------------


def _write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


class TestCheck:
    def _setup(self, tmp_path, done_text, active_text, json_data):
        done = tmp_path / "BACKLOG-DONE.md"
        done.write_text(done_text, encoding="utf-8")
        active = tmp_path / "BACKLOG.md"
        active.write_text(active_text, encoding="utf-8")
        id_file = tmp_path / "backlogid.json"
        _write_json(id_file, json_data)
        return done, active, id_file

    def test_clean_returns_zero(self, tmp_path, monkeypatch):
        done, active, id_file = self._setup(
            tmp_path,
            _DONE_BLOCK,
            _ACTIVE_BLOCK,
            {"BK": 174, "BUG": 194, "ID": 176, "AF": 40, "BL": 10},
        )
        monkeypatch.setattr(_mod, "BACKLOG_DONE", done)
        monkeypatch.setattr(_mod, "BACKLOG", active)
        monkeypatch.setattr(_mod, "ID_FILE", id_file)
        monkeypatch.setattr(_mod, "ROOT", tmp_path)
        assert _mod._check() == 0

    def test_collision_returns_one(self, tmp_path, monkeypatch, capsys):
        collision_active = f"- [ ] **BK-174 {_EM} Duplicate item**\n"
        done, active, id_file = self._setup(
            tmp_path,
            _DONE_BLOCK,
            collision_active,
            {"BK": 174, "BUG": 194, "ID": 176, "AF": 40, "BL": 10},
        )
        monkeypatch.setattr(_mod, "BACKLOG_DONE", done)
        monkeypatch.setattr(_mod, "BACKLOG", active)
        monkeypatch.setattr(_mod, "ID_FILE", id_file)
        monkeypatch.setattr(_mod, "ROOT", tmp_path)
        result = _mod._check()
        assert result == 1
        out = capsys.readouterr().out
        assert "BK-174" in out

    def test_stale_json_returns_one(self, tmp_path, monkeypatch, capsys):
        done, active, id_file = self._setup(
            tmp_path,
            _DONE_BLOCK,
            _ACTIVE_BLOCK,
            {"BK": 100, "BUG": 194, "ID": 176, "AF": 40, "BL": 10},  # BK stale
        )
        monkeypatch.setattr(_mod, "BACKLOG_DONE", done)
        monkeypatch.setattr(_mod, "BACKLOG", active)
        monkeypatch.setattr(_mod, "ID_FILE", id_file)
        monkeypatch.setattr(_mod, "ROOT", tmp_path)
        result = _mod._check()
        assert result == 1
        out = capsys.readouterr().out
        assert "STALE" in out
        assert "gen-backlogid" in out

    def test_missing_json_returns_one(self, tmp_path, monkeypatch, capsys):
        done = tmp_path / "BACKLOG-DONE.md"
        done.write_text(_DONE_BLOCK, encoding="utf-8")
        active = tmp_path / "BACKLOG.md"
        active.write_text(_ACTIVE_BLOCK, encoding="utf-8")
        id_file = tmp_path / "backlogid.json"  # intentionally not created

        monkeypatch.setattr(_mod, "BACKLOG_DONE", done)
        monkeypatch.setattr(_mod, "BACKLOG", active)
        monkeypatch.setattr(_mod, "ID_FILE", id_file)
        monkeypatch.setattr(_mod, "ROOT", tmp_path)
        result = _mod._check()
        assert result == 1
        assert "gen-backlogid" in capsys.readouterr().out

    def test_suffix_variant_not_false_positive(self, tmp_path, monkeypatch):
        # BK-139d is active; BK-139b is done — different IDs, no collision.
        done_text = f"- [x] **BK-139b {_EM} Done item**\n"
        active_text = f"- [ ] **BK-139d {_EM} Active remainder**\n"
        done, active, id_file = self._setup(
            tmp_path,
            done_text,
            active_text,
            {"BK": 139, "BUG": 0, "ID": 0, "AF": 0, "BL": 0},
        )
        monkeypatch.setattr(_mod, "BACKLOG_DONE", done)
        monkeypatch.setattr(_mod, "BACKLOG", active)
        monkeypatch.setattr(_mod, "ID_FILE", id_file)
        monkeypatch.setattr(_mod, "ROOT", tmp_path)
        assert _mod._check() == 0
