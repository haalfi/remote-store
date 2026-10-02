"""Unit tests for scripts/gen_backlogid.py."""

from __future__ import annotations

import json
import subprocess
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
# R1: every open item carries this line directly under its header.
_ATTR = "  spec: — · effort: S · audience: contributor.tooling"


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
{_ATTR}
- [~] **ID-018 {_EM} conda-forge publishing**
{_ATTR}
- [ ] **BUG-197 {_EM} read_bytes mishandles HNS**
{_ATTR}
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
        collision_active = f"- [ ] **BK-174 {_EM} Duplicate item**\n{_ATTR}\n"
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
            f"- [ ] **BK-382 {_EM} The file-ancestor gate ships unexercised**\n{_ATTR}\n"
            f"- [ ] **BK-177 {_EM} Parametrize self-op tests**\n{_ATTR}\n"
            f"- [ ] **BK-382 {_EM} RFC-0015 is built but unmeasured**\n{_ATTR}\n"
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
            f"- [ ] **ID-018 {_EM} conda-forge publishing**\n{_ATTR}\n"
            f"- [~] **ID-018 {_EM} something else entirely**\n{_ATTR}\n"
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
            f"- [ ] **BK-382 {_EM} One open item**\n{_ATTR}\n"
            f"- [ ] **BK-382 {_EM} Another open item**\n{_ATTR}\n"
            f"- [ ] **BK-174 {_EM} Collides with a done item**\n{_ATTR}\n"
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

    def _run_done(self, tmp_path, monkeypatch, done_text, **maxima):
        stored = {"BK": 0, "BUG": 0, "ID": 0, "AF": 0, "BL": 0} | maxima
        done, active, id_file = self._setup(tmp_path, done_text, _ACTIVE_BLOCK, stored)
        monkeypatch.setattr(_mod, "BACKLOG_DONE", done)
        monkeypatch.setattr(_mod, "BACKLOG", active)
        monkeypatch.setattr(_mod, "ID_FILE", id_file)
        monkeypatch.setattr(_mod, "ROOT", tmp_path)
        return _mod._check()

    def test_two_closes_of_one_id_under_unreleased_are_reported(self, tmp_path, monkeypatch, capsys):
        """BK-385: two branches mint one ID and each closes its item before merging.

        Neither ID is ever open, so the open-side rules see nothing; without this
        the register keeps two completed items under one ID for good.
        """
        done_text = (
            "## Unreleased\n\n"
            f"- [x] **BK-500 {_EM} One branch closed this**\n"
            f"- [x] **BK-500 {_EM} Another branch closed something else**\n\n"
            "## v0.1.0\n\n"
            f"- [x] **BK-001 {_EM} Old item**\n"
        )
        assert self._run_done(tmp_path, monkeypatch, done_text, BK=500) == 1
        out = capsys.readouterr().out
        assert "BK-500 (2 headers)" in out
        assert "BACKLOG-DONE.md" in out
        assert "BK-001" not in out

    def test_a_close_colliding_with_released_history_is_reported(self, tmp_path, monkeypatch, capsys):
        """One header in the live region is enough: a new close reusing a released ID."""
        done_text = (
            "## Unreleased\n\n"
            f"- [x] **BK-001 {_EM} New close reusing an old ID**\n\n"
            "## v0.1.0\n\n"
            f"- [x] **BK-001 {_EM} Old item**\n"
        )
        assert self._run_done(tmp_path, monkeypatch, done_text, BK=1) == 1
        assert "BK-001 (2 headers)" in capsys.readouterr().out

    def test_absorbed_and_decided_against_sections_are_live(self, tmp_path, monkeypatch, capsys):
        """Everything above the first `## v<digit>` heading is live, not only `## Unreleased`."""
        done_text = (
            "## Absorbed\n\n"
            f"- [x] **ID-900 {_EM} Absorbed into a host**\n\n"
            "## Unreleased\n\n"
            f"- [x] **ID-900 {_EM} Shipped under the same ID**\n"
        )
        assert self._run_done(tmp_path, monkeypatch, done_text, ID=900) == 1
        assert "ID-900 (2 headers)" in capsys.readouterr().out

    def test_stated_bound_a_pair_wholly_in_released_history_is_not_reported(self, tmp_path, monkeypatch, capsys):
        """The bound, pinned: the four pre-discipline pairs live wholly below `## v…`.

        Renumbering inside released sections would falsify the release record,
        and no new pair can arrive there without first passing the live region.
        Widening the rule to released history deletes this test.
        """
        done_text = (
            "## Unreleased\n\n*(none)*\n\n"
            "## v0.2.0\n\n"
            f"- [x] **BK-001 {_EM} Audit workflow**\n\n"
            "## v0.1.0\n\n"
            f"- [x] **BK-001 {_EM} Azure backend**\n"
        )
        assert self._run_done(tmp_path, monkeypatch, done_text, BK=1) == 0
        assert "duplicate" not in capsys.readouterr().out

    def test_split_suffixes_in_the_done_register_are_not_duplicates(self, tmp_path, monkeypatch):
        done_text = f"## Unreleased\n\n- [x] **BK-139a {_EM} First**\n- [x] **BK-139b {_EM} Second**\n"
        assert self._run_done(tmp_path, monkeypatch, done_text, BK=139) == 0

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
        active_text = f"- [ ] **BK-174 {_EM} Same id, still open**\n{_ATTR}\n"
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
        split_active = f"- [ ] **BK-139a {_EM} First half**\n{_ATTR}\n- [ ] **BK-139b {_EM} Second half**\n{_ATTR}\n"
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
        active_text = f"- [ ] **BK-139d {_EM} Active remainder**\n{_ATTR}\n"
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


