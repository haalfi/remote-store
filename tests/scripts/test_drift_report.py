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

import dataclasses
import json
import sys
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPTS = ROOT / "scripts"

# Every time-dependent entry point in `drift_report` takes a `today`. Four of
# them DEFAULT it to `date.today()`, and those are the ones a test can get wrong
# by omission — the rest require it, so the mistake is impossible there.
# `test_no_call_in_this_module_lets_today_default` below refuses an omission at
# the four that default, because
# measured: seven tests in this file went red on a shifted clock -- one from
# 2026-10-05, when 3.10's window closes with the committed register empty, and
# six more from 2027-01-01, when every `KNOWN-FINDINGS.md` row's `Review by`
# expires at once. This day is chosen so both are false: nothing is past its
# window and every register row is live, which is the state the assertions were
# written against.
TODAY = date(2026, 9, 17)


@pytest.fixture(scope="module")
def drift_report():
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    import drift_report

    return drift_report


@pytest.fixture(scope="module")
def python_support():
    """The sibling module `drift_report` reads its interpreter dates from.

    Same module object `drift_report` imported, so a `monkeypatch.delitem` on
    `PYTHON_RELEASES` here is what `windows()` sees.
    """
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    import python_support

    return python_support


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
        assert drift_report.has_signal(reports, {}, today=TODAY) is False

    @pytest.mark.parametrize("status", ["drift", "needs_refresh", "error"])
    def test_diff_status_signals(self, drift_report, tmp_path, status):
        assert (
            drift_report.has_signal(self._reports(drift_report, tmp_path, _diff("s3", status)), {}, today=TODAY) is True
        )

    def test_floor_resolve_error_signals(self, drift_report, tmp_path):
        reports = self._reports(drift_report, tmp_path, _diff("s3"), _floor("s3", "error", reason="no wheel"))
        assert drift_report.has_signal(reports, {}, today=TODAY) is True

    def test_newest_lane_smoke_failure_signals(self, drift_report, tmp_path):
        # A clean resolution whose isolated install then fails is precisely the
        # finding the early return used to make unreachable.
        reports = self._reports(
            drift_report, tmp_path, _diff("s3"), _smoke("s3", "newest", "fail", phase="import-extra")
        )
        assert drift_report.has_signal(reports, {}, today=TODAY) is True

    def test_floor_smoke_failure_signals(self, drift_report, tmp_path):
        reports = self._reports(drift_report, tmp_path, _diff("s3"), _smoke("s3", "floor", "fail", phase="smoke"))
        assert drift_report.has_signal(reports, {}, today=TODAY) is True

    def test_registered_floor_finding_does_not_signal(self, drift_report, tmp_path):
        # Its owner and rationale are committed. Holding the issue open for it
        # would make every week's issue identical, which is how a reader learns
        # to skip it.
        reports = self._reports(
            drift_report,
            tmp_path,
            _diff("s3"),
            _smoke("s3", "newest", "pass"),
            _floor("s3", "error"),
            _smoke("s3", "floor", "fail", phase="smoke"),
        )
        assert drift_report.has_signal(reports, {("s3", "floor"): ("BUG-287", "2026-12-31")}, today=TODAY) is False

    def test_registering_a_floor_does_not_silence_its_newest_lane(self, drift_report, tmp_path):
        # The register is about a known-bad *floor*. It must not also suppress
        # the newest lane for that extra, which is a different claim entirely.
        reports = self._reports(drift_report, tmp_path, _diff("s3"), _smoke("s3", "newest", "fail", phase="smoke"))
        assert drift_report.has_signal(reports, {("s3", "floor"): ("BUG-287", "2026-12-31")}, today=TODAY) is True

    def test_registered_newest_finding_does_not_signal(self, drift_report, tmp_path):
        # The same argument as the floor case: a finding whose owner and
        # rationale are committed is not news. Its leg still goes red — the
        # register changes what the issue presents, never what CI does.
        reports = self._reports(drift_report, tmp_path, _diff("sql"), _smoke("sql", "newest", "fail", phase="smoke"))
        assert drift_report.has_signal(reports, {("sql", "newest"): ("BUG-281", "2026-12-31")}, today=TODAY) is False

    def test_registering_a_finding_never_suppresses_version_drift(self, drift_report, tmp_path):
        # A row registers a verdict somebody owns, not the movement of a
        # package. Drift is what the newest lane exists to report, so it must
        # survive any registration.
        reports = self._reports(
            drift_report, tmp_path, _diff("sql", "drift"), _smoke("sql", "newest", "fail", phase="smoke")
        )
        assert drift_report.has_signal(reports, {("sql", "newest"): ("BUG-281", "2026-12-31")}, today=TODAY) is True

    def test_an_unreadable_report_signals(self, drift_report, tmp_path):
        # A missing row and a clean row look identical on the issue, so a
        # report that silently lost one must hold the issue open.
        _write(tmp_path, "good.json", _diff("s3"))
        (tmp_path / "bad.json").write_text("not json", encoding="utf-8")
        assert drift_report.has_signal(drift_report._load_reports(tmp_path), {}, today=TODAY) is True

    def test_skipped_smoke_is_not_a_failure(self, drift_report, tmp_path):
        # `skipped` means no resolution existed to pin against — reported, not
        # lost. The floor report it belongs to is `error`, which signals on its
        # own; here the question is only whether `skipped` adds one.
        reports = self._reports(
            drift_report,
            tmp_path,
            _diff("s3"),
            _smoke("s3", "newest", "pass"),
            _floor("s3"),
            _smoke("s3", "floor", "skipped"),
        )
        assert drift_report.has_signal(reports, {}, today=TODAY) is False


class TestRenderBody:
    """Which section a finding lands in. The phase split is the whole value:
    the causes take different actions and read identically as a red X.
    """

    def _body(self, drift_report, tmp_path, *payloads, register=None):
        for i, payload in enumerate(payloads):
            _write(tmp_path, f"{i}.json", payload)
        return drift_report._render_body(
            drift_report._load_reports(tmp_path), "https://run", register or {}, today=TODAY
        )

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

    def test_a_registered_newest_smoke_failure_names_its_owner(self, drift_report, tmp_path):
        # The phase the prose sections cannot reach. `_render_isolation_findings`
        # takes the newest lane's install and import phases and `_render_floor_lane`
        # takes the floor, so a registered newest-lane *smoke* failure — the one
        # row the committed register actually carries, `[sql]`/BUG-281 — reached
        # neither and rendered as a bare `fail (smoke)` with no owner, while
        # three artifacts said a registered finding renders with one.
        body = self._body(
            drift_report,
            tmp_path,
            _diff("sql", "drift"),
            _smoke("sql", "newest", "fail", phase="smoke"),
            register={("sql", "newest"): ("BUG-281", "2026-12-31")},
        )
        assert "| `[sql]` | fail (smoke) — known, BUG-281 | — |" in body

    def test_an_unregistered_smoke_failure_is_not_marked_known(self, drift_report, tmp_path):
        # The other direction, and the one that matters: a new finding must not
        # inherit the marker that tells a reader somebody already owns it.
        body = self._body(
            drift_report,
            tmp_path,
            _diff("sql", "drift"),
            _smoke("sql", "newest", "fail", phase="smoke"),
            register={},
        )
        assert "| `[sql]` | fail (smoke) | — |" in body

    def test_a_report_without_status_is_named_not_silently_dropped(self, drift_report, tmp_path):
        # Three behaviours, and the middle one is what the first version of this
        # test missed. It must not abort the body (it raised `KeyError: 'status'`
        # one function after the load was hardened against that class); it must
        # NAME the report it could not place; and naming it is what keeps the
        # run out of the silent-close path. Asserting only that `[yaml]` still
        # rendered passed on a version that dropped `[broken]` without a word
        # and closed the issue.
        body = self._body(
            drift_report,
            tmp_path,
            _diff("yaml"),
            _smoke("yaml", "newest", "pass"),
            {"extra": "broken"},
        )
        assert "`[yaml]`" in body
        assert "## Unreadable reports" in body

    def test_a_partial_drift_entry_costs_only_its_own_row(self, drift_report, tmp_path):
        # Same class one level down: an entry inside `stable_drift` missing
        # `package` raised out of `_render_body`, exited 1, and took every other
        # extra's rows with it.
        body = self._body(
            drift_report,
            tmp_path,
            _diff("sql", "drift", stable_drift=[{"baseline": "1.0", "resolved": "2.0"}]),
            _smoke("sql", "newest", "pass"),
        )
        assert "## Drift detected" in body
        assert "| `?` | `1.0` | `2.0` |" in body

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
            _floor("s3"),
            _floor("yaml"),
            _smoke("s3", "newest", "pass"),
            _smoke("yaml", "newest", "pass"),
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


