"""Unit tests for scripts/gen_backlogid.py."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"

if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import gen_backlogid as _mod  # noqa: E402

_extract_ids = _mod._extract_ids
_max_numeric = _mod._max_numeric
_PREFIXES = _mod._PREFIXES

# ---------------------------------------------------------------------------
# _max_numeric
# ---------------------------------------------------------------------------

_EM = "—"  # em dash used in backlog header format


@pytest.mark.parametrize(
    ("ids", "expected"),
    [
        ({"BK-174", "BK-120", "BK-001"}, 174),
        ({"BK-139a", "BK-139b", "BK-139c"}, 139),
        ({"BK-174", "BK-139b"}, 174),
        (set(), 0),
        ({"ID-176"}, 176),
    ],
)
def test_max_numeric(ids, expected):
    assert _max_numeric(ids) == expected


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

    def test_clean_returns_zero(self, tmp_path, monkeypatch, capsys):
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
        result = _mod._check()
        assert result == 0
        out = capsys.readouterr().out
        assert "BK=178" in out
        # Both rules named on the clean path, not just the older one.
        assert "No ID collisions" in out
        assert "no ID on two open items" in out

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

    def test_two_open_items_sharing_an_id_are_reported(self, tmp_path, monkeypatch, capsys):
        """Two *open* headers with one ID must fail the check.

        The real collision: BUG-281's branch and BK-378's each minted `BK-382`
        from a master where 382 was free, and both merged. `_extract_ids`
        returns sets, so the repeat collapsed before any comparison, and
        `_check` only ever compared open against *done* — so a file carrying
        the same ID twice printed "No ID collisions." This is ID-257's
        open-versus-open half, which this change builds and that item now
        hands over.
        """
        duplicate_active = (
            f"- [ ] **BK-382 {_EM} The file-ancestor gate ships unexercised**\n"
            f"- [ ] **BK-177 {_EM} Parametrize self-op tests**\n"
            f"- [ ] **BK-382 {_EM} RFC-0015 is built but unmeasured**\n"
        )
        done, active, id_file = self._setup(
            tmp_path,
            _DONE_BLOCK,
            duplicate_active,
            {"BK": 174, "BUG": 194, "ID": 176, "AF": 40, "BL": 10},
        )
        monkeypatch.setattr(_mod, "BACKLOG_DONE", done)
        monkeypatch.setattr(_mod, "BACKLOG", active)
        monkeypatch.setattr(_mod, "ID_FILE", id_file)
        monkeypatch.setattr(_mod, "ROOT", tmp_path)

        assert _mod._check() == 1
        out = capsys.readouterr().out
        assert "BK-382" in out
        # The count, not just the ID: a reader has to know how many headers to
        # go and find, and "2" is what separates this from the done-collision
        # report above, which names an ID appearing once on each side.
        assert "(2 headers)" in out
        assert "BK-177" not in out

    def test_status_variants_of_one_id_collide(self, tmp_path, monkeypatch, capsys):
        """`- [ ]` and `- [~]` are both open, so one ID across them is a duplicate.

        `_check` reads open items with the status set `" ~"`, so a partially
        done item and a fresh one sharing an ID is the same defect wearing a
        different checkbox — and the likelier shape, since an item in flight is
        what a concurrent branch collides with.
        """
        mixed_active = (
            f"- [ ] **ID-018 {_EM} conda-forge publishing**\n- [~] **ID-018 {_EM} something else entirely**\n"
        )
        done, active, id_file = self._setup(
            tmp_path,
            _DONE_BLOCK,
            mixed_active,
            {"BK": 174, "BUG": 194, "ID": 176, "AF": 40, "BL": 10},
        )
        monkeypatch.setattr(_mod, "BACKLOG_DONE", done)
        monkeypatch.setattr(_mod, "BACKLOG", active)
        monkeypatch.setattr(_mod, "ID_FILE", id_file)
        monkeypatch.setattr(_mod, "ROOT", tmp_path)

        assert _mod._check() == 1
        assert "ID-018" in capsys.readouterr().out

    def test_a_duplicate_and_a_collision_are_both_reported_in_one_run(self, tmp_path, monkeypatch, capsys):
        """Neither failure short-circuits the other.

        The two are independent, so an author who fixes a duplicate and is then
        told about a collision pays two read-fix-rerun cycles for one read of
        the file. Without this, an implementation that returned early inside
        the duplicates block passes every other test here while producing
        exactly that.
        """
        both_active = (
            f"- [ ] **BK-382 {_EM} One open item**\n"
            f"- [ ] **BK-382 {_EM} Another open item**\n"
            f"- [ ] **BK-174 {_EM} Collides with a done item**\n"
        )
        done, active, id_file = self._setup(
            tmp_path,
            _DONE_BLOCK,
            both_active,
            {"BK": 174, "BUG": 194, "ID": 176, "AF": 40, "BL": 10},
        )
        monkeypatch.setattr(_mod, "BACKLOG_DONE", done)
        monkeypatch.setattr(_mod, "BACKLOG", active)
        monkeypatch.setattr(_mod, "ID_FILE", id_file)
        monkeypatch.setattr(_mod, "ROOT", tmp_path)

        assert _mod._check() == 1
        out = capsys.readouterr().out
        assert "duplicate ID" in out
        assert "collision(s)" in out
        assert "BK-382" in out
        assert "BK-174" in out

    def test_a_duplicate_in_the_done_register_is_not_reported(self, tmp_path, monkeypatch, capsys):
        """The stated bound, pinned so it cannot drift silently either way.

        `BACKLOG-DONE.md` collapses the same way and the path is reachable, but
        the register already carries four such pairs from before the ID
        discipline, and renumbering inside released sections would falsify the
        release record. Out of scope by decision, not by oversight — BK-385
        carries it. A future widening has to delete this test, which is the
        point: the bound is not something a reader has to infer.
        """
        duplicate_done = (
            f"- [x] **BK-500 {_EM} One branch closed this**\n"
            f"- [x] **BK-500 {_EM} Another branch closed something else**\n"
        )
        done, active, id_file = self._setup(
            tmp_path, duplicate_done, _ACTIVE_BLOCK, {"BK": 500, "BUG": 0, "ID": 0, "AF": 0, "BL": 0}
        )
        monkeypatch.setattr(_mod, "BACKLOG_DONE", done)
        monkeypatch.setattr(_mod, "BACKLOG", active)
        monkeypatch.setattr(_mod, "ID_FILE", id_file)
        monkeypatch.setattr(_mod, "ROOT", tmp_path)

        assert _mod._check() == 0
        assert "duplicate" not in capsys.readouterr().out

    def test_one_id_open_in_one_file_and_done_in_the_other_is_a_collision(self, tmp_path, monkeypatch, capsys):
        """That is the *collision* case, which has its own report and its own message.

        The duplicate rule is within-file and within-status; conflating the two
        would give one defect two names and send the author to the wrong remedy
        (renumber a concurrent mint, versus close or reopen one item).
        """
        # The SAME id on both sides. Two different ids would make the
        # assertion vacuous: the file would hold neither a collision nor a
        # duplicate, and pass against an implementation with no rule at all.
        done_text = f"- [x] **BK-174 {_EM} Done item**\n"
        active_text = f"- [ ] **BK-174 {_EM} Same id, still open**\n"
        done, active, id_file = self._setup(
            tmp_path, done_text, active_text, {"BK": 174, "BUG": 0, "ID": 0, "AF": 0, "BL": 0}
        )
        monkeypatch.setattr(_mod, "BACKLOG_DONE", done)
        monkeypatch.setattr(_mod, "BACKLOG", active)
        monkeypatch.setattr(_mod, "ID_FILE", id_file)
        monkeypatch.setattr(_mod, "ROOT", tmp_path)

        assert _mod._check() == 1
        out = capsys.readouterr().out
        assert "collision(s)" in out
        assert "duplicate ID" not in out, "one defect must not be reported under both names"

    def test_suffix_variants_are_not_duplicates(self, tmp_path, monkeypatch):
        """`BK-139a` and `BK-139b` are two items, not one appearing twice.

        The split-item suffix is part of the ID (`_HEADER_RE` spells the number
        `\\d+[a-z]*`), so the duplicate check keys on the whole token. Keying on
        the numeric part would make every split item fail the gate that exists
        to protect it.
        """
        split_active = f"- [ ] **BK-139a {_EM} First half**\n- [ ] **BK-139b {_EM} Second half**\n"
        done, active, id_file = self._setup(
            tmp_path,
            _DONE_BLOCK,
            split_active,
            {"BK": 174, "BUG": 194, "ID": 176, "AF": 40, "BL": 10},
        )
        monkeypatch.setattr(_mod, "BACKLOG_DONE", done)
        monkeypatch.setattr(_mod, "BACKLOG", active)
        monkeypatch.setattr(_mod, "ID_FILE", id_file)
        monkeypatch.setattr(_mod, "ROOT", tmp_path)

        assert _mod._check() == 0

    def test_suffix_variant_not_false_positive(self, tmp_path, monkeypatch):
        # Suffixed IDs must not false-positive against each other: the fixture
        # puts BK-139d in the active file and BK-139b in the done file.
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