# ---------------------------------------------------------------------------
# --remote: a mint's view of pushed branches (ID-257)
# ---------------------------------------------------------------------------


def _git(cwd: Path, *args: str) -> str:
    # Signing and identity pinned so the test does not inherit a host config.
    cmd = ["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", "-c", "commit.gpgsign=false"]
    return subprocess.run([*cmd, "-C", str(cwd), *args], check=True, capture_output=True, text=True).stdout


def _open_item(item_id: str) -> str:
    return f"- [ ] **{item_id} {_EM} Minted here**\n{_ATTR}\n"


class TestRemote:
    """Two clones of one bare remote, standing in for two parallel sessions.

    Session A mints on a pushed branch; session B is the tree under check, so
    the module's paths point into B. Nothing here touches the network: the
    remote is a local bare repository.
    """

    @pytest.fixture
    def clones(self, tmp_path, monkeypatch):
        origin = tmp_path / "origin.git"
        _git(tmp_path, "init", "--quiet", "--bare", "--initial-branch=master", str(origin))
        seed = tmp_path / "seed"
        _git(tmp_path, "clone", "--quiet", str(origin), str(seed))
        (seed / "sdd").mkdir()
        (seed / "sdd" / "BACKLOG-DONE.md").write_text(_DONE_BLOCK, encoding="utf-8")
        (seed / "sdd" / "BACKLOG.md").write_text(_ACTIVE_BLOCK, encoding="utf-8")
        _write_json(seed / "sdd" / "backlogid.json", _CLEAN_JSON)
        _git(seed, "checkout", "--quiet", "-B", "master")
        _git(seed, "add", "-A")
        _git(seed, "commit", "--quiet", "-m", "seed")
        _git(seed, "push", "--quiet", "origin", "master")
        a, b = tmp_path / "a", tmp_path / "b"
        for clone in (a, b):
            _git(tmp_path, "clone", "--quiet", str(origin), str(clone))
        _git(b, "checkout", "--quiet", "-b", "b-work")
        monkeypatch.setattr(_mod, "ROOT", b)
        monkeypatch.setattr(_mod, "BACKLOG", b / "sdd" / "BACKLOG.md")
        monkeypatch.setattr(_mod, "BACKLOG_DONE", b / "sdd" / "BACKLOG-DONE.md")
        monkeypatch.setattr(_mod, "ID_FILE", b / "sdd" / "backlogid.json")
        return a, b

    @staticmethod
    def _mint(clone: Path, item_id: str, branch: str | None, push: bool = True) -> None:
        """Add an open item; commit and push it on ``branch`` (``None``: leave it uncommitted)."""
        backlog = clone / "sdd" / "BACKLOG.md"
        backlog.write_text(backlog.read_text(encoding="utf-8") + _open_item(item_id), encoding="utf-8")
        if branch is None:
            return
        _git(clone, "checkout", "--quiet", "-B", branch)
        _git(clone, "commit", "--quiet", "-am", f"{item_id}: mint")
        if push:
            _git(clone, "push", "--quiet", "origin", branch)

    def test_an_id_minted_on_another_pushed_branch_is_reported(self, clones, capsys):
        """The ID-257 collision, before either branch merges: both sessions mint ID-900."""
        a, b = clones
        self._mint(a, "ID-900", "a-work")
        self._mint(b, "ID-900", None)  # B has not even committed yet
        assert _mod._check(remote=True) == 1
        out = capsys.readouterr().out
        assert "ID-900 also minted on origin/a-work" in out

    def test_the_offline_check_cannot_see_it(self, clones, capsys):
        """Same state without the flag: the local gate has no view of A and passes."""
        a, b = clones
        self._mint(a, "ID-900", "a-work")
        self._mint(b, "ID-900", None)
        assert _mod._check() == 0
        assert "a-work" not in capsys.readouterr().out

    def test_distinct_mints_pass_and_raise_the_floor(self, clones, capsys):
        a, b = clones
        self._mint(a, "ID-900", "a-work")
        self._mint(b, "ID-901", None)
        assert _mod._check(remote=True) == 0
        out = capsys.readouterr().out
        assert "Next safe IDs across pushed branches:" in out
        assert "ID=902" in out

    def test_this_branch_pushed_is_not_its_own_clash(self, clones, capsys):
        _a, b = clones
        self._mint(b, "ID-900", "b-work")
        assert _mod._check(remote=True) == 0
        assert "also minted" not in capsys.readouterr().out

    def test_an_id_master_gained_after_this_branch_forked_is_reported(self, clones, capsys):
        """A merged in the meantime: the clash is with master, not with a branch."""
        a, b = clones
        self._mint(a, "ID-900", "master")
        self._mint(b, "ID-900", None)
        assert _mod._check(remote=True) == 1
        assert "ID-900 also minted on origin/master" in capsys.readouterr().out

    def test_an_unreachable_remote_fails_loud(self, clones, tmp_path, capsys):
        _a, b = clones
        _git(b, "remote", "set-url", "origin", str(tmp_path / "gone.git"))
        assert _mod._check(remote=True) == 1
        assert "ERROR: --remote could not fetch origin" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# R1: attribute vocabulary (RFC-0016 D5, ADR-0040)