class TestIncompleteLegs:
    """Every leg writes a report and a verdict. A missing half means a leg died
    before uploading, or two uploads landed on one basename — which happened
    twice while this lane was being built, and whose signature is a row that is
    quietly absent rather than wrong.
    """

    def _reports(self, drift_report, tmp_path, *payloads):
        for i, payload in enumerate(payloads):
            _write(tmp_path, f"{i}.json", payload)
        return drift_report._load_reports(tmp_path)

    def test_a_complete_pair_is_not_flagged(self, drift_report, tmp_path):
        reports = self._reports(drift_report, tmp_path, _diff("s3"), _smoke("s3", "newest", "pass"))
        assert drift_report._incomplete_legs(reports) == []

    def test_a_report_with_no_verdict_is_flagged(self, drift_report, tmp_path):
        reports = self._reports(drift_report, tmp_path, _floor("s3"))
        assert any("floor report with no smoke verdict" in e for e in drift_report._incomplete_legs(reports))

    def test_a_verdict_with_no_report_is_flagged(self, drift_report, tmp_path):
        reports = self._reports(drift_report, tmp_path, _smoke("s3", "floor", "pass"))
        assert any("smoke verdict with no report" in e for e in drift_report._incomplete_legs(reports))

    def test_a_skipped_verdict_still_counts_as_present(self, drift_report, tmp_path):
        # `skipped` is a verdict. Treating it as absent would flag every leg
        # whose resolve failed, which is a reported state rather than a lost one.
        reports = self._reports(drift_report, tmp_path, _floor("s3", "error"), _smoke("s3", "floor", "skipped"))
        assert drift_report._incomplete_legs(reports) == []

    def test_an_extra_that_reported_nothing_is_flagged(self, drift_report, tmp_path):
        # The case the two halves cannot see between them: a leg that died
        # before uploading anything contributes no key on either side, so
        # comparing the sides finds it complete. Measured on the committed
        # script before the fix: the body said "Both lanes clean" and the run
        # closed the issue with the unchecked extra absent entirely.
        reports = self._reports(drift_report, tmp_path, _diff("s3"), _smoke("s3", "newest", "pass"))
        flagged = drift_report._incomplete_legs(reports, ["s3", "azure"], ["newest"])
        assert any("`[azure]` newest: reported nothing at all" in entry for entry in flagged)
        assert not any("`[s3]`" in entry for entry in flagged)

    def test_an_extra_that_lost_one_lane_is_flagged(self, drift_report, tmp_path):
        # The narrower shape, and the one that survived the fix above: `[sql]`
        # reports fully on the newest lane and loses its whole floor leg. Keyed
        # on the extra alone it stays in `covered`, contributes no row, and the
        # body then names it under `Clear`. Measured on the committed script
        # before this fix: "Both lanes clean: `[arrow]`, `[sql]`, `[yaml]`",
        # and the dry run would have closed the issue.
        reports = self._reports(
            drift_report,
            tmp_path,
            _diff("sql"),
            _smoke("sql", "newest", "pass"),
            _diff("yaml"),
            _smoke("yaml", "newest", "pass"),
            _floor("yaml"),
            _smoke("yaml", "floor", "pass"),
        )
        flagged = drift_report._incomplete_legs(reports, ["sql", "yaml"])
        assert any("`[sql]` floor: reported nothing at all" in entry for entry in flagged)
        assert not any("`[yaml]`" in entry for entry in flagged)
        assert drift_report.has_signal(reports, {}, ["sql", "yaml"], today=TODAY) is True

    def test_an_extra_that_lost_one_lane_is_not_called_clear(self, drift_report, tmp_path):
        # The half of the same defect a reader actually sees. An incomplete leg
        # has to cost its extra the `Clear` line as well as earning a row:
        # naming it clean is the sentence that gets believed.
        reports = self._reports(
            drift_report,
            tmp_path,
            _diff("sql"),
            _smoke("sql", "newest", "pass"),
        )
        body = drift_report._render_body(reports, "https://run", {}, ["sql"], today=TODAY)
        assert "## Incomplete legs" in body
        # `[sql]`'s newest diff is `ok`, so it would have been the whole Clear
        # list; excluding it leaves no section at all.
        assert "## Clear" not in body

    def test_a_single_lane_dispatch_does_not_report_the_other_lane_as_lost(self, drift_report, tmp_path):
        # `lane: newest` must not emit fourteen false floor rows. The lane half
        # of the claim space comes from the dispatch, exactly as the extra half does.
        reports = self._reports(drift_report, tmp_path, _diff("s3"), _smoke("s3", "newest", "pass"))
        assert drift_report._incomplete_legs(reports, ["s3"], ["newest"]) == []
        assert any("floor" in e for e in drift_report._incomplete_legs(reports, ["s3"]))

    def test_a_narrowed_dispatch_does_not_report_the_rest_as_lost(self, drift_report, tmp_path):
        # `extra: s3` must not emit thirteen false rows. The expected set is the
        # dispatched slice, not the whole table.
        reports = self._reports(
            drift_report,
            tmp_path,
            _diff("s3"),
            _smoke("s3", "newest", "pass"),
            _floor("s3"),
            _smoke("s3", "floor", "pass"),
        )
        assert drift_report._incomplete_legs(reports, ["s3"]) == []

    def test_no_expected_set_falls_back_to_comparing_halves(self, drift_report, tmp_path):
        # Called without the slice (an operator running it by hand), the
        # half-against-half check still applies and nothing is invented.
        reports = self._reports(drift_report, tmp_path, _diff("s3"), _smoke("s3", "newest", "pass"))
        assert drift_report._incomplete_legs(reports) == []

    def test_an_incomplete_leg_signals_and_renders(self, drift_report, tmp_path):
        reports = self._reports(drift_report, tmp_path, _diff("s3"))
        assert drift_report.has_signal(reports, {}, today=TODAY) is True
        assert "## Incomplete legs" in drift_report._render_body(reports, "https://run", {}, today=TODAY)


class TestDecide:
    """The one function both the dry run and the real run consult.

    They derived their verdict separately until the closing gate measured them
    disagreeing: on an all-clean single-lane dispatch the preview said "would
    close" and the run it previewed left the issue alone.
    """

    def _reports(self, drift_report, tmp_path, *payloads):
        for i, payload in enumerate(payloads):
            _write(tmp_path, f"{i}.json", payload)
        return drift_report._load_reports(tmp_path)

    def test_both_lanes_clean_closes(self, drift_report, tmp_path):
        reports = self._reports(
            drift_report,
            tmp_path,
            _diff("s3"),
            _smoke("s3", "newest", "pass"),
            _floor("s3"),
            _smoke("s3", "floor", "pass"),
        )
        assert drift_report.decide(reports, {}, ["s3"], today=TODAY)[0] == "close"

    def test_one_lane_clean_leaves_the_issue_alone(self, drift_report, tmp_path):
        # The case the dry run used to preview as a close.
        reports = self._reports(drift_report, tmp_path, _diff("s3"), _smoke("s3", "newest", "pass"))
        action, reason = drift_report.decide(reports, {}, ["s3"], ["newest"], today=TODAY)
        assert action == "leave"
        assert "did not cover both lanes" in reason

    def test_a_finding_updates(self, drift_report, tmp_path):
        reports = self._reports(drift_report, tmp_path, _diff("s3", "drift"), _smoke("s3", "newest", "pass"))
        assert drift_report.decide(reports, {}, ["s3"], today=TODAY)[0] == "update"


class TestExpectLanesCli:
    """`--expect-lanes` reaches `_parse_expected` through argparse, in the exact
    spelling the workflow's `setup` job emits.

    The lane half of the claim space is joined to the workflow by a string
    literal (`lanes="newest,floor"`), and nothing under `tests/` reached it.
    """

    def _run(self, drift_report, tmp_path, monkeypatch, capsys, *args, payloads=()):
        for i, payload in enumerate(payloads):
            _write(tmp_path, f"{i}.json", payload)
        calls = []
        monkeypatch.setattr(drift_report, "_gh", lambda *a, **k: calls.append(a))
        rc = drift_report.main(
            [
                str(tmp_path),
                "--repo",
                "haalfi/remote-store",
                "--run-url",
                "https://run",
                "--title",
                "t",
                *args,
                "--today",
                str(TODAY),
            ]
        )
        return rc, capsys.readouterr(), calls

    def test_the_workflow_spelling_parses(self, drift_report):
        # `setup` emits exactly this for a `lane: all` run.
        assert drift_report._parse_expected("newest,floor") == ["newest", "floor"]
        assert drift_report._parse_expected("floor") == ["floor"]
        assert drift_report._parse_expected("") == []

    def test_an_absent_flag_falls_back_to_both_lanes(self, drift_report, tmp_path, monkeypatch, capsys):
        # An operator running it by hand must not have every floor leg reported
        # as lost, nor have the fallback quietly narrow to one lane.
        rc, out, _ = self._run(
            drift_report,
            tmp_path,
            monkeypatch,
            capsys,
            "--dry-run",
            payloads=(_diff("s3"), _smoke("s3", "newest", "pass"), _floor("s3"), _smoke("s3", "floor", "pass")),
        )
        assert rc == 0
        assert "Incomplete legs" not in out.out

    def test_a_narrowed_lane_reaches_the_decision(self, drift_report, tmp_path, monkeypatch, capsys):
        # End to end through argparse: the preview must say `leave`, matching
        # what the real path does, and must not report the floor lane as lost.
        rc, out, calls = self._run(
            drift_report,
            tmp_path,
            monkeypatch,
            capsys,
            "--dry-run",
            "--expect-extras",
            "s3",
            "--expect-lanes",
            "newest",
            payloads=(_diff("s3"), _smoke("s3", "newest", "pass")),
        )
        assert rc == 0
        assert calls == []
        assert "Incomplete legs" not in out.out
        assert "would leave alone" in out.err
        assert "newest lane only" in out.out

    def test_the_real_path_refuses_to_close_on_one_lane(self, drift_report, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(drift_report, "_find_open_issue", lambda *a, **k: 42)
        rc, out, calls = self._run(
            drift_report,
            tmp_path,
            monkeypatch,
            capsys,
            "--expect-extras",
            "s3",
            "--expect-lanes",
            "newest",
            payloads=(_diff("s3"), _smoke("s3", "newest", "pass")),
        )
        assert rc == 0
        assert calls == []
        assert "leaving the issue alone" in out.err


class TestSingleLaneRuns:
    """A dispatch can select one lane, and the report must not speak for the
    other. The body is recoverable if it is wrong; a closed issue is not.
    """

    def _reports(self, drift_report, tmp_path, *payloads):
        for i, payload in enumerate(payloads):
            _write(tmp_path, f"{i}.json", payload)
        return drift_report._load_reports(tmp_path)

    def test_clear_names_the_lane_when_only_one_ran(self, drift_report, tmp_path):
        reports = self._reports(drift_report, tmp_path, _diff("s3"), _smoke("s3", "newest", "pass"))
        body = drift_report._render_body(reports, "https://run", {}, today=TODAY)
        assert "newest lane only" in body
        assert "Both lanes clean" not in body

    def test_clear_says_both_when_both_ran(self, drift_report, tmp_path):
        reports = self._reports(
            drift_report,
            tmp_path,
            _diff("s3"),
            _floor("s3"),
            _smoke("s3", "newest", "pass"),
            _smoke("s3", "floor", "pass"),
        )
        assert "Both lanes clean" in drift_report._render_body(reports, "https://run", {}, today=TODAY)

    def test_a_both_lane_clear_run_does_close_the_issue(self, drift_report, tmp_path, monkeypatch):
        # The positive half. Measured: with the refusal hard-coded to `if True`
        # the whole file still passed, so the guard was pinned only in the
        # direction that refuses. Auto-close is contract, not incidental — the
        # body footer states it, `CI-OPERATIONS.md` restates it, and `/drift`
        # step 1 reads "no open issue" as "drift has cleared".
        for name, payload in (
            ("d.json", _diff("s3")),
            ("f.json", _floor("s3")),
            ("n.json", _smoke("s3", "newest", "pass")),
            ("fs.json", _smoke("s3", "floor", "pass")),
        ):
            _write(tmp_path, name, payload)
        calls = []
        monkeypatch.setattr(drift_report, "_gh", lambda *a, **k: calls.append(a[:2]))
        monkeypatch.setattr(drift_report, "_find_open_issue", lambda *a, **k: 42)
        assert (
            drift_report.main(
                [
                    str(tmp_path),
                    "--repo",
                    "haalfi/remote-store",
                    "--run-url",
                    "https://run",
                    "--title",
                    "t",
                    "--today",
                    str(TODAY),
                ]
            )
            == 0
        )
        assert calls == [("issue", "comment"), ("issue", "close")]

    def test_a_single_lane_run_never_closes_the_issue(self, drift_report, tmp_path, monkeypatch):
        # A floor-only dispatch whose findings are all registered reaches the
        # all-clear branch. Closing there would discard the scheduled newest
        # lane's open findings, which nothing else records.
        _write(tmp_path, "f.json", _floor("arrow"))
        _write(tmp_path, "s.json", _smoke("arrow", "floor", "fail", phase="smoke"))
        calls = []
        monkeypatch.setattr(drift_report, "_gh", lambda *a, **k: calls.append(a))
        monkeypatch.setattr(drift_report, "_find_open_issue", lambda *a, **k: 42)
        rc = drift_report.main(
            [
                str(tmp_path),
                "--repo",
                "haalfi/remote-store",
                "--run-url",
                "https://run",
                "--title",
                "t",
                "--known-findings",
                str(_register(tmp_path, ("arrow", "floor"))),
                "--today",
                str(TODAY),
            ]
        )
        assert rc == 0
        assert calls == [], "a single-lane run must not comment or close"


def _register(dir_: Path, *rows: tuple[str, str]) -> Path:
    path = dir_ / "register.md"
    path.write_text(
        "".join(f"| `[{extra}]` | {lane} | BUG-1 | why | 2026-12-31 |\n" for extra, lane in rows),
        encoding="utf-8",
    )
    return path


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
            [
                str(tmp_path),
                "--repo",
                "haalfi/remote-store",
                "--run-url",
                "https://run",
                "--title",
                "t",
                "--dry-run",
                "--today",
                str(TODAY),
            ]
        )
        assert rc == 0
        assert "## Drift detected" in capsys.readouterr().out

    def test_dry_run_prints_the_body_it_would_write(self, drift_report, tmp_path, monkeypatch, capsys):
        _write(tmp_path, "s3.json", _diff("s3"))
        _write(tmp_path, "s3-newest-smoke.json", _smoke("s3", "newest", "pass"))
        _write(tmp_path, "s3-floor.json", _floor("s3"))
        _write(tmp_path, "s3-floor-smoke.json", _smoke("s3", "floor", "pass"))
        monkeypatch.setattr(drift_report, "_gh", lambda *a, **k: None)
        drift_report.main(
            [
                str(tmp_path),
                "--repo",
                "haalfi/remote-store",
                "--run-url",
                "https://run",
                "--title",
                "t",
                "--dry-run",
                "--today",
                str(TODAY),
            ]
        )
        out = capsys.readouterr()
        assert "## Clear" in out.out
        assert "dry run" in out.err

    def test_empty_report_dir_is_a_no_op(self, drift_report, tmp_path, monkeypatch):
        """Still true, and now for a narrower reason than it used to be.

        The guard is `Reports.__bool__`, which the calendar state joined, so
        "no artefacts" is a no-op only while no support window has also crossed.
        `TestSupportWindowSignal` pins the other half.
        """
        monkeypatch.setattr(drift_report, "_gh", lambda *a, **k: (_ for _ in ()).throw(AssertionError("called gh")))
        assert (
            drift_report.main([str(tmp_path), "--repo", "r", "--run-url", "u", "--title", "t", "--today", str(TODAY)])
            == 0
        )


