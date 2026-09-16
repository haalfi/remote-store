"""Tests for scripts/drift_report.py (ID-182).

The script composes the rolling issue from whatever a run uploaded and then
reconciles the issue through ``gh``. Everything worth testing is on the first
half: which JSON shape a file is, which sections it lands in, whether it holds
the issue open, and — the one that would be silent if wrong — that a dry run
reaches no GitHub API at all.

The ``gh`` half is not unit-tested beyond that: it is three subprocess calls,
and the workflow's own run is their acceptance test.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPTS = ROOT / "scripts"


@pytest.fixture(scope="module")
def drift_report():
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    import drift_report

    return drift_report


def _write(dir_: Path, name: str, payload: dict) -> None:
    dir_.mkdir(parents=True, exist_ok=True)
    (dir_ / name).write_text(json.dumps(payload), encoding="utf-8")


def _diff(extra: str, status: str = "ok", **kw) -> dict:
    return {
        "extra": extra,
        "status": status,
        "python_baseline": "3.13",
        "python_run": "3.13",
        "captured": "2026-09-07",
        "stable_drift": [],
        "prerelease_drift": [],
        **kw,
    }


def _floor(extra: str, status: str = "resolved", **kw) -> dict:
    return {"extra": extra, "lane": "floor", "status": status, "python_run": "3.10", **kw}


def _smoke(extra: str, lane: str, smoke: str, **kw) -> dict:
    return {"extra": extra, "lane": lane, "smoke": smoke, **kw}


class TestLoadReportsShapeSplit:
    """All three shapes carry ``"extra"``, and a run uploads several per extra.

    Keying one flat dict on that field would keep whichever file sorted last
    and drop the other two — silently, and differently per extra depending on
    filename order. The discriminators are the fields themselves.
    """

    def test_splits_the_three_shapes(self, drift_report, tmp_path):
        _write(tmp_path, "a.json", _diff("s3"))
        _write(tmp_path, "b.json", _floor("s3"))
        _write(tmp_path, "c.json", _smoke("s3", "newest", "pass"))
        reports = drift_report._load_reports(tmp_path)
        assert set(reports.diffs) == {"s3"}
        assert set(reports.floors) == {"s3"}
        assert set(reports.smokes) == {("s3", "newest")}

    def test_keeps_both_lanes_for_one_extra(self, drift_report, tmp_path):
        _write(tmp_path, "n.json", _smoke("s3", "newest", "pass"))
        _write(tmp_path, "f.json", _smoke("s3", "floor", "fail", phase="smoke"))
        reports = drift_report._load_reports(tmp_path)
        assert reports.smokes[("s3", "newest")]["smoke"] == "pass"
        assert reports.smokes[("s3", "floor")]["smoke"] == "fail"

    def test_reads_nested_artifact_layouts(self, drift_report, tmp_path):
        # upload-artifact keeps the workspace-relative directory prefix inside
        # the artifact, so a merged download is one level deeper than flat.
        _write(tmp_path / "drift-reports", "s3.json", _diff("s3"))
        _write(tmp_path / "drift-floors", "s3.json", _floor("s3"))
        reports = drift_report._load_reports(tmp_path)
        assert set(reports.diffs) == {"s3"}
        assert set(reports.floors) == {"s3"}

    def test_empty_dir_is_falsy(self, drift_report, tmp_path):
        assert not drift_report._load_reports(tmp_path)

    def test_an_unreadable_file_is_named_and_skipped(self, drift_report, tmp_path):
        # Measured on a real run: two single-file artefacts landed on one
        # filename under `merge-multiple` and the concatenation aborted the
        # whole report, losing every other extra's rows for a reason that had
        # nothing to do with them.
        _write(tmp_path, "good.json", _diff("s3"))
        (tmp_path / "bad.json").write_text('{"extra": "yaml"}{"extra": "yaml"}', encoding="utf-8")
        reports = drift_report._load_reports(tmp_path)
        assert set(reports.diffs) == {"s3"}
        assert reports.unreadable == ["bad.json"]

    def test_a_json_file_with_no_extra_key_is_skipped(self, drift_report, tmp_path):
        (tmp_path / "stray.json").write_text('{"hello": "world"}', encoding="utf-8")
        assert drift_report._load_reports(tmp_path).unreadable == ["stray.json"]

    def test_an_unreadable_file_alone_is_still_truthy(self, drift_report, tmp_path):
        # Otherwise `main` reports "nothing to reconcile" and exits 0 on a run
        # whose every upload was corrupt.
        (tmp_path / "bad.json").write_text("not json", encoding="utf-8")
        assert drift_report._load_reports(tmp_path)


class TestHasSignal:
    """What holds the rolling issue open. A red smoke counts even on a clean
    resolution — that is the isolated-install finding, and before this it
    reached only a red run, which the durable-TODO principle says is not a
    channel to rely on.
    """

    def _reports(self, drift_report, tmp_path, *payloads):
        for i, payload in enumerate(payloads):
            _write(tmp_path, f"{i}.json", payload)
        return drift_report._load_reports(tmp_path)

    def test_all_clear_is_no_signal(self, drift_report, tmp_path):
        reports = self._reports(
            drift_report,
            tmp_path,
            _diff("s3"),
            _floor("s3"),
            _smoke("s3", "newest", "pass"),
            _smoke("s3", "floor", "pass"),
        )
        assert drift_report.has_signal(reports, {}) is False

    @pytest.mark.parametrize("status", ["drift", "needs_refresh", "error"])
    def test_diff_status_signals(self, drift_report, tmp_path, status):
        assert drift_report.has_signal(self._reports(drift_report, tmp_path, _diff("s3", status)), {}) is True

    def test_floor_resolve_error_signals(self, drift_report, tmp_path):
        reports = self._reports(drift_report, tmp_path, _diff("s3"), _floor("s3", "error", reason="no wheel"))
        assert drift_report.has_signal(reports, {}) is True

    def test_newest_lane_smoke_failure_signals(self, drift_report, tmp_path):
        # A clean resolution whose isolated install then fails is precisely the
        # finding the early return used to make unreachable.
        reports = self._reports(
            drift_report, tmp_path, _diff("s3"), _smoke("s3", "newest", "fail", phase="import-extra")
        )
        assert drift_report.has_signal(reports, {}) is True

    def test_floor_smoke_failure_signals(self, drift_report, tmp_path):
        reports = self._reports(drift_report, tmp_path, _diff("s3"), _smoke("s3", "floor", "fail", phase="smoke"))
        assert drift_report.has_signal(reports, {}) is True

    def test_registered_floor_finding_does_not_signal(self, drift_report, tmp_path):
        # Its owner and rationale are committed. Holding the issue open for it
        # would make every week's issue identical, which is how a reader learns
        # to skip it.
        reports = self._reports(
            drift_report, tmp_path, _diff("s3"), _floor("s3", "error"), _smoke("s3", "floor", "fail", phase="smoke")
        )
        assert drift_report.has_signal(reports, {("s3", "floor"): ("BUG-287", "2026-12-31")}) is False

    def test_registering_a_floor_does_not_silence_its_newest_lane(self, drift_report, tmp_path):
        # The register is about a known-bad *floor*. It must not also suppress
        # the newest lane for that extra, which is a different claim entirely.
        reports = self._reports(drift_report, tmp_path, _diff("s3"), _smoke("s3", "newest", "fail", phase="smoke"))
        assert drift_report.has_signal(reports, {("s3", "floor"): ("BUG-287", "2026-12-31")}) is True

    def test_registered_newest_finding_does_not_signal(self, drift_report, tmp_path):
        # The same argument as the floor case: a finding whose owner and
        # rationale are committed is not news. Its leg still goes red — the
        # register changes what the issue presents, never what CI does.
        reports = self._reports(drift_report, tmp_path, _diff("sql"), _smoke("sql", "newest", "fail", phase="smoke"))
        assert drift_report.has_signal(reports, {("sql", "newest"): ("BUG-281", "2026-12-31")}) is False

    def test_registering_a_finding_never_suppresses_version_drift(self, drift_report, tmp_path):
        # A row registers a verdict somebody owns, not the movement of a
        # package. Drift is what the newest lane exists to report, so it must
        # survive any registration.
        reports = self._reports(
            drift_report, tmp_path, _diff("sql", "drift"), _smoke("sql", "newest", "fail", phase="smoke")
        )
        assert drift_report.has_signal(reports, {("sql", "newest"): ("BUG-281", "2026-12-31")}) is True

    def test_an_unreadable_report_signals(self, drift_report, tmp_path):
        # A missing row and a clean row look identical on the issue, so a
        # report that silently lost one must hold the issue open.
        _write(tmp_path, "good.json", _diff("s3"))
        (tmp_path / "bad.json").write_text("not json", encoding="utf-8")
        assert drift_report.has_signal(drift_report._load_reports(tmp_path), {}) is True

    def test_skipped_smoke_is_not_a_failure(self, drift_report, tmp_path):
        reports = self._reports(drift_report, tmp_path, _diff("s3"), _smoke("s3", "floor", "skipped"))
        assert drift_report.has_signal(reports, {}) is False


class TestRenderBody:
    """Which section a finding lands in. The phase split is the whole value:
    the causes take different actions and read identically as a red X.
    """

    def _body(self, drift_report, tmp_path, *payloads, register=None):
        for i, payload in enumerate(payloads):
            _write(tmp_path, f"{i}.json", payload)
        return drift_report._render_body(drift_report._load_reports(tmp_path), "https://run", register or {})

    def test_floor_smoke_failure_is_installs_then_breaks(self, drift_report, tmp_path):
        body = self._body(
            drift_report,
            tmp_path,
            _floor("azure", floor={"aiohttp": "3.0.0"}),
            _smoke("azure", "floor", "fail", phase="smoke"),
        )
        assert "### Floor installs, then breaks" in body
        assert "`aiohttp`" in body

    def test_floor_import_failure_is_also_installs_then_breaks(self, drift_report, tmp_path):
        # It installed and its own declared package will not import. Same
        # finding, one step earlier than the smoke.
        body = self._body(
            drift_report, tmp_path, _floor("azure"), _smoke("azure", "floor", "fail", phase="import-extra")
        )
        assert "### Floor installs, then breaks" in body

    def test_floor_resolve_error_is_does_not_install(self, drift_report, tmp_path):
        body = self._body(drift_report, tmp_path, _floor("azure", "error", reason="no wheel for aiohttp 3.0.0"))
        assert "### Floor does not install" in body
        assert "no wheel for aiohttp 3.0.0" in body

    def test_plugin_conflict_is_a_harness_section(self, drift_report, tmp_path):
        body = self._body(drift_report, tmp_path, _floor("s3"), _smoke("s3", "floor", "fail", phase="install-plugins"))
        assert "### Test plugins cannot coexist with the floor" in body
        assert "harness gap" in body

    def test_registered_finding_names_its_owner(self, drift_report, tmp_path):
        body = self._body(
            drift_report,
            tmp_path,
            _floor("arrow"),
            _smoke("arrow", "floor", "fail", phase="smoke"),
            register={("arrow", "floor"): ("BUG-287", "2026-12-31")},
        )
        assert "_Known: owned by BUG-287, review by 2026-12-31._" in body

    def test_registered_newest_finding_names_its_owner(self, drift_report, tmp_path):
        body = self._body(
            drift_report,
            tmp_path,
            _diff("azure"),
            _smoke("azure", "newest", "fail", phase="import-extra"),
            register={("azure", "newest"): ("BUG-281", "2026-12-31")},
        )
        assert "_Known: owned by BUG-281, review by 2026-12-31._" in body

    def test_newest_lane_import_failure_is_an_isolation_finding(self, drift_report, tmp_path):
        # The extra installed alone and could not stand up — which is invisible
        # in any environment where another extra supplies what it forgot.
        body = self._body(
            drift_report, tmp_path, _diff("azure"), _smoke("azure", "newest", "fail", phase="import-extra")
        )
        assert "## Isolated install failed" in body
        assert "`[azure]`" in body

    def test_smoke_verdict_table_covers_both_lanes(self, drift_report, tmp_path):
        body = self._body(
            drift_report, tmp_path, _smoke("s3", "newest", "pass"), _smoke("s3", "floor", "fail", phase="smoke")
        )
        assert "| Extra | Newest | Floor |" in body
        assert "| `[s3]` | pass | fail (smoke) |" in body

    def test_clear_requires_both_lanes(self, drift_report, tmp_path):
        # An extra whose newest resolution is `ok` while its floor is red is
        # not a clean extra; listing it under Clear is what would let the
        # finding pass unread.
        body = self._body(
            drift_report,
            tmp_path,
            _diff("s3"),
            _diff("yaml"),
            _smoke("s3", "floor", "fail", phase="smoke"),
            _smoke("yaml", "floor", "pass"),
        )
        clear = body.rsplit("## Clear", 1)[-1]
        assert "`[yaml]`" in clear
        assert "`[s3]`" not in clear

    def test_no_floor_section_when_the_lane_is_clean(self, drift_report, tmp_path):
        body = self._body(drift_report, tmp_path, _diff("s3"), _floor("s3"), _smoke("s3", "floor", "pass"))
        assert "## Floor lane" not in body


class TestKnownFindings:
    """The register is what separates a finding somebody owns from a new one."""

    def test_parses_the_committed_register(self, drift_report):
        register = drift_report.load_known_findings()
        assert register, "the committed register should parse"
        for owner, review in register.values():
            assert owner
            assert review

    def test_every_registered_row_names_a_tracked_extra_and_a_real_lane(self, drift_report):
        # A row for an extra the guard does not track, or a lane that does not
        # exist, would silence nothing and go unnoticed: no leg ever produces a
        # verdict it could match.
        sys.path.insert(0, str(SCRIPTS))
        from drift_check import list_extras

        tracked = set(list_extras())
        for extra, lane in drift_report.load_known_findings():
            assert extra in tracked, f"{extra} is not a tracked extra"
            assert lane in ("newest", "floor"), f"{lane} is not a lane"

    def test_missing_register_is_not_an_error(self, drift_report, tmp_path):
        assert drift_report.load_known_findings(tmp_path / "absent.md") == {}

    def test_ignores_the_header_row(self, drift_report, tmp_path):
        path = tmp_path / "register.md"
        path.write_text(
            "| Extra | Lane | Owner | Rationale | Review by |\n"
            "|---|---|---|---|---|\n"
            "| `[s3]` | floor | BUG-1 | why | 2026-12-31 |\n",
            encoding="utf-8",
        )
        assert drift_report.load_known_findings(path) == {("s3", "floor"): ("BUG-1", "2026-12-31")}

    def test_keys_the_two_lanes_apart(self, drift_report, tmp_path):
        # The lanes make different claims about the same extra, so a row for one
        # must not answer for the other.
        path = tmp_path / "register.md"
        path.write_text(
            "| `[s3]` | floor | BUG-1 | why | 2026-12-31 |\n| `[s3]` | newest | BUG-2 | why | 2027-01-31 |\n",
            encoding="utf-8",
        )
        register = drift_report.load_known_findings(path)
        assert register[("s3", "floor")][0] == "BUG-1"
        assert register[("s3", "newest")][0] == "BUG-2"


class TestDryRun:
    """A dispatch from a branch must be observable without writing to the issue
    the scheduled runs own — including without *reading* it, since the read is
    an authenticated call a branch run may not be able to make.
    """

    def test_dry_run_makes_no_gh_call(self, drift_report, tmp_path, monkeypatch, capsys):
        _write(
            tmp_path,
            "s3.json",
            _diff("s3", "drift", stable_drift=[{"package": "s3fs", "baseline": "1", "resolved": "2"}]),
        )

        def _explode(*args, **kwargs):
            raise AssertionError("a dry run reached the GitHub API")

        monkeypatch.setattr(drift_report, "_gh", _explode)
        rc = drift_report.main(
            [str(tmp_path), "--repo", "haalfi/remote-store", "--run-url", "https://run", "--title", "t", "--dry-run"]
        )
        assert rc == 0
        assert "## Drift detected" in capsys.readouterr().out

    def test_dry_run_prints_the_body_it_would_write(self, drift_report, tmp_path, monkeypatch, capsys):
        _write(tmp_path, "s3.json", _diff("s3"))
        monkeypatch.setattr(drift_report, "_gh", lambda *a, **k: None)
        drift_report.main(
            [str(tmp_path), "--repo", "haalfi/remote-store", "--run-url", "https://run", "--title", "t", "--dry-run"]
        )
        out = capsys.readouterr()
        assert "## Clear" in out.out
        assert "dry run" in out.err

    def test_empty_report_dir_is_a_no_op(self, drift_report, tmp_path, monkeypatch):
        monkeypatch.setattr(drift_report, "_gh", lambda *a, **k: (_ for _ in ()).throw(AssertionError("called gh")))
        assert drift_report.main([str(tmp_path), "--repo", "r", "--run-url", "u", "--title", "t"]) == 0