# ---------------------------------------------------------------------------

_CLEAN_JSON = {"BK": 174, "BUG": 194, "ID": 176, "AF": 40, "BL": 10}


class TestAttributeVocabulary:
    def _run(self, tmp_path, monkeypatch, active_text, done_text=_DONE_BLOCK):
        done = tmp_path / "BACKLOG-DONE.md"
        done.write_text(done_text, encoding="utf-8")
        active = tmp_path / "BACKLOG.md"
        active.write_text(active_text, encoding="utf-8")
        id_file = tmp_path / "backlogid.json"
        _write_json(id_file, _CLEAN_JSON)
        monkeypatch.setattr(_mod, "BACKLOG_DONE", done)
        monkeypatch.setattr(_mod, "BACKLOG", active)
        monkeypatch.setattr(_mod, "ID_FILE", id_file)
        monkeypatch.setattr(_mod, "ROOT", tmp_path)
        return _mod._check()

    def test_open_item_without_attribute_line_fails(self, tmp_path, monkeypatch, capsys):
        """A missing line would otherwise let an item bypass the vocabulary check."""
        active = f"- [ ] **BK-177 {_EM} No attributes**\n  Diagnosis starts here.\n"
        assert self._run(tmp_path, monkeypatch, active) == 1
        out = capsys.readouterr().out
        assert "line 2: BK-177: no attribute line" in out

    @pytest.mark.parametrize("effort", ["XS", "S/M", "XS/S", "S to define, M per run", "—"])
    def test_effort_outside_legend_fails(self, tmp_path, monkeypatch, capsys, effort):
        # The first four are values the tree carried when R1 landed; `—` is the
        # legend's old "not applicable", which RFC-0016 did not keep for effort.
        active = f"- [ ] **BK-177 {_EM} Title**\n  spec: — · effort: {effort} · audience: infra.ci\n"
        assert self._run(tmp_path, monkeypatch, active) == 1
        assert f"line 2: BK-177: effort {effort!r}" in capsys.readouterr().out

    def test_audience_outside_schema_enum_fails(self, tmp_path, monkeypatch, capsys):
        """`contributor` is the bare value ID-242 carried; the enum has only dotted forms."""
        active = f"- [ ] **ID-242 {_EM} Title**\n  spec: — · effort: S · audience: user.api, contributor\n"
        assert self._run(tmp_path, monkeypatch, active) == 1
        out = capsys.readouterr().out
        assert "line 2: ID-242: audience 'contributor'" in out
        assert "audience 'user.api'" not in out

    def test_every_schema_audience_and_multi_value_passes(self, tmp_path, monkeypatch):
        """The enum is read from sdd/traces/_schema.yml, not copied here."""
        enum = sorted(_mod._audience_enum())
        assert "infra.test" in enum  # an empty parse must not pass vacuously
        active = "".join(
            f"- [ ] **BK-{200 + n} {_EM} T**\n  spec: — · effort: L · audience: {a}, {enum[0]}\n"
            for n, a in enumerate(enum)
        )
        assert self._run(tmp_path, monkeypatch, active) == 0

    def test_done_register_is_not_checked(self, tmp_path, monkeypatch):
        """Bound: R1 covers open items; BACKLOG-DONE.md entries carry no attribute line."""
        done = _DONE_BLOCK.replace("  body text here", "  effort: XS")
        assert "effort: XS" in done
        assert self._run(tmp_path, monkeypatch, _ACTIVE_BLOCK, done_text=done) == 0

    def test_r1_is_reported_alongside_a_duplicate(self, tmp_path, monkeypatch, capsys):
        """R1 does not short-circuit the ID rules, nor they it."""
        active = (
            f"- [ ] **BK-382 {_EM} One**\n{_ATTR}\n"
            f"- [ ] **BK-382 {_EM} Two**\n  spec: — · effort: XS · audience: infra.ci\n"
        )
        assert self._run(tmp_path, monkeypatch, active) == 1
        out = capsys.readouterr().out
        assert "duplicate ID" in out
        assert "effort 'XS'" in out