def _python_register(dir_: Path, *rows: tuple[str, str]) -> Path:
    """The interpreter register, as `| `3.10` | owner | rationale | review |` rows.

    A sibling of `_register` above, and deliberately a different file: the two
    registers are keyed differently, and one loader per file is what keeps them
    from reading each other's rows.
    """
    path = dir_ / "python-support.md"
    path.write_text(
        "| Interpreter | Owner | Rationale | Review by |\n|---|---|---|---|\n"
        + "".join(f"| `{version}` | ADR-0039 | kept deliberately | {review} |\n" for version, review in rows),
        encoding="utf-8",
    )
    return path


class TestRegisterExpiry:
    """`Review by` is read by code now, in both registers, through one predicate.

    It used to be read by nothing, which `KNOWN-FINDINGS.md` recorded as a
    hazard it did not enforce: a row past its date kept silencing its finding
    until a person noticed.
    """

    def test_a_future_date_has_not_expired(self, drift_report):
        assert drift_report.is_expired("2026-12-31", date(2026, 9, 17)) is False

    def test_the_date_itself_has_not_expired(self, drift_report):
        """A row is live through its review date; it lapses the day after.

        Pinned on both sides of the boundary so the comparison cannot silently
        become `<=`.
        """
        assert drift_report.is_expired("2026-09-17", date(2026, 9, 17)) is False
        assert drift_report.is_expired("2026-09-16", date(2026, 9, 17)) is True

    def test_an_unparseable_date_is_a_hard_failure(self, drift_report):
        """Not a row that never expires, which is the hazard being removed."""
        with pytest.raises(drift_report.RegisterDateError, match="not an ISO date"):
            drift_report.is_expired("next minor release", date(2026, 9, 17))

    def test_the_refusal_names_the_file_and_the_row(self, drift_report, tmp_path):
        """DRIFT-RULES Rule 2: name the element, not the fact of a problem.

        The validation lives in the loaders for exactly this reason — they know
        the path and the key, where `is_expired` only ever sees a bare string.
        "`Review by` is 'next minor release'" does not tell a maintainer which
        row to open, whichever of the two files it came from — and the file it
        came from is the first thing they need.
        """
        path = _python_register(tmp_path, ("3.10", "next minor release"))
        with pytest.raises(drift_report.RegisterDateError) as excinfo:
            drift_report.load_python_support_register(path)
        message = str(excinfo.value)
        assert "python-support.md" in message
        assert "`3.10`" in message

    def test_the_dependency_register_names_its_row_too(self, drift_report, tmp_path):
        path = dir_ = tmp_path / "register.md"
        dir_.write_text("| `[s3]` | floor | BUG-1 | why | whenever |\n", encoding="utf-8")
        with pytest.raises(drift_report.RegisterDateError) as excinfo:
            drift_report.load_known_findings(path)
        message = str(excinfo.value)
        assert "register.md" in message
        assert "`[s3]` / floor" in message

    def test_a_malformed_register_is_reported_rather_than_tracebacked(
        self, drift_report, tmp_path, monkeypatch, capsys
    ):
        """A hard failure is still a report. The run exits 1 and touches no issue.

        The `Drift-gate` declaration says so in these terms: nothing this script
        *finds* makes it exit non-zero, and only an uncomparable register date
        does.
        """
        monkeypatch.setattr(drift_report, "_gh", lambda *a, **k: (_ for _ in ()).throw(AssertionError("called gh")))
        bad = _python_register(tmp_path, ("3.10", "next minor release"))
        _write(tmp_path, "s3.json", _diff("s3"))
        rc = drift_report.main(
            [
                str(tmp_path),
                "--repo",
                "r",
                "--run-url",
                "u",
                "--title",
                "t",
                "--python-support-register",
                str(bad),
                "--today",
                str(TODAY),
            ]
        )
        assert rc == 1
        assert "unusable register" in capsys.readouterr().err

    def test_an_expired_dependency_row_stops_silencing_its_finding(self, drift_report, tmp_path):
        """The behaviour change to the dependency register, in the direction
        that matters: the finding comes back."""
        _write(tmp_path, "s3.json", _diff("s3"))
        _write(tmp_path, "s3-newest-smoke.json", _smoke("s3", "newest", "pass"))
        _write(tmp_path, "s3-floor.json", _floor("s3", "error", reason="no wheel"))
        _write(tmp_path, "s3-floor-smoke.json", _smoke("s3", "floor", "skipped"))
        reports = drift_report._load_reports(tmp_path)
        register = {("s3", "floor"): ("BUG-289", "2026-12-31")}
        assert drift_report.has_signal(reports, register, today=date(2026, 9, 17)) is False
        assert drift_report.has_signal(reports, register, today=date(2027, 1, 1)) is True

    def test_silencing_drops_only_the_expired_rows(self, drift_report):
        register = {("a", "floor"): ("X", "2026-12-31"), ("b", "floor"): ("Y", "2026-01-01")}
        assert drift_report.silencing(register, date(2026, 9, 17)) == {("a", "floor")}


class TestPythonSupportRegister:
    """The interpreter register's loader, and its disjointness from the other one."""

    def test_reads_version_owner_and_review_date(self, drift_report, tmp_path):
        path = _python_register(tmp_path, ("3.10", "2026-12-31"))
        assert drift_report.load_python_support_register(path) == {"3.10": ("ADR-0039", "2026-12-31")}

    def test_the_header_and_separator_are_not_rows(self, drift_report, tmp_path):
        """The measured failure mode of a loader written without a row shape:
        a four-cell match takes the header and the `|---|` separator too."""
        path = _python_register(tmp_path, ("3.10", "2026-12-31"))
        assert set(drift_report.load_python_support_register(path)) == {"3.10"}

    def test_a_missing_file_is_an_empty_register(self, drift_report, tmp_path):
        assert drift_report.load_python_support_register(tmp_path / "absent.md") == {}

    def test_the_two_loaders_do_not_read_each_others_rows(self, drift_report, tmp_path):
        """The collision this file's split exists to prevent, in both directions.

        Measured before the split: a four-cell loader pointed at
        `KNOWN-FINDINGS.md` matched all seven dependency rows plus the header
        and separator, inventing seven "interpreters" whose `Review by` was a
        prose paragraph — which `is_expired` would then reject.

        **Only one direction can use the committed files.** `PYTHON-SUPPORT.md`
        ships with an empty table on purpose, so asserting the dependency loader
        reads nothing from it passes for any row shape whatsoever, including a
        loader that reads interpreter rows — the assertion was vacuous. That
        direction takes a populated fixture instead, which is the state the
        collision would actually occur in.
        """
        assert drift_report.load_python_support_register(drift_report.KNOWN_FINDINGS) == {}
        populated = _python_register(tmp_path, ("3.10", "2026-12-31"), ("3.11", "2027-06-30"))
        assert drift_report.load_python_support_register(populated) != {}, "the fixture must carry rows to be a test"
        assert drift_report.load_known_findings(populated) == {}

    def test_the_committed_registers_carry_parseable_dates(self, drift_report):
        """Every live row's date can be compared, in both files.

        `is_expired` refuses an unparseable cell, so a row that cannot be dated
        would crash the weekly run rather than silence quietly. This is the test
        that keeps that refusal from being a landmine.
        """
        today = date(2026, 9, 17)
        for register in (
            drift_report.load_known_findings(),
            drift_report.load_python_support_register(),
        ):
            for _key, (_owner, review) in register.items():
                assert isinstance(drift_report.is_expired(review, today), bool)


class TestSupportWindowState:
    """The calendar half, over the committed classifiers and release dates."""

    def test_every_supported_interpreter_gets_a_row(self, drift_report):
        state = drift_report.support_window_state(date(2026, 9, 17))
        assert [row.version for row in state.rows] == ["3.10", "3.11", "3.12", "3.13", "3.14"]

    def test_nothing_is_past_its_window_today(self, drift_report):
        """As of the day this shipped, 3.10 was the closest at 17 days out."""
        state = drift_report.support_window_state(date(2026, 9, 17))
        assert state.unregistered == ()
        assert state.holds_issue is False

    def test_a_crossing_with_no_row_holds_the_issue(self, drift_report):
        state = drift_report.support_window_state(date(2026, 10, 6))
        assert state.unregistered == ("3.10",)
        assert state.holds_issue is True

    def test_a_registered_crossing_does_not_hold_the_issue(self, drift_report, tmp_path):
        register = drift_report.load_python_support_register(_python_register(tmp_path, ("3.10", "2027-06-30")))
        state = drift_report.support_window_state(date(2026, 10, 6), register)
        assert state.unregistered == ()
        assert state.holds_issue is False

    def test_an_expired_row_stops_silencing_the_crossing(self, drift_report, tmp_path):
        """The interpreter register's whole point: the date is the mechanism."""
        register = drift_report.load_python_support_register(_python_register(tmp_path, ("3.10", "2026-10-05")))
        state = drift_report.support_window_state(date(2026, 10, 6), register)
        assert state.unregistered == ("3.10",)
        assert state.holds_issue is True

    def test_a_narrowed_run_reports_the_crossing_without_holding_the_issue(self, drift_report):
        """A crossing is true on every run, and a narrowed non-dry run rewrites
        the whole body from its slice. So the crossing still renders — it just
        cannot be what forces the rewrite."""
        state = drift_report.support_window_state(date(2026, 10, 6), holds_issue=False)
        assert state.unregistered == ("3.10",)
        assert state.holds_issue is False


class TestSupportWindowSignal:
    """How the crossing reaches `has_signal`, `decide` and the body."""

    def _clean(self, tmp_path):
        _write(tmp_path, "s3.json", _diff("s3"))
        _write(tmp_path, "s3-newest-smoke.json", _smoke("s3", "newest", "pass"))
        _write(tmp_path, "s3-floor.json", _floor("s3"))
        _write(tmp_path, "s3-floor-smoke.json", _smoke("s3", "floor", "pass"))

    def test_an_unowned_crossing_is_a_signal_on_an_otherwise_clean_run(self, drift_report, tmp_path):
        self._clean(tmp_path)
        reports = dataclasses.replace(
            drift_report._load_reports(tmp_path),
            windows=drift_report.support_window_state(date(2026, 10, 6)),
        )
        assert drift_report.has_signal(reports, {}, today=date(2026, 10, 6)) is True
        assert drift_report.decide(reports, {}, today=date(2026, 10, 6))[0] == "update"

    def test_a_clean_run_with_no_crossing_still_closes(self, drift_report, tmp_path):
        """The passing direction, so the clause above cannot be satisfied by a
        predicate that simply always returns True."""
        self._clean(tmp_path)
        reports = dataclasses.replace(
            drift_report._load_reports(tmp_path),
            windows=drift_report.support_window_state(date(2026, 9, 17)),
        )
        assert drift_report.has_signal(reports, {}, today=date(2026, 9, 17)) is False
        assert drift_report.decide(reports, {}, today=date(2026, 9, 17))[0] == "close"

    def test_a_crossing_on_a_narrowed_run_does_not_force_an_update(self, drift_report, tmp_path):
        self._clean(tmp_path)
        reports = dataclasses.replace(
            drift_report._load_reports(tmp_path),
            windows=drift_report.support_window_state(date(2026, 10, 6), holds_issue=False),
        )
        assert drift_report.has_signal(reports, {}, today=date(2026, 10, 6)) is False

    def test_a_narrowed_run_may_not_close_the_issue_over_an_unowned_crossing(self, drift_report, tmp_path):
        """A narrowed run withholds the update; it must withhold the close too.

        Reproduced on the case the `SupportWindowState` docstring names,
        `extra: s3, lane: all`, with clean reports in both lanes and 3.10 one
        day past its window: the run answered **close**, so the rolling issue
        would disappear while an interpreter sat past its window with nobody
        named. `holds_issue=False` is about not rewriting a body from a slice,
        and this file's own lane guard already ranks the two outcomes -- "the
        body is recoverable if it is wrong; a closed issue is not". Withholding
        the update while permitting the close took the worse half of that trade.
        `leave` takes neither: the body survives, and the next unnarrowed run
        decides.
        """
        self._clean(tmp_path)
        reports = dataclasses.replace(
            drift_report._load_reports(tmp_path),
            windows=drift_report.support_window_state(date(2026, 10, 6), holds_issue=False),
        )
        action, reason = drift_report.decide(reports, {}, ["s3"], today=date(2026, 10, 6))
        assert action == "leave"
        assert "3.10" in reason

    def test_a_narrowed_run_with_a_registered_crossing_still_closes(self, drift_report, tmp_path):
        """The other direction, so the clause above is not "narrowed never closes".

        A crossing somebody owns is not an open question, so it does not stand
        between an all-clear run and the close.
        """
        self._clean(tmp_path)
        register = drift_report.load_python_support_register(_python_register(tmp_path, ("3.10", "2027-06-30")))
        reports = dataclasses.replace(
            drift_report._load_reports(tmp_path),
            windows=drift_report.support_window_state(date(2026, 10, 6), register, holds_issue=False),
        )
        assert drift_report.decide(reports, {}, ["s3"], today=date(2026, 10, 6))[0] == "close"

    def test_a_narrowed_dispatch_with_no_artefacts_leaves_the_issue_alone(self, drift_report, tmp_path, monkeypatch):
        """The emptiness guard must key on `holds_issue`, not on `unregistered`.

        Measured before the fix, on a narrowed dispatch (one extra of fourteen)
        whose legs uploaded nothing, with a crossing present: `holds_issue` was
        correctly False, but `Reports.__bool__` read `unregistered` and so came
        back True, `main` did not return early, `_incomplete_legs` reported two
        lost legs, and `decide` answered `update` -- re-rendering the whole
        rolling issue from a one-extra slice. That is BUG-282, which the
        workflow header warns about, and it is a regression against the
        pre-change behaviour where the same run returned 0 untouched.
        """
        calls: list[tuple] = []
        monkeypatch.setattr(drift_report, "_gh", lambda *a, **k: calls.append(a))
        monkeypatch.setattr(drift_report, "_find_open_issue", lambda *a, **k: None)
        monkeypatch.setattr(drift_report, "list_extras", lambda: ["s3", "arrow"])
        rc = drift_report.main(
            [
                str(tmp_path),
                "--repo",
                "haalfi/remote-store",
                "--run-url",
                "https://run",
                "--title",
                "t",
                "--expect-extras",
                "s3",
                "--expect-lanes",
                "newest,floor",
                "--today",
                "2026-10-06",
            ]
        )
        assert rc == 0
        assert calls == [], "a narrowed dispatch with no artefacts must not rewrite the issue body"

    def test_the_emptiness_message_does_not_deny_a_crossing_it_computed(
        self, drift_report, tmp_path, monkeypatch, capsys
    ):
        """The third reader of the `holds_issue` / `unregistered` distinction.

        The two found in round 2 were `Reports.__bool__` and the rendered
        section. This is the stderr line the same guard prints on the way out,
        and it said "no support window crossed" on a run where
        `unregistered == ('3.10',)` -- measured. It is the line a maintainer
        reads in a `workflow_dispatch` step log precisely to learn what the run
        saw, so denying the crossing sends them away from it. Nothing else
        changes: the run still touches no issue and still exits 0.
        """
        monkeypatch.setattr(drift_report, "_gh", lambda *a, **k: pytest.fail("touched the issue"))
        monkeypatch.setattr(drift_report, "_find_open_issue", lambda *a, **k: None)
        monkeypatch.setattr(drift_report, "list_extras", lambda: ["s3", "arrow"])
        rc = drift_report.main(
            [
                str(tmp_path),
                "--repo",
                "haalfi/remote-store",
                "--run-url",
                "https://run",
                "--title",
                "t",
                "--expect-extras",
                "s3",
                "--expect-lanes",
                "newest,floor",
                "--today",
                "2026-10-06",
            ]
        )
        assert rc == 0
        err = capsys.readouterr().err
        assert "no support window crossed" not in err
        assert "3.10" in err, "the message must name the crossing this run computed and withheld"

    def test_the_emptiness_message_says_so_when_nothing_has_crossed(self, drift_report, tmp_path, monkeypatch, capsys):
        """The other direction, so the clause above is not "always name a crossing".

        On `TODAY` nothing is past its window, so the plain sentence is true and
        must be the one printed. **This test asserted only the exit code until a
        review pointed out that made it no control at all**: it passed against
        any wording, including the inverse defect of naming a crossing on a run
        where none had happened. A control that cannot fail does not bound the
        clause it sits beside.
        """
        monkeypatch.setattr(drift_report, "_gh", lambda *a, **k: pytest.fail("touched the issue"))
        monkeypatch.setattr(drift_report, "_find_open_issue", lambda *a, **k: None)
        rc = drift_report.main([str(tmp_path), "--repo", "r", "--run-url", "u", "--title", "t", "--today", str(TODAY)])
        assert rc == 0
        err = capsys.readouterr().err
        assert "no support window crossed" in err
        assert "past its support window" not in err

    def test_a_bad_today_is_reported_rather_than_tracebacked(self, drift_report, tmp_path, monkeypatch, capsys):
        """The flag this change introduced, held to this file's own standard.

        Ten lines above the register catch sits the comment "a hard failure is
        still a report rather than a traceback"; the new flag then raised
        `ValueError: Invalid isoformat string` out of `main`.
        """
        monkeypatch.setattr(drift_report, "_gh", lambda *a, **k: pytest.fail("touched the issue"))
        rc = drift_report.main(
            [str(tmp_path), "--repo", "r", "--run-url", "u", "--title", "t", "--today", "next Monday"]
        )
        assert rc == 1
        assert "--today must be YYYY-MM-DD" in capsys.readouterr().err

    def test_a_malformed_expect_extras_is_reported_rather_than_tracebacked(
        self, drift_report, tmp_path, monkeypatch, capsys
    ):
        """The input a workflow expression supplies, so the one most likely to arrive broken.

        `--expect-extras` and `--expect-lanes` are interpolated from another
        job's outputs, not typed. Measured before this fix: a value opening `[`
        that did not parse reached `main` as a `json.JSONDecodeError` traceback
        from inside `_parse_expected`, which told an operator nothing about
        which argument was wrong.
        """
        monkeypatch.setattr(drift_report, "_gh", lambda *a, **k: pytest.fail("touched the issue"))
        rc = drift_report.main(
            [
                str(tmp_path),
                "--repo",
                "r",
                "--run-url",
                "u",
                "--title",
                "t",
                "--today",
                str(TODAY),
                "--expect-extras",
                "[bad",
            ]
        )
        assert rc == 1
        err = capsys.readouterr().err
        assert "::error::" in err
        assert "'[bad'" in err, "name the value that arrived, not just the failure"

    def test_expect_extras_that_parses_to_a_non_list_is_refused(self, drift_report, tmp_path, monkeypatch, capsys):
        """`[` is the JSON sniff, so valid JSON of the wrong shape gets that far."""
        monkeypatch.setattr(drift_report, "_gh", lambda *a, **k: pytest.fail("touched the issue"))
        rc = drift_report.main(
            [
                str(tmp_path),
                "--repo",
                "r",
                "--run-url",
                "u",
                "--title",
                "t",
                "--today",
                str(TODAY),
                "--expect-lanes",
                '["ok"',
            ]
        )
        assert rc == 1
        assert "::error::" in capsys.readouterr().err

    def test_a_list_of_non_names_is_refused_rather_than_coerced(self, drift_report, tmp_path, monkeypatch, capsys):
        """The check the `Raises:` clause promised and the code did not make.

        Measured: `--expect-extras '[1,2]'` passed the container check, went
        through `str()`, and rendered `[1]` and `[2]` as **fabricated incomplete
        legs** on an otherwise clean run — then answered `create/update`, so a
        scheduled run would have rewritten the rolling issue with them.
        Coercion is the wrong instinct for an input a workflow expression
        supplies: a `json.dumps` of the wrong object is as likely from a
        template as a truncated string.
        """
        monkeypatch.setattr(drift_report, "_gh", lambda *a, **k: pytest.fail("touched the issue"))
        rc = drift_report.main(
            [
                str(tmp_path),
                "--repo",
                "r",
                "--run-url",
                "u",
                "--title",
                "t",
                "--today",
                str(TODAY),
                "--expect-extras",
                "[1,2]",
            ]
        )
        assert rc == 1
        err = capsys.readouterr().err
        assert "not a name" in err
        assert "1" in err, "name the element that arrived"

    def test_an_unknown_lane_is_refused(self, drift_report, tmp_path, monkeypatch, capsys):
        """`LANES` is a closed two-element set, so an unknown lane cannot be interpreted.

        Measured before this check: `--expect-lanes bogus` was accepted whole.
        The body announced "This run covered the bogus lane only", printed a
        `Bogus` verdict column, and `_incomplete_leg_rows` mapped the unknown
        lane onto the floor lane — so a run missing every newest-lane report
        read as complete. That is exactly the "misreport which legs ran" harm
        the `Drift-gate` declaration gives as its reason to refuse an input.
        """
        monkeypatch.setattr(drift_report, "_gh", lambda *a, **k: pytest.fail("touched the issue"))
        rc = drift_report.main(
            [
                str(tmp_path),
                "--repo",
                "r",
                "--run-url",
                "u",
                "--title",
                "t",
                "--today",
                str(TODAY),
                "--expect-lanes",
                "bogus",
            ]
        )
        assert rc == 1
        err = capsys.readouterr().err
        assert "'bogus'" in err
        assert "'floor', 'newest'" in err, "say what the closed set is"

    def test_the_real_lanes_are_still_accepted(self, drift_report, tmp_path, monkeypatch):
        """The other direction, so the clause above is not "lanes never parse"."""
        monkeypatch.setattr(drift_report, "_gh", lambda *a, **k: pytest.fail("touched the issue"))
        monkeypatch.setattr(drift_report, "_find_open_issue", lambda *a, **k: None)
        for value in ("newest,floor", "newest", '["newest", "floor"]'):
            rc = drift_report.main(
                [
                    str(tmp_path),
                    "--repo",
                    "r",
                    "--run-url",
                    "u",
                    "--title",
                    "t",
                    "--today",
                    str(TODAY),
                    "--expect-lanes",
                    value,
                ]
            )
            assert rc == 0, f"{value!r} is a legitimate lane list"

    def test_an_undated_classifier_is_reported_rather_than_tracebacked(
        self, drift_report, python_support, tmp_path, monkeypatch, capsys
    ):
        """The second hard failure, which the `Drift-gate` text said did not exist.

        `supported_versions` refuses a classifier with no `PYTHON_RELEASES`
        row -- DRIFT-RULES Rule 3, since an unlisted classifier is what the
        enumeration exists to catch. Measured before this fix:
        `UnknownInterpreterError` propagated out of `main` as a traceback, so
        the weekly run died instead of reporting. `preflight`'s
        `gen_python_support.py --check` makes the state unreachable on master,
        which is why it is a bound rather than a live bug -- but the same
        argument that moved `RegisterDateError` to a reported failure applies
        unchanged, and the declaration now names both.
        """
        monkeypatch.setattr(drift_report, "_gh", lambda *a, **k: pytest.fail("touched the issue"))
        monkeypatch.setattr(drift_report, "_find_open_issue", lambda *a, **k: None)
        monkeypatch.delitem(python_support.PYTHON_RELEASES, "3.14")
        rc = drift_report.main([str(tmp_path), "--repo", "r", "--run-url", "u", "--title", "t", "--today", str(TODAY)])
        assert rc == 1
        err = capsys.readouterr().err
        assert "::error::" in err
        assert "3.14" in err, "DRIFT-RULES Rule 2: name the classifier, not the fact of a problem"

    def test_an_empty_report_dir_with_a_crossing_still_opens_the_issue(self, drift_report, tmp_path, monkeypatch):
        """The guard fix, pinned.

        `main` returns early when `Reports` is falsy, and the calendar half comes
        from no artefact. Before the state was attached to `Reports`, a run whose
        download produced nothing could not report a crossing at all: no body,
        no issue, exit 0 — the silent-close class this file was already hardened
        against, arriving through the guard.
        """
        calls: list[tuple] = []
        monkeypatch.setattr(drift_report, "_gh", lambda *a, **k: calls.append(a))
        monkeypatch.setattr(drift_report, "_find_open_issue", lambda *a, **k: None)
        monkeypatch.setattr(drift_report, "list_extras", lambda: ["s3"])
        rc = drift_report.main(
            [
                str(tmp_path),
                "--repo",
                "haalfi/remote-store",
                "--run-url",
                "https://run",
                "--title",
                "t",
                "--expect-extras",
                "s3",
                "--expect-lanes",
                "newest,floor",
                "--today",
                "2026-10-06",
            ]
        )
        assert rc == 0
        assert calls, "a crossing with no artefacts must still reach the issue"
        assert calls[0][:2] == ("issue", "create")