# ---------------------------------------------------------------------------
# R2 item cap, R3 section shape, R4 dossier link (RFC-0016 D5, ADR-0040)
# ---------------------------------------------------------------------------

_RULES = (
    "# Development Backlog\n\n"
    '<a id="how-this-file-works"></a>\n'
    "## How this file works\n\n"
    "Rules. Many sentences. Never gated. By R3. Or anything.\n\n"
    "**Status legend:** `[ ]` pending\n\n---\n\n"
)
_RETIRED_MARKER = "<!-- backlog: unconverted -->"
_BLOCKERS = "## Release Blockers\n\n**Promise:** nothing ships to PyPI until this section is empty.\n\n---\n\n"


def _item(item_id: str, diagnosis_lines: int, detail: str | None = None) -> str:
    body = "".join(f"  Diagnosis line {n}.\n" for n in range(diagnosis_lines))
    tail = f"  Detail: [dossier]({detail})\n" if detail else ""
    return f"- [ ] **{item_id} {_EM} Title**\n{_ATTR}\n{body}{tail}"


def _section(anchor: str, title: str, preamble: str, *items: str, marker: bool = False) -> str:
    """`marker` puts ADR-0040's retired migration marker under the heading.

    Since ADR-0041 it exempts nothing: the gate reads it as preamble text, so R3 fails on it.
    """
    marker_line = f"{_RETIRED_MARKER}\n" if marker else ""
    return f'<a id="{anchor}"></a>\n## {title}\n{marker_line}\n{preamble}\n\n' + "\n".join(items) + "\n---\n\n"