class TestRenderSupportWindows:
    """The section a maintainer reads."""

    def test_renders_on_a_clean_week_too(self, drift_report):
        """The number nobody can compute is how much time is left, so the rows
        are worth printing even when nothing has crossed."""
        lines = drift_report._render_support_windows(
            drift_report.support_window_state(date(2026, 9, 17)), {}, date(2026, 9, 17)
        )
        body = "\n".join(lines)
        assert "## Support windows" in body
        assert "| `3.10` | 2021-10-04 | 2026-10-04 | 17 days left |" in body
        assert "| `3.14` | 2025-10-07 | 2030-10-07 | 1481 days left |" in body

    def test_marks_an_unregistered_crossing(self, drift_report):
        lines = drift_report._render_support_windows(
            drift_report.support_window_state(date(2026, 10, 6)), {}, date(2026, 10, 6)
        )
        body = "\n".join(lines)
        assert "**2 days past, unregistered**" in body
        assert "holds this issue open" in body

    def test_a_narrowed_run_does_not_claim_the_crossing_holds_the_issue(self, drift_report):
        """The reading half of the `holds_issue` distinction.

        Caught by the sibling sweep over the `Reports.__bool__` fix: the section
        was keyed on `unregistered`, so a narrowed dispatch printed "holds this
        issue open" for a crossing that could not hold it — sending a reader to
        look for an issue the run was never going to keep open.
        """
        narrowed = drift_report.support_window_state(date(2026, 10, 6), holds_issue=False)
        body = "\n".join(drift_report._render_support_windows(narrowed, {}, date(2026, 10, 6)))
        assert "2 days past, unregistered" in body
        assert "covered only part of the matrix" in body
        assert "` holds this issue open" not in body
        # And it says the half that IS true of a narrowed run, since `decide`
        # refuses to close over the crossing: a reader told only what the run
        # will not do cannot distinguish that from the crossing having no effect.
        assert "stop this run closing the issue" in body

    def test_names_the_owner_of_a_registered_crossing(self, drift_report, tmp_path):
        register = drift_report.load_python_support_register(_python_register(tmp_path, ("3.10", "2027-06-30")))
        lines = drift_report._render_support_windows(
            drift_report.support_window_state(date(2026, 10, 6), register), register, date(2026, 10, 6)
        )
        body = "\n".join(lines)
        assert "known, ADR-0039, review by 2027-06-30" in body
        assert "none of them is holding this issue open" in body

    def test_says_when_a_registered_rows_date_has_passed(self, drift_report, tmp_path):
        register = drift_report.load_python_support_register(_python_register(tmp_path, ("3.10", "2026-10-05")))
        lines = drift_report._render_support_windows(
            drift_report.support_window_state(date(2026, 10, 6), register), register, date(2026, 10, 6)
        )
        body = "\n".join(lines)
        assert "review date passed" in body
        assert "holds this issue open" in body

    def test_states_that_a_closed_window_does_not_require_a_drop(self, drift_report):
        """The rule promises a floor, not a ceiling, and a report that reads as
        an obligation would invert it."""
        lines = drift_report._render_support_windows(
            drift_report.support_window_state(date(2026, 9, 17)), {}, date(2026, 9, 17)
        )
        assert "licenses a drop; it never requires one" in "\n".join(lines)

    def test_an_empty_state_renders_nothing(self, drift_report):
        assert drift_report._render_support_windows(drift_report.SupportWindowState(), {}, date(2026, 9, 17)) == []


class TestThisModuleIsReproducible:
    """A guard over this file's own source, not over `drift_report`.

    Seven tests here went red on a shifted clock: one from 2026-10-05, when
    3.10's window closes against a deliberately empty register, and six more
    from 2027-01-01, when every `KNOWN-FINDINGS.md` row expires at once. Each
    had let `today` default to `date.today()`, so each asserted the answer for
    the day it happened to run. Nothing caught it because they were all green
    on the day they were written, which is the property a test cannot have and
    also be a test.

    The fix was mechanical; this is what keeps it. Two earlier attempts at the
    same class were caught by review rather than by a gate -- a clock-reading
    assertion in `test_gen_python_support.py`, and these seven -- so the guard
    is deliberately structural: it reads the source, because a test that runs
    the code can only ever observe the current date.
    """

    # Every `drift_report` function whose `today` DEFAULTS, so omitting it
    # silently asserts the day the test ran. Derived by reading each signature
    # rather than recalled: `has_signal`, `decide`, `_render_body` and
    # `_render_smoke_verdicts` default it; `support_window_state`, `is_expired`,
    # `silencing`, `_known_note`, `_render_support_windows`,
    # `_render_isolation_findings` and `_render_floor_lane` REQUIRE it, so they
    # cannot be got wrong this way and need no policing. The first two were the
    # only entries when this guard was written, which left the two renderers
    # unguarded — and `_render_body` was already one of the seven offenders the
    # class docstring describes, so the omission was not hypothetical.
    TIME_DEPENDENT = {"has_signal", "decide", "_render_body", "_render_smoke_verdicts"}

    def _calls(self):
        import ast

        tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                fn = node.func
                name = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", None)
                yield name, node

    def test_no_call_in_this_module_lets_today_default(self):
        offenders = [
            f"line {node.lineno}: {name}()"
            for name, node in self._calls()
            if name in self.TIME_DEPENDENT and "today" not in {kw.arg for kw in node.keywords}
        ]
        assert offenders == [], f"pass today=TODAY, or the assertion is about the day it ran: {offenders}"

    def test_every_non_zero_exit_from_main_is_reported(self):
        """The `Drift-gate` block's claim, pinned as a property rather than a count.

        The declaration said "nothing it FINDS makes it exit non-zero" and then
        listed what does. The list was wrong three times — as one entry, as two,
        and as a class with `gh` named as the sole non-input escape — because
        each round added a path without revisiting the sentence. So the sentence
        stopped enumerating and this asserts the property instead.

        **Two earlier versions of this guard were themselves unsound**, which is
        the more useful lesson. The first scanned six source lines backwards and
        passed a bare `return 1` whose window reached an unrelated branch's
        print. The second required a report anywhere earlier in the same block —
        and `main`'s top level contains one stderr print, so every statement
        after it was pre-satisfied and the tail of `main` was unguarded. Each
        narrowing was refuted by a state the narrowing did not consider, which
        is the signal to stop narrowing and constrain the subject instead.

        **So the rule is adjacency, and `main` complies with it:** a non-zero
        exit is `print(..., file=sys.stderr)` immediately followed by the exit.
        That is checkable without modelling control flow, and it covers `return`,
        `sys.exit` and `raise SystemExit` alike — `return` alone made
        `sys.exit(1)` invisible, and `sys.exit(main())` is this module's own
        idiom, so that was not an exotic shape to miss.
        """
        import ast

        source = Path(SCRIPTS / "drift_report.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        main = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "main")

        def is_stderr_report(stmt: ast.stmt) -> bool:
            """`print(..., file=sys.stderr)` — the stream matters, not just `file=`."""
            call = stmt.value if isinstance(stmt, ast.Expr) else None
            if not isinstance(call, ast.Call) or getattr(call.func, "id", None) != "print":
                return False
            for kw in call.keywords:
                if kw.arg == "file" and isinstance(kw.value, ast.Attribute) and kw.value.attr == "stderr":
                    return True
            return False

        def exit_code(stmt: ast.stmt) -> object | None:
            """The non-zero code this statement leaves the process with, or None.

            `return <literal>`, `sys.exit(<literal>)` and `raise SystemExit(...)`
            are one thing from a caller's point of view. A non-literal code
            (`return rc`) is deliberately NOT treated as an exit: this guard
            cannot evaluate it, and claiming to would be the third unsound
            version. `main` uses literals, and this test is what keeps that true.
            """
            if isinstance(stmt, ast.Return) and isinstance(stmt.value, ast.Constant) and stmt.value.value:
                return stmt.value.value
            call = stmt.value if isinstance(stmt, ast.Expr) else None
            if isinstance(stmt, ast.Raise):
                call = stmt.exc
            if isinstance(call, ast.Call):
                name = getattr(call.func, "attr", None) or getattr(call.func, "id", None)
                if name in {"exit", "SystemExit"} and call.args:
                    arg = call.args[0]
                    if isinstance(arg, ast.Constant) and arg.value:
                        return arg.value
            return None

        # Nested functions are their own scope: a helper defined inside `main`
        # returning 1 is not `main` exiting, and counting it produced a false
        # positive that would have blocked a legitimate refactor.
        nested = {
            n for fn in ast.walk(main) if fn is not main and isinstance(fn, ast.FunctionDef) for n in ast.walk(fn)
        }

        exits, unreported = [], []
        for node in ast.walk(main):
            if node in nested:
                continue
            for attr in ("body", "orelse", "finalbody"):
                block = getattr(node, attr, None)
                if not isinstance(block, list):
                    continue
                for i, stmt in enumerate(block):
                    if stmt in nested or exit_code(stmt) is None:
                        continue
                    exits.append(stmt.lineno)
                    if i == 0 or not is_stderr_report(block[i - 1]):
                        unreported.append(stmt.lineno)

        # A FLOOR, not an equality. Derivation: the `return 1` statements inside
        # `main` at the time of writing are four -- the `--today` parse, the
        # register load, the undated classifier and the unusable expect-list --
        # each preceded by its `::error::` print. Equality was the first
        # spelling and it was wrong in a way the attack harness caught: adding a
        # new, *correctly reported* exit made the count five and failed the
        # test, so the check blocked exactly the change it exists to bless. The
        # floor keeps what equality was for -- if a `return 1` becomes
        # `return rc`, this guard cannot see it, the count drops to three and
        # this line fires.
        #
        # Stated bound: an exit *added* with a non-literal code is invisible to
        # this guard. Evaluating arbitrary expressions is what the two unsound
        # earlier versions tried; the floor plus the adjacency rule is what can
        # be checked soundly.
        assert len(exits) >= 4, f"expected at least main's four non-zero exits, found {len(exits)} at {exits}"
        assert unreported == [], (
            f"a non-zero exit whose immediately preceding sibling is not a stderr report, at line(s) {unreported}"
        )

    def test_no_main_invocation_in_this_module_omits_today(self):
        """`main` takes the day as `--today` inside its argv rather than a kwarg.

        The one that went red first was a `main` call: an all-clear run that
        stopped closing the issue once 3.10 crossed its window.
        """
        import ast

        offenders = [
            f"line {node.lineno}" for name, node in self._calls() if name == "main" and "--today" not in ast.dump(node)
        ]
        assert offenders == [], f"add '--today', str(TODAY) to the argv: {offenders}"


# ---------------------------------------------------------------------------
# The published conda recipe
# ---------------------------------------------------------------------------

_SAMPLE_DIFF = """\
-  - pyarrow >=14.0.0
+  - pyarrow >=12.0.0
"""


# Two register keys, distinct and obviously synthetic. A real one is
# `drift_feedstock.fingerprint()` over the published body; these only have to be
# the right *shape*, which is what the loader keys on.
_FP = "sha256:" + "a" * 64
_FP_OTHER = "sha256:" + "b" * 64


def _feedstock(status: str, **kw) -> dict:
    return {
        "status": status,
        "remote_version": "0.32.0",
        "newest_tag": "v0.32.0",
        "trailing": False,
        "reason": f"synthetic {status}",
        "diff": "",
        "keys": [],
        "fingerprint": "",
        **kw,
    }


def _all_clear(dir_: Path, extras: list[str]) -> None:
    """One clean leg per extra per lane, so only the feedstock can decide."""
    for extra in extras:
        _write(dir_, f"{extra}-newest-diff.json", _diff(extra))
        _write(dir_, f"{extra}-newest-smoke.json", _smoke(extra, "newest", "pass"))
        _write(dir_, f"{extra}-floor-resolve.json", _floor(extra))
        _write(dir_, f"{extra}-floor-smoke.json", _smoke(extra, "floor", "pass"))


class TestFeedstockLoad:
    def test_absent_flag_is_absent_status(self, drift_report):
        assert drift_report.load_feedstock_report(None).status == "absent"

    def test_a_report_round_trips(self, drift_report, tmp_path):
        path = tmp_path / "f.json"
        path.write_text(
            json.dumps(_feedstock("drift", keys=["about.summary"], diff=_SAMPLE_DIFF)),
            encoding="utf-8",
        )
        state = drift_report.load_feedstock_report(path)
        assert state.status == "drift"
        assert state.keys == ("about.summary",)
        assert state.remote_version == "0.32.0"

    @pytest.mark.parametrize(
        ("case", "payload"),
        [
            ("missing file", None),
            ("not json", "{{{"),
            ("not an object", "[1, 2]"),
            ("no status", '{"remote_version": "0.32.0"}'),
            ("status is not a string", '{"status": ["drift"]}'),
        ],
    )
    def test_an_unusable_report_is_named_rather_than_skipped_or_raised(self, drift_report, tmp_path, case, payload):
        """Named, not skipped -- and not fatal either.

        Skipping would retire the signal while the issue kept closing on "all
        clear", the silent-close shape ``_load_reports`` records for artefacts.
        Raising costs more than it buys: this is read before the issue update,
        so one broken step would take that week's diffs, floor results and
        smoke verdicts down with it, for a reason that has nothing to do with
        them -- the failure ``_load_reports`` was hardened against, arriving
        from the other side. So it becomes an ``error``, which holds the issue
        open and says why.
        """
        path = tmp_path / "f.json"
        if payload is not None:
            path.write_text(payload, encoding="utf-8")
        state = drift_report.load_feedstock_report(path)
        assert state.status == "error"
        assert str(path) in state.reason

    def test_an_unusable_report_still_holds_the_issue(self, drift_report, tmp_path, capsys):
        """Tolerating it must not mean tolerating it into silence.

        Driven through ``main`` on an otherwise-clean unnarrowed run, so
        ``holds_issue`` is the value ``main`` computes rather than one this test
        sets. Setting it by hand would pin ``has_signal`` and leave the field's
        own derivation -- the narrowing rule -- untested under this name.
        """
        reports_dir = tmp_path / "reports"
        extras = drift_report.list_extras()
        for extra in extras:
            _write(reports_dir, f"{extra}-newest-diff.json", _diff(extra))
            _write(reports_dir, f"{extra}-newest-smoke.json", _smoke(extra, "newest", "pass"))
            _write(reports_dir, f"{extra}-floor-resolve.json", _floor(extra))
            _write(reports_dir, f"{extra}-floor-smoke.json", _smoke(extra, "floor", "pass"))
        broken = tmp_path / "f.json"
        broken.write_text("{{{", encoding="utf-8")
        rc = drift_report.main(
            [
                str(reports_dir),
                "--repo",
                "x/y",
                "--run-url",
                "http://run",
                "--title",
                "t",
                "--expect-extras",
                json.dumps(extras),
                "--expect-lanes",
                "newest,floor",
                "--feedstock-report",
                str(broken),
                "--today",
                str(TODAY),
                "--dry-run",
            ]
        )
        captured = capsys.readouterr()
        assert rc == 0
        # Everything else is clean, so only the unreadable report can be doing this.
        assert "would create/update" in captured.err
        assert "holds this issue open" in captured.out

    def test_an_unusable_report_does_not_cost_the_other_signals(self, drift_report, tmp_path, capsys):
        """The blast radius, pinned.

        A drifted extra must still reach the issue when the feedstock report is
        unreadable -- that is the whole reason this is a status rather than an
        exit. The rows are asserted **in the body**: ``rc == 0`` alone would
        pass for a run that silently dropped them, which is the failure this
        test is named for (`sdd/TESTING.md` Rule 1 -- "no crash" is not a test).
        """
        reports_dir = tmp_path / "reports"
        _write(
            reports_dir,
            "s3-newest-diff.json",
            _diff("s3", status="drift", stable_drift=[{"package": "s3fs", "baseline": "1.0", "resolved": "2.0"}]),
        )
        _write(reports_dir, "s3-newest-smoke.json", _smoke("s3", "newest", "pass"))
        broken = tmp_path / "f.json"
        broken.write_text("{{{", encoding="utf-8")
        rc = drift_report.main(
            [
                str(reports_dir),
                "--repo",
                "x/y",
                "--run-url",
                "http://run",
                "--title",
                "t",
                "--expect-extras",
                "s3",
                "--expect-lanes",
                "newest",
                "--feedstock-report",
                str(broken),
                "--today",
                str(TODAY),
                "--dry-run",
            ]
        )
        body = capsys.readouterr().out
        assert rc == 0
        assert "## Drift detected" in body
        assert "`s3fs`" in body
        assert "`2.0`" in body
        # ...and the broken input named beside them rather than instead of them.
        assert "## Conda feedstock" in body


class TestFeedstockVocabulary:
    """The status set is one vocabulary, and it lives where it is produced.

    ``drift_report`` held three copies of it -- two frozensets and a summary
    table -- against a producer that this module's own docstring says "owns the
    vocabulary". Nothing compared them, which is the parallel-artefact shape
    ``sdd/DRIFT-RULES.md`` Rule 3 forbids one layer up.
    """

    def test_every_status_the_watch_emits_is_classified(self, drift_report):
        """Derived from the producer, not restated here (DRIFT-RULES Rule 3)."""
        if str(SCRIPTS) not in sys.path:
            sys.path.insert(0, str(SCRIPTS))
        import drift_feedstock

        classified = drift_report.FEEDSTOCK_HOLDS | drift_report.FEEDSTOCK_INCONCLUSIVE | drift_report.FEEDSTOCK_CLEAR
        assert classified == drift_feedstock.STATUSES

    def test_every_status_renders_a_summary(self, drift_report):
        if str(SCRIPTS) not in sys.path:
            sys.path.insert(0, str(SCRIPTS))
        import drift_feedstock

        assert set(drift_report._FEEDSTOCK_SUMMARY) >= drift_feedstock.STATUSES

    @pytest.mark.parametrize("status", ["partial", "ok", "DRIFT", "", "no_baseline"])
    def test_an_unrecognised_status_fails_closed(self, drift_report, tmp_path, status):
        """A status nobody classified must not read as "the copies agree".

        Measured before this: ``'partial'``, ``'ok'``, ``'DRIFT'`` and ``''``
        every one gave ``blocks_close`` False, so a typo in the producer -- or a
        status added there and not here -- would let the run close the rolling
        issue while the published recipe disagreed with us. Failing open is the
        one direction this signal must never take.
        """
        path = tmp_path / "f.json"
        path.write_text(json.dumps({"status": status}), encoding="utf-8")
        state = drift_report.load_feedstock_report(path)
        assert state.status == "error"
        assert repr(status) in state.reason
        assert state.blocks_close


class TestFeedstockSignal:
    def test_only_holding_statuses_are_a_signal(self, drift_report):
        for status in ("drift", "missing", "error"):
            state = drift_report.FeedstockState(status=status, holds_issue=True)
            reports = drift_report.Reports(diffs={}, floors={}, smokes={}, feedstock=state)
            assert drift_report.has_signal(reports, today=TODAY), status

    def test_inconclusive_statuses_are_not_a_signal(self, drift_report):
        for status in ("unreachable", "no-baseline", "match", "ahead-of-tag", "absent"):
            state = drift_report.FeedstockState(status=status)
            reports = drift_report.Reports(diffs={}, floors={}, smokes={}, feedstock=state)
            assert not drift_report.has_signal(reports, today=TODAY), status

    def test_bool_keys_on_holds_issue_not_on_the_raw_status(self, drift_report):
        """BUG-282's shape arriving through the new signal.

        A published-copy drift is true on every run, so a narrowed dispatch
        whose legs uploaded nothing must stay falsy -- otherwise ``main``
        proceeds, every uncovered extra is reported as a lost leg, and the
        whole issue body is re-rendered from that slice.
        """
        narrowed = drift_report.Reports(
            diffs={},
            floors={},
            smokes={},
            feedstock=drift_report.FeedstockState(status="drift", holds_issue=False),
        )
        assert not narrowed
        full = dataclasses.replace(
            narrowed,
            feedstock=drift_report.FeedstockState(status="drift", holds_issue=True),
        )
        assert full

    @pytest.mark.parametrize("status", ["drift", "missing", "error", "unreachable", "no-baseline"])
    def test_these_statuses_refuse_a_close(self, drift_report, tmp_path, status):
        """Not knowing is not agreement.

        ``holds_issue`` is False for all of these on a narrowed run, and for
        the inconclusive pair on every run -- but closing would report a
        comparison this run did not perform, and a closed issue is not
        recoverable the way a rewritten body is.
        """
        _all_clear(tmp_path, ["s3"])
        reports = dataclasses.replace(
            drift_report._load_reports(tmp_path),
            feedstock=drift_report.FeedstockState(status=status),
        )
        action, reason = drift_report.decide(reports, expected=["s3"], today=TODAY)
        assert action == "leave", reason

    @pytest.mark.parametrize("status", ["match", "ahead-of-tag", "absent"])
    def test_these_statuses_permit_a_close(self, drift_report, tmp_path, status):
        _all_clear(tmp_path, ["s3"])
        reports = dataclasses.replace(
            drift_report._load_reports(tmp_path),
            feedstock=drift_report.FeedstockState(status=status),
        )
        action, reason = drift_report.decide(reports, expected=["s3"], today=TODAY)
        assert action == "close", reason


class TestFeedstockRegister:
    """DRIFT-RULES Rule 6: a divergence this project will not revert gets an owner.

    The published recipe is the one artifact pair here where a difference can
    be imposed without consent -- a conda-forge migrator, or the
    ``please add user @X`` flow editing ``extra.recipe-maintainers``. Without a
    register that edit holds the **shared** rolling issue open forever, which
    would retire the dependency lanes' own "drift cleared" signal.

    Keyed on the published body's **fingerprint**. An earlier spelling keyed on
    the YAML key path and had two measured defects a content key does not have:
    3 of the recipe's 62 real key paths could not be written as a row at all,
    and a difference that localized to ``?`` -- a column-0 comment -- was
    dropped before the check, so one registered key plus one unregistered
    comment edit closed the rolling issue. Both derivations are recorded in
    ``infra/drift-locks/FEEDSTOCK-DIVERGENCE.md``.
    """

    FP = _FP
    OTHER = _FP_OTHER

    def _register(self, tmp_path, rows):
        path = tmp_path / "FEEDSTOCK-DIVERGENCE.md"
        body = ["| Published body | Owner | Rationale | Review by |", "|---|---|---|---|"]
        body += [f"| `{key}` | {owner} | because | {review} |" for key, owner, review in rows]
        path.write_text("\n".join(body) + "\n", encoding="utf-8")
        return path

    def test_the_committed_register_loads_and_is_empty(self, drift_report):
        """Ships empty: nothing is accepted today, which is the healthy state."""
        assert drift_report.load_feedstock_register() == {}

    def test_a_row_round_trips(self, drift_report, tmp_path):
        path = self._register(tmp_path, [(self.FP, "haalfi", "2026-12-31")])
        assert drift_report.load_feedstock_register(path) == {self.FP: ("haalfi", "2026-12-31")}

    @pytest.mark.parametrize(
        "cell",
        ["extra.recipe-maintainers", "sha256:" + "a" * 63, "sha256:" + "A" * 64, "a" * 64, "sha256:zz"],
    )
    def test_a_cell_that_is_not_a_fingerprint_is_not_a_row(self, drift_report, tmp_path, cell):
        """The shape is the whole guard, so it is pinned rather than assumed.

        A row nothing matches is inert, which fails in the safe direction -- but
        the symptom is a row that does nothing and says nothing, so the file
        format section is what a new row is checked against.
        """
        path = self._register(tmp_path, [(cell, "haalfi", "2026-12-31")])
        assert drift_report.load_feedstock_register(path) == {}

    def test_the_three_row_shapes_are_disjoint(self, drift_report, tmp_path):
        """One file, one row of each shape, three loaders -- each reads only its own.

        Pinned over a file carrying all three rather than by pointing each
        loader at the committed registers: ``PYTHON-SUPPORT.md`` ships with no
        rows, so half of that spelling could not have failed.
        """
        path = tmp_path / "mixed.md"
        path.write_text(
            "| `[arrow]` | floor | BUG-287 | because | 2026-12-31 |\n"
            "| `3.10` | BUG-999 | because | 2026-12-31 |\n"
            f"| `{self.FP}` | haalfi | because | 2026-12-31 |\n",
            encoding="utf-8",
        )
        assert list(drift_report.load_known_findings(path)) == [("arrow", "floor")]
        assert list(drift_report.load_python_support_register(path)) == ["3.10"]
        assert list(drift_report.load_feedstock_register(path)) == [self.FP]

    def test_a_bad_review_date_is_refused_with_the_row_named(self, drift_report, tmp_path):
        path = self._register(tmp_path, [(self.FP, "haalfi", "whenever")])
        with pytest.raises(drift_report.RegisterDateError) as exc:
            drift_report.load_feedstock_register(path)
        assert self.FP in str(exc.value)

    def test_an_ownerless_row_is_refused_rather_than_silencing_anonymously(self, drift_report, tmp_path):
        """A row exists to name who is answerable; one that names nobody is not a row.

        A hard failure rather than a skip, for the same reason as the date
        above: silently ignoring it leaves a row that looks like a decision and
        has no effect, and the sibling registers record that as a live hazard.
        """
        path = self._register(tmp_path, [(self.FP, "   ", "2026-12-31")])
        with pytest.raises(drift_report.UnusableInputError) as exc:
            drift_report.load_feedstock_register(path)
        assert self.FP in str(exc.value)

    def test_a_registered_body_holds_nothing(self, drift_report):
        state = drift_report.FeedstockState(status="drift", fingerprint=self.FP, accepted=("haalfi", "2026-12-31"))
        assert state.registered
        assert not state.blocks_close

    def test_an_unregistered_body_holds(self, drift_report):
        state = drift_report.FeedstockState(status="drift", fingerprint=self.FP)
        assert not state.registered
        assert state.blocks_close

    def test_the_register_only_reaches_drift(self, drift_report):
        """A verdict that compared nothing is nobody's to accept.

        Every state here carries the same accepted row, so the status is the
        only thing that differs -- an earlier spelling gave both states empty
        keys as well, and could not have failed.
        """
        for status in ("missing", "error", "no-baseline", "unreachable"):
            state = drift_report.FeedstockState(status=status, fingerprint=self.FP, accepted=("haalfi", "2026-12-31"))
            assert not state.registered, status
            assert state.blocks_close, status

    def test_an_expired_row_stops_silencing(self, drift_report, tmp_path):
        path = self._register(tmp_path, [(self.FP, "haalfi", "2020-01-01")])
        register = drift_report.load_feedstock_register(path)
        assert drift_report.silencing(register, TODAY) == set()

    def test_end_to_end_a_registered_divergence_lets_the_issue_close(self, drift_report, tmp_path, capsys):
        """The consequence the register exists for, driven through ``main``."""
        reports_dir = tmp_path / "reports"
        extras = drift_report.list_extras()
        for extra in extras:
            _write(reports_dir, f"{extra}-newest-diff.json", _diff(extra))
            _write(reports_dir, f"{extra}-newest-smoke.json", _smoke(extra, "newest", "pass"))
            _write(reports_dir, f"{extra}-floor-resolve.json", _floor(extra))
            _write(reports_dir, f"{extra}-floor-smoke.json", _smoke(extra, "floor", "pass"))
        report = tmp_path / "f.json"
        report.write_text(
            json.dumps(_feedstock("drift", fingerprint=self.FP, keys=["extra.recipe-maintainers"], diff=_SAMPLE_DIFF)),
            encoding="utf-8",
        )
        register = self._register(tmp_path, [(self.FP, "haalfi", "2026-12-31")])
        argv = [
            str(reports_dir),
            "--repo",
            "x/y",
            "--run-url",
            "http://run",
            "--title",
            "t",
            "--expect-extras",
            json.dumps(extras),
            "--expect-lanes",
            "newest,floor",
            "--feedstock-report",
            str(report),
            "--dry-run",
        ]
        assert drift_report.main([*argv, "--today", str(TODAY), "--feedstock-register", str(register)]) == 0
        registered = capsys.readouterr()
        assert "would close" in registered.err
        assert "owned by haalfi" in registered.out

        # Same run, register absent: the identical difference holds the issue.
        absent = str(tmp_path / "none.md")
        assert drift_report.main([*argv, "--today", str(TODAY), "--feedstock-register", absent]) == 0
        assert "would create/update" in capsys.readouterr().err

        # Same run, a row for a DIFFERENT body: a row accepts one file, not a
        # standing permission. This is the property the key-path spelling could
        # not offer, because a second edit could leave its registered key intact.
        other = self._register(tmp_path, [(self.OTHER, "haalfi", "2026-12-31")])
        assert drift_report.main([*argv, "--today", str(TODAY), "--feedstock-register", str(other)]) == 0
        assert "would create/update" in capsys.readouterr().err

        # Same run, same row, past its `Review by`: the date is the mechanism.
        # Driven through `main` rather than asserted on `silencing`, which pins
        # the predicate and leaves its caller free to ignore it — measured:
        # dropping the expiry check from `main` survived the predicate test.
        expired = self._register(tmp_path, [(self.FP, "haalfi", "2020-01-01")])
        assert drift_report.main([*argv, "--today", str(TODAY), "--feedstock-register", str(expired)]) == 0
        assert "would create/update" in capsys.readouterr().err

    def test_a_registered_drift_is_not_described_as_withheld_for_narrowness(
        self, drift_report, tmp_path, monkeypatch, capsys
    ):
        """The empty-reports log line keys on registration, not on the raw status.

        With no artefacts at all the run prints why it is doing nothing. Keyed
        on ``status in FEEDSTOCK_HOLDS``, a registered drift was reported there
        as "this run was too narrow to act on that" -- which names the wrong
        reason on a full run and is simply false on any run.
        """
        monkeypatch.setattr(drift_report, "_gh", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no gh")))
        report = tmp_path / "f.json"
        report.write_text(json.dumps(_feedstock("drift", fingerprint=self.FP, diff=_SAMPLE_DIFF)), encoding="utf-8")
        register = self._register(tmp_path, [(self.FP, "haalfi", "2026-12-31")])
        empty = tmp_path / "reports"
        empty.mkdir()
        assert (
            drift_report.main(
                [
                    str(empty),
                    "--repo",
                    "x/y",
                    "--run-url",
                    "http://run",
                    "--title",
                    "t",
                    "--expect-extras",
                    json.dumps(drift_report.list_extras()),
                    "--expect-lanes",
                    "newest,floor",
                    "--feedstock-report",
                    str(report),
                    "--feedstock-register",
                    str(register),
                    "--today",
                    str(TODAY),
                ]
            )
            == 0
        )
        assert "too narrow" not in capsys.readouterr().err


class TestFeedstockNarrowing:
    """The BUG-282 guard's *other* branch, driven through ``main``.

    ``holds_issue = unnarrowed and status in FEEDSTOCK_HOLDS`` was only ever
    exercised end to end on its ``unnarrowed=True`` side; the False side was
    asserted on a hand-built state, which pins ``has_signal`` rather than the
    field's own derivation -- the objection this module raises for the sibling
    case two classes up.
    """

    def _run(self, drift_report, tmp_path, capsys, expect_extras, lanes):
        reports_dir = tmp_path / "reports"
        for extra in expect_extras:
            _write(reports_dir, f"{extra}-newest-diff.json", _diff(extra))
            _write(reports_dir, f"{extra}-newest-smoke.json", _smoke(extra, "newest", "pass"))
            if "floor" in lanes:
                _write(reports_dir, f"{extra}-floor-resolve.json", _floor(extra))
                _write(reports_dir, f"{extra}-floor-smoke.json", _smoke(extra, "floor", "pass"))
        report = tmp_path / "f.json"
        report.write_text(json.dumps(_feedstock("drift", keys=["about.summary"], diff=_SAMPLE_DIFF)), encoding="utf-8")
        rc = drift_report.main(
            [
                str(reports_dir),
                "--repo",
                "x/y",
                "--run-url",
                "http://run",
                "--title",
                "t",
                "--expect-extras",
                json.dumps(expect_extras),
                "--expect-lanes",
                ",".join(lanes),
                "--feedstock-report",
                str(report),
                "--today",
                str(TODAY),
                "--dry-run",
            ]
        )
        return rc, capsys.readouterr()

    def test_a_narrowed_dispatch_neither_rewrites_nor_closes(self, drift_report, tmp_path, capsys):
        """One extra of fourteen, with a real drift: the issue is left alone.

        Answering ``update`` here is BUG-282 -- the body would be re-rendered
        from this slice and every other extra's rows dropped.
        """
        rc, out = self._run(drift_report, tmp_path, capsys, ["s3"], ["newest", "floor"])
        assert rc == 0
        assert "would leave alone" in out.err
        assert "## Conda feedstock" in out.out
        assert "would hold this issue open on a full run" in out.out

    def test_the_same_drift_on_a_full_run_forces_the_update(self, drift_report, tmp_path, capsys):
        """The contrast that makes the previous test about narrowing."""
        rc, out = self._run(drift_report, tmp_path, capsys, drift_report.list_extras(), ["newest", "floor"])
        assert rc == 0
        assert "would create/update" in out.err
        assert "This holds this issue open" in out.out


class TestFeedstockSection:
    def _body(self, drift_report, tmp_path, state):
        _all_clear(tmp_path, ["s3"])
        reports = dataclasses.replace(drift_report._load_reports(tmp_path), feedstock=state)
        return drift_report._render_body(reports, "http://run", expected=["s3"], today=TODAY)

    @pytest.mark.parametrize(
        "status",
        ["match", "drift", "ahead-of-tag", "no-baseline", "missing", "unreachable", "error"],
    )
    def test_the_section_renders_on_every_verdict(self, drift_report, tmp_path, status):
        """Including ``match``.

        A section that appears only on a finding is indistinguishable from a
        signal that stopped running, and this one depends on a network fetch
        that can quietly start failing.
        """
        body = self._body(drift_report, tmp_path, drift_report.FeedstockState(status=status))
        assert "## Conda feedstock" in body

    def test_absent_renders_nothing(self, drift_report, tmp_path):
        body = self._body(drift_report, tmp_path, drift_report.FeedstockState())
        assert "## Conda feedstock" not in body

    def test_a_drift_leads_with_its_keys(self, drift_report, tmp_path):
        """DRIFT-RULES Rule 2: name the element, not the fact of a difference.

        The recipe is mostly comments, so a line number is not what changed.
        """
        state = drift_report.FeedstockState(
            status="drift",
            keys=("requirements.run_constraints[pyarrow]", "about.summary"),
            diff=_SAMPLE_DIFF,
            holds_issue=True,
        )
        body = self._body(drift_report, tmp_path, state)
        assert "`requirements.run_constraints[pyarrow]`" in body
        assert "`about.summary`" in body
        assert "pyarrow >=12.0.0" in body
        assert "holds this issue open" in body

    def test_a_narrowed_drift_says_both_halves(self, drift_report, tmp_path):
        # A reader told only what the run will not do cannot tell that from
        # "no effect" -- the wording rule the support-window section states.
        state = drift_report.FeedstockState(status="drift", holds_issue=False)
        body = self._body(drift_report, tmp_path, state)
        assert "would hold this issue open on a full run" in body
        assert "stop this run closing the issue" in body

    def test_trailing_is_informational(self, drift_report, tmp_path):
        state = drift_report.FeedstockState(status="match", trailing=True, newest_tag="v0.33.0")
        body = self._body(drift_report, tmp_path, state)
        assert "never holds this issue open" in body
        assert "release checklist owns it" in body

    def test_an_inconclusive_verdict_says_it_compared_nothing(self, drift_report, tmp_path):
        body = self._body(drift_report, tmp_path, drift_report.FeedstockState(status="no-baseline"))
        assert "not the same as finding them equal" in body

    def test_a_registered_drift_names_its_owner_and_drops_the_holding_prose(self, drift_report, tmp_path):
        """Two contradictory paragraphs, both of whose clauses were false.

        Keyed on ``status in FEEDSTOCK_HOLDS``, a registered drift rendered the
        narrowed-run sentence ("would hold this issue open on a full run ... it
        does stop this run closing the issue") directly under the sentence
        saying it holds nothing open. It does neither.
        """
        state = drift_report.FeedstockState(
            status="drift", fingerprint=_FP, accepted=("haalfi", "2026-12-31"), diff=_SAMPLE_DIFF
        )
        body = self._body(drift_report, tmp_path, state)
        assert "owned by haalfi" in body
        assert "2026-12-31" in body
        assert "hold this issue open" not in body
        assert "stop this run closing the issue" not in body

    def test_a_drift_publishes_the_fingerprint_a_row_would_carry(self, drift_report, tmp_path):
        """A reader cutting a row should not have to re-derive the key by hand."""
        state = drift_report.FeedstockState(status="drift", fingerprint=_FP, holds_issue=True)
        assert _FP in self._body(drift_report, tmp_path, state)