def _gated(preamble: str, *items: str) -> str:
    """A rules header, Release Blockers and one section."""
    return _RULES + _BLOCKERS + _section("a", "1. A", preamble, *items)


class TestShape:
    def _run(self, tmp_path, monkeypatch, active_text):
        done = tmp_path / "BACKLOG-DONE.md"
        done.write_text(_DONE_BLOCK, encoding="utf-8")
        active = tmp_path / "BACKLOG.md"
        active.write_text(active_text, encoding="utf-8")
        id_file = tmp_path / "backlogid.json"
        _write_json(id_file, _CLEAN_JSON)
        monkeypatch.setattr(_mod, "BACKLOG_DONE", done)
        monkeypatch.setattr(_mod, "BACKLOG", active)
        monkeypatch.setattr(_mod, "ID_FILE", id_file)
        monkeypatch.setattr(_mod, "ROOT", tmp_path)
        return _mod._check()

    def _dossier(self, tmp_path, name: str, header_id: str) -> str:
        (tmp_path / "backlog").mkdir(exist_ok=True)
        (tmp_path / "backlog" / name).write_text(
            f"# {header_id} {_EM} Title\n<!-- doc: repo-only -->\n\nBody.\n", encoding="utf-8"
        )
        return f"backlog/{name}"

    # -- R2 -----------------------------------------------------------------

    def test_an_item_over_eight_content_lines_fails_naming_it_and_its_length(self, tmp_path, monkeypatch, capsys):
        assert self._run(tmp_path, monkeypatch, _gated("**Promise:** one.", _item("BUG-276", 7))) == 1
        assert "BUG-276: 9 content lines (cap 8)" in capsys.readouterr().out

    def test_eight_lines_with_detail_pass_and_separators_are_not_counted(self, tmp_path, monkeypatch):
        """D1's delimitation: the blank line, `---` and the next anchor are not content."""
        link = self._dossier(tmp_path, "bug-276-x.md", "BUG-276")
        text = _gated("**Promise:** one.", _item("BUG-276", 5, link)) + _section(
            "b", "2. B", "**Promise:** two.", _item("BK-177", 1)
        )
        assert self._run(tmp_path, monkeypatch, text) == 0

    def test_six_diagnosis_lines_fail_even_within_eight(self, tmp_path, monkeypatch, capsys):
        """Without a Detail: line the item fits eight, but the diagnosis cap is five."""
        assert self._run(tmp_path, monkeypatch, _gated("**Promise:** one.", _item("BUG-273", 6))) == 1
        out = capsys.readouterr().out
        assert "BUG-273: diagnosis 6 lines (cap 5)" in out
        assert "content lines (cap 8)" not in out

    def test_the_retired_migration_marker_exempts_nothing(self, tmp_path, monkeypatch, capsys):
        """ADR-0041: with every section converted, the opt-out is gone, so a re-added marker gates."""
        text = _RULES + _BLOCKERS + _section("a", "1. A", "**Promise:** one.", _item("BUG-276", 40), marker=True)
        assert self._run(tmp_path, monkeypatch, text) == 1
        assert "BUG-276: 42 content lines (cap 8)" in capsys.readouterr().out

    # -- R3 -----------------------------------------------------------------

    def test_a_closes_when_paragraph_fails_a_section(self, tmp_path, monkeypatch, capsys):
        text = _gated("**Promise:** one.\n\n**Closes when:** x.", _item("BK-177", 1))
        assert self._run(tmp_path, monkeypatch, text) == 1
        assert "1. A: preamble has 2 paragraphs" in capsys.readouterr().out

    def test_a_promise_of_four_sentences_fails_and_three_pass(self, tmp_path, monkeypatch, capsys):
        three = "**Promise:** one thing. Another `thing`. A third (thing), e.g. this."
        assert self._run(tmp_path, monkeypatch, _gated(three, _item("BK-177", 1))) == 0
        assert self._run(tmp_path, monkeypatch, _gated(three + " Fourth.", _item("BK-177", 1))) == 1
        assert "1. A: Promise has 4 sentences (cap 3)" in capsys.readouterr().out

    def test_stated_bound_a_lowercase_or_digit_opener_is_not_counted(self, tmp_path, monkeypatch):
        """R3's fail-open direction, pinned so the docstring cannot over-claim.

        Four sentences, three of them opening with a lowercase identifier or a
        digit, count as one. Widening the splitter to catch them deletes this test.
        """
        four = "**Promise:** one. s3fs lanes truncate. paramiko leaks. 404s propagate."
        assert self._run(tmp_path, monkeypatch, _gated(four, _item("BK-177", 1))) == 0

    def test_a_preamble_that_is_not_a_promise_fails(self, tmp_path, monkeypatch, capsys):
        assert self._run(tmp_path, monkeypatch, _gated("Some notes.", _item("BK-177", 1))) == 1
        assert "1. A: preamble does not open with **Promise:**" in capsys.readouterr().out

    def test_release_blockers_empty_with_no_anchor_passes(self, tmp_path, monkeypatch):
        """The standing section: empty is its normal state and it needs no exemption."""
        assert self._run(tmp_path, monkeypatch, _RULES + _BLOCKERS) == 0

    def test_the_retired_migration_marker_does_not_spare_a_long_preamble(self, tmp_path, monkeypatch, capsys):
        """The marker is now preamble text: it adds a paragraph and displaces the Promise."""
        long = "**Promise:** a. B. C. D.\n\n**Closes when:** e.\n\nNotes."
        text = _RULES + _BLOCKERS + _section("a", "1. A", long, _item("BK-177", 1), marker=True)
        assert self._run(tmp_path, monkeypatch, text) == 1
        out = capsys.readouterr().out
        assert "1. A: preamble has 4 paragraphs" in out
        assert "1. A: preamble does not open with **Promise:**" in out

    # -- R4 -----------------------------------------------------------------

    def test_a_detail_link_that_does_not_resolve_fails(self, tmp_path, monkeypatch, capsys):
        text = _gated("**Promise:** one.", _item("BUG-276", 1, "backlog/bug-276-x.md"))
        assert self._run(tmp_path, monkeypatch, text) == 1
        assert "BUG-276: Detail: backlog/bug-276-x.md does not resolve" in capsys.readouterr().out

    def test_a_dossier_whose_header_names_another_id_fails(self, tmp_path, monkeypatch, capsys):
        link = self._dossier(tmp_path, "bug-276-x.md", "BUG-273")
        assert self._run(tmp_path, monkeypatch, _gated("**Promise:** one.", _item("BUG-276", 1, link))) == 1
        assert "BUG-276: dossier backlog/bug-276-x.md is headed BUG-273" in capsys.readouterr().out

    def test_a_dossier_path_not_named_for_its_item_fails(self, tmp_path, monkeypatch, capsys):
        """D2's path is `<id>-<slug>.md`; the ID in the path is what a reader greps for."""
        link = self._dossier(tmp_path, "bug-999-x.md", "BUG-276")
        assert self._run(tmp_path, monkeypatch, _gated("**Promise:** one.", _item("BUG-276", 1, link))) == 1
        assert "BUG-276: dossier path backlog/bug-999-x.md is not named bug-276-<slug>.md" in capsys.readouterr().out

    def test_a_malformed_detail_line_fails(self, tmp_path, monkeypatch, capsys):
        item = f"- [ ] **BUG-276 {_EM} Title**\n{_ATTR}\n  Diagnosis.\n  Detail: see the dossier\n"
        assert self._run(tmp_path, monkeypatch, _gated("**Promise:** one.", item)) == 1
        assert "BUG-276: Detail: line is not `Detail: [dossier](backlog/<id>-<slug>.md)`" in capsys.readouterr().out

    def test_shape_rules_do_not_short_circuit_r1(self, tmp_path, monkeypatch, capsys):
        bad_attr = f"- [ ] **BK-177 {_EM} T**\n  spec: — · effort: XS · audience: infra.ci\n"
        assert self._run(tmp_path, monkeypatch, _gated("Notes.", bad_attr + _item("BUG-276", 9))) == 1
        out = capsys.readouterr().out
        assert "effort 'XS'" in out
        assert "BUG-276: 11 content lines (cap 8)" in out
        assert "preamble does not open with **Promise:**" in out
