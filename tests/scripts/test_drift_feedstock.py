"""Tests for scripts/drift_feedstock.py.

Every network call is mocked. What matters here is the taxonomy: the script's
whole design claim is that a failure of ours and a failure of the feedstock's
are different answers, so most of these pin which status a given failure
produces rather than that a failure was noticed.
"""

from __future__ import annotations

import http.client
import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPTS = ROOT / "scripts"


@pytest.fixture(scope="module")
def watch():
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    import drift_feedstock

    return drift_feedstock


HEADER = """\
# a header, replaced by the generator
# so it never takes part in a comparison
"""

BODY = """\
context:
  version: "0.32.0"

source:
  url: https://example.invalid/remote_store-${{ version }}.tar.gz
  sha256: aaaa

build:
  noarch: python
  number: 0

requirements:
  run_constraints:
    # a comment
    - pyarrow >=14.0.0
    - paramiko >=3.1

about:
  summary: "eight backends"
"""

RECIPE = HEADER + BODY


@pytest.fixture
def wire(monkeypatch, watch):
    """Replace all three lookups; each test overrides only what it is about."""

    def _wire(*, remote=RECIPE, baseline=RECIPE, tag=True, newest="v0.32.0", remote_exc=None, local=RECIPE):
        def fetch(url=watch.FEEDSTOCK_URL):
            if remote_exc is not None:
                raise remote_exc
            return remote

        monkeypatch.setattr(watch, "fetch_remote", fetch)
        monkeypatch.setattr(watch, "tag_exists", lambda *_a, **_k: tag)
        monkeypatch.setattr(watch, "baseline_at", lambda *_a, **_k: baseline)
        monkeypatch.setattr(watch, "newest_tag", lambda *_a, **_k: newest)
        return local

    return _wire


class TestStatusTableMatchesTheConstants:
    """DRIFT-RULES Rule 3, applied to this module's own docstring.

    The commit that centralised this vocabulary removed three hand-maintained
    copies from ``drift_report`` and imported them instead -- then left the
    docstring's Statuses table sitting directly above the definitions,
    asserting an equivalence ("are that table in code") that nothing checked.
    A prose rendering for humans beside a frozenset for code is a legitimate
    pair; an *unchecked* one is the parallel artefact the rule forbids.
    """

    def _table_rows(self, watch):
        """Parse the RST table by its column gaps, which is what separates its cells."""
        rows = {}
        for line in watch.__doc__.splitlines():
            if not line.startswith("``"):
                continue
            cells = re.split(r"\s{2,}", line.strip())
            if len(cells) != 4:
                continue
            status = cells[0].strip("`")
            rows[status] = (cells[2] != "no", cells[3] == "yes")
        return rows

    def test_the_table_names_exactly_the_statuses_the_code_defines(self, watch):
        assert set(self._table_rows(watch)) == set(watch.STATUSES)

    def test_each_row_agrees_with_its_frozenset(self, watch):
        for status, (forces, permits_close) in self._table_rows(watch).items():
            assert forces == (status in watch.HOLDS), f"{status}: `Forces update` column"
            assert permits_close == (status in watch.CLEAR), f"{status}: `Permits close` column"

    def test_the_parse_finds_every_row(self, watch):
        """Guard on the guard: a table this regex silently stopped matching would pass vacuously."""
        assert len(self._table_rows(watch)) == 7


class TestNormalization:
    def test_the_header_is_never_compared(self, watch):
        assert watch.body(RECIPE) == BODY

    def test_a_recipe_without_the_marker_is_compared_whole(self, watch):
        """A difference worth reporting, not one to normalize away."""
        assert watch.body("package:\n  name: x\n") == "package:\n  name: x\n"

    @pytest.mark.parametrize(("field", "changed"), [("number: 0", "number: 7"), ("sha256: aaaa", "sha256: bbbb")])
    def test_the_two_owned_fields_are_excluded(self, watch, field, changed):
        """conda-forge owns ``build.number``; ``source.sha256`` lands after the tag.

        Measured on this repository: the sha256 for a release is fetched from
        PyPI and committed *after* the tag is cut, so a tag structurally
        carries the previous release's digest.
        """
        assert watch.comparable(RECIPE) == watch.comparable(RECIPE.replace(field, changed))

    def test_masking_keeps_the_line_count(self, watch):
        """So a reported key path points at the line a reader will find."""
        masked = watch.mask_excluded(BODY)
        assert len(masked.splitlines()) == len(BODY.splitlines())

    @pytest.mark.parametrize("spelling", ["number : 7", "number:\t7", "number   :   7"])
    def test_an_owned_field_is_masked_however_it_is_spaced(self, watch, spelling):
        """The published file is not ours to keep tidy -- the same rule as `_VERSION_RE`.

        A `build.number` the far side wrote as `number : 7` would otherwise go
        unmasked and report as drift, on the one field conda-forge is
        explicitly entitled to change.
        """
        assert watch.comparable(RECIPE) == watch.comparable(RECIPE.replace("number: 0", spelling))

    def test_masking_does_not_reach_a_different_key(self, watch):
        """Tolerating spacing must not widen which keys are excluded."""
        assert watch.comparable(RECIPE) != watch.comparable(RECIPE.replace("noarch: python", "noarch: generic"))

    def test_a_real_change_is_not_excluded(self, watch):
        assert watch.comparable(RECIPE) != watch.comparable(RECIPE.replace("eight backends", "four backends"))

    def test_line_endings_are_not_a_difference(self, watch):
        """A CRLF remote is the same recipe, not a drifted one.

        Two ways this bites without normalisation, and the second only appears
        once the first is fixed: the version parse misses the marker line, and
        `mask_excluded` rewrites a masked line's terminator to `\\n` while
        leaving its neighbours `\\r\\n`, so every line differs. Four sibling
        generators in this repo normalise before comparing for the same reason.
        """
        crlf = RECIPE.replace("\n", "\r\n")
        assert watch.comparable(crlf) == watch.comparable(RECIPE)

    def test_a_crlf_remote_reports_match(self, watch, wire):
        """End to end: line endings must not reach the verdict."""
        wire(remote=RECIPE.replace("\n", "\r\n"))
        assert watch.compare().status == "match"


class TestFingerprint:
    """The register's key (DRIFT-RULES Rule 6), and the two properties it needs.

    **Total**: every possible published body has one, so no divergence is
    unregisterable and no key is unexpressible. **Exact**: it is the hash of the
    body this watch actually compares, so a row accepts one published file and
    stops matching the moment anything else on the far side changes.
    """

    def test_it_is_a_prefixed_sha256(self, watch):
        """Self-describing at the point of use, which is a row in a Markdown table."""
        assert re.fullmatch(r"sha256:[0-9a-f]{64}", watch.fingerprint(RECIPE))

    def test_the_two_owned_fields_do_not_change_it(self, watch):
        """Over ``comparable``, not over the raw bytes, and this is why.

        conda-forge bumps ``build.number`` on every rerender -- including in the
        very ``please add user @X`` commit the register exists for. A
        fingerprint over the raw file would expire its own row in the same
        commit that made the row necessary.
        """
        bumped = RECIPE.replace("number: 0", "number: 4").replace("sha256: aaaa", "sha256: bbbb")
        assert watch.fingerprint(bumped) == watch.fingerprint(RECIPE)

    def test_the_header_does_not_change_it(self, watch):
        assert watch.fingerprint(RECIPE) == watch.fingerprint("# something else entirely\n" + BODY)

    def test_crlf_does_not_change_it(self, watch):
        assert watch.fingerprint(RECIPE.replace("\n", "\r\n")) == watch.fingerprint(RECIPE)

    def test_any_further_edit_changes_it(self, watch):
        """The property that replaced the key-path register's fail-open.

        Keyed by key path, an accepted ``extra.recipe-maintainers`` edit plus an
        unregistered column-0 comment edit closed the rolling issue: the comment
        localized to ``?``, which ``differing_keys`` drops. Keyed by content,
        the second edit changes the key and the row simply stops matching.
        """
        registered = RECIPE.replace("eight backends", "four backends")
        plus_a_comment = registered.replace("# a comment", "# a comment, edited by hand")
        assert watch.fingerprint(plus_a_comment) != watch.fingerprint(registered)

    def test_compare_reports_the_published_bodys_fingerprint(self, watch, wire):
        """The verdict carries the key, so a maintainer can cut a row from it."""
        remote = RECIPE.replace("eight backends", "four backends")
        wire(remote=remote)
        result = watch.compare()
        assert result.status == "drift"
        assert result.fingerprint == watch.fingerprint(remote)

    @pytest.mark.parametrize(
        ("status", "kwargs"),
        [
            ("match", {}),
            ("no-baseline", {"baseline": None}),
            ("error", {"tag": False}),
        ],
    )
    def test_every_verdict_that_fetched_a_body_reports_it(self, watch, wire, status, kwargs):
        """Not only ``drift``.

        A row is cut *after* a maintainer reads a verdict, and the verdict a
        divergence first arrives in need not be the one they act on.
        """
        wire(**kwargs)
        result = watch.compare()
        assert result.status == status
        assert result.fingerprint == watch.fingerprint(RECIPE)

    @pytest.mark.parametrize(
        ("status", "exc"),
        [("unreachable", "RemoteUnreachableError"), ("missing", "RemoteMissingError")],
    )
    def test_a_verdict_that_fetched_nothing_reports_no_fingerprint(self, watch, wire, status, exc):
        """``unreachable`` and ``missing`` have no body to fingerprint.

        An empty string rather than a hash of nothing: no register row can
        carry it, so neither verdict can be accepted by accident.
        """
        wire(remote_exc=getattr(watch, exc)("boom"))
        result = watch.compare()
        assert result.status == status
        assert result.fingerprint == ""


class TestLocalization:
    """DRIFT-RULES Rule 2: name the element, not the fact of a difference."""

    def test_a_pin_names_its_package(self, watch):
        a = watch.comparable(RECIPE)
        b = watch.comparable(RECIPE.replace("- pyarrow >=14.0.0", "- pyarrow >=12.0.0"))
        assert "requirements.run_constraints[pyarrow]" in watch.differing_keys(a, b)

    def test_a_value_names_its_path(self, watch):
        a = watch.comparable(RECIPE)
        b = watch.comparable(RECIPE.replace('summary: "eight backends"', 'summary: "four backends"'))
        assert "about.summary" in watch.differing_keys(a, b)

    def test_a_comment_names_its_enclosing_block_not_the_key_above_it(self, watch):
        """The lines that differ in practice are as often comments as values.

        Naming the preceding sibling would point a reader at a key that did
        not change.
        """
        a = watch.comparable(RECIPE)
        b = watch.comparable(RECIPE.replace("    # a comment", "    # a different comment"))
        keys = watch.differing_keys(a, b)
        assert "requirements.run_constraints" in keys

    def test_identical_bodies_name_nothing(self, watch):
        assert watch.differing_keys(watch.comparable(RECIPE), watch.comparable(RECIPE)) == ()


class TestVersionParsing:
    def test_reads_the_context_version(self, watch):
        assert watch.remote_version(RECIPE) == "0.32.0"

    def test_a_recipe_with_no_context_version_reads_as_none(self, watch):
        assert watch.remote_version("package:\n  name: x\n") is None

    @pytest.mark.parametrize(
        ("shape", "text"),
        [
            ("blank line", 'context:\n\n  version: "0.32.0"\n'),
            ("column-0 comment", 'context:\n# a migrator touched this\n  version: "0.32.0"\n'),
            ("indented comment", 'context:\n  # set at release\n  version: "0.32.0"\n'),
            ("another key first", 'context:\n  name: remote-store\n  version: "0.32.0"\n'),
            ("trailing spaces", 'context:   \n  version: "0.32.0"\n'),
            # The two shapes that shipped green through two fix rounds, because
            # every case above is LF and every one has a bare `context:` line.
            ("crlf", 'context:\r\n  version: "0.32.0"\r\n'),
            ("comment on the marker line", 'context:  # set by the bot\n  version: "0.32.0"\n'),
            ("crlf and a marker comment", 'context: # bot\r\n  version: "0.32.0"\r\n'),
        ],
    )
    def test_the_version_survives_reformatting_of_the_block(self, watch, shape, text):
        """The published file is not ours to keep tidy.

        A conda-forge migrator, a rerender or a maintainer can reformat the
        block, and failing to read the version reports `error` -- which five
        artefacts define as a fault on **our** side. That inverts the split the
        status taxonomy exists for, so the parse has to tolerate anything YAML
        does.
        """
        assert watch.remote_version(text) == "0.32.0", shape

    def test_a_version_outside_the_context_block_is_still_not_read(self, watch):
        """Tolerating layout must not widen what counts as the version."""
        assert watch.remote_version('package:\n  version: "9.9.9"\ncontext:\n  other: 1\n') is None

    def test_a_version_elsewhere_is_not_the_context_one(self, watch):
        """``package.version`` is a template reference, not the source of truth."""
        assert watch.remote_version('package:\n  version: "9.9.9"\n') is None

    @pytest.mark.parametrize(
        ("tag", "expected"), [("v0.32.0", (0, 32, 0)), ("v1.2", (1, 2)), ("0.32.0", None), ("vX", None)]
    )
    def test_version_tuples(self, watch, tag, expected):
        assert watch._version_tuple(tag) == expected


class TestNewestTag:
    """The real body, which every status test stubs away.

    `wire` replaces `newest_tag` wholesale, so its parsing and max-selection
    never ran -- and "by version order rather than by push order" is the
    load-bearing half of its docstring.
    """

    def _gh_returning(self, watch, monkeypatch, stdout, returncode=0):
        import subprocess

        def fake(args, **_kw):
            return subprocess.CompletedProcess(args=args, returncode=returncode, stdout=stdout, stderr="")

        monkeypatch.setattr(watch.subprocess, "run", fake)

    def test_picks_by_version_order_not_push_order(self, watch, monkeypatch):
        # `gh api .../tags` returns push order; v0.9.0 sorts above v0.10.0 as a
        # string and below it as a version, so a lexical max would pick wrong.
        self._gh_returning(watch, monkeypatch, "v0.9.0\nv0.32.0\nv0.10.0\nv0.31.0\n")
        assert watch.newest_tag() == "v0.32.0"

    def test_ignores_tags_that_are_not_versions(self, watch, monkeypatch):
        self._gh_returning(watch, monkeypatch, "nightly\nv0.31.0\nrelease-candidate\nvX.Y\n")
        assert watch.newest_tag() == "v0.31.0"

    def test_a_failed_call_yields_none(self, watch, monkeypatch):
        self._gh_returning(watch, monkeypatch, "", returncode=1)
        assert watch.newest_tag() is None

    def test_no_version_tags_yields_none(self, watch, monkeypatch):
        self._gh_returning(watch, monkeypatch, "nightly\nmain\n")
        assert watch.newest_tag() is None


class TestStatuses:
    def test_identical_copies_match(self, watch, wire):
        wire()
        assert watch.compare().status == "match"

    def test_an_owned_field_alone_still_matches(self, watch, wire):
        wire(remote=RECIPE.replace("number: 0", "number: 4"))
        assert watch.compare().status == "match"

    def test_a_real_difference_is_drift_and_carries_its_evidence(self, watch, wire):
        wire(remote=RECIPE.replace("eight backends", "four backends"))
        result = watch.compare()
        assert result.status == "drift"
        assert "about.summary" in result.keys
        assert "four backends" in result.diff

    def test_a_copy_out_made_after_the_tag_is_not_drift(self, watch, wire, tmp_path):
        """The release procedure puts a gap between the tag and the copy-out.

        ``source.sha256`` lands in it by design, and anything else merged in
        that window rides out with the copy. Without this status such a
        copy-out reads as drift for a whole release cycle.
        """
        newer = RECIPE.replace("- paramiko >=3.1", "- paramiko >=3.4")
        local = tmp_path / "local.yaml"
        local.write_text(newer, encoding="utf-8")
        wire(remote=newer, baseline=RECIPE)
        assert watch.compare(local_baseline=local).status == "ahead-of-tag"

    def test_a_tag_with_no_committed_copy_is_no_baseline(self, watch, wire):
        wire(baseline=None)
        result = watch.compare()
        assert result.status == "no-baseline"
        assert result.diff == ""

    def test_a_version_this_repo_never_tagged_is_our_error(self, watch, wire):
        """Never folded into ``unreachable``.

        A tag that will not resolve is a broken watch or a feedstock on a
        version that was never released here; both are this side's, and both
        must hold the issue open rather than sit in the bucket reserved for
        the other repository being down.
        """
        wire(tag=False)
        assert watch.compare().status == "error"

    def test_a_404_on_the_published_recipe_is_missing(self, watch, wire):
        wire(remote_exc=watch.RemoteMissingError("404"))
        assert watch.compare().status == "missing"

    def test_a_failed_fetch_is_unreachable(self, watch, wire):
        wire(remote_exc=watch.RemoteUnreachableError("connection reset"))
        assert watch.compare().status == "unreachable"

    def test_an_unparseable_remote_is_our_error(self, watch, wire):
        wire(remote="not a recipe at all\n")
        result = watch.compare()
        assert result.status == "error"
        assert "context.version" in result.reason

    def test_compare_never_raises(self, watch, monkeypatch):
        """The workflow step's red/green must mean "did this script run", not "what did it find"."""

        def boom(*_a, **_k):
            raise OSError("network stack on fire")

        monkeypatch.setattr(watch.urllib.request, "urlopen", boom)
        assert watch.compare().status == "unreachable"

    def test_a_truncated_response_body_is_unreachable(self, watch, monkeypatch):
        """`http.client.HTTPException` is not an `OSError`.

        `IncompleteRead` is raised while reading the body, after the request
        succeeded, so the `OSError` arm does not cover it and it would escape
        `compare()` as a traceback.
        """

        def truncated(*_a, **_k):
            raise http.client.IncompleteRead(b"half a recipe")

        monkeypatch.setattr(watch.urllib.request, "urlopen", truncated)
        assert watch.compare().status == "unreachable"

    def test_an_absent_gh_binary_does_not_escape(self, watch, monkeypatch):
        """`check=False` suppresses a non-zero exit, not a failure to exec.

        `tag_exists` runs inside `compare()` with no guard of its own, so a
        `FileNotFoundError` from the exec would propagate out of a function
        whose contract is that it never raises -- and out of a workflow step
        that precedes the issue update.

        Only the fetch is stubbed here, deliberately. Stubbing `tag_exists` as
        the other status tests do would route around `_gh` entirely, and the
        first version of this test did exactly that and passed against the
        unfixed code.
        """
        monkeypatch.setattr(watch, "fetch_remote", lambda url=watch.FEEDSTOCK_URL: RECIPE)
        real = watch.subprocess.run

        def no_gh(args, **kw):
            if args and args[0] == "gh":
                raise FileNotFoundError(2, "No such file or directory: 'gh'")
            return real(args, **kw)

        monkeypatch.setattr(watch.subprocess, "run", no_gh)
        result = watch.compare()
        assert result.status == "error"
        assert "did not run" in result.reason

    def test_a_failed_blob_lookup_is_not_reported_as_no_baseline(self, watch, monkeypatch):
        """The sibling of the `tag_exists` split, and the same conflation.

        `baseline_at` returning `None` means "this tag carries no copy", which
        is normal operation and holds nothing. A `gh` that never ran must not
        borrow that answer.

        Breaking `subprocess.run` for the *contents* call alone is what makes
        the real `baseline_at` raise; an earlier version of this test stubbed
        `baseline_at` itself and passed against the unfixed code.
        """
        monkeypatch.setattr(watch, "fetch_remote", lambda url=watch.FEEDSTOCK_URL: RECIPE)
        monkeypatch.setattr(watch, "newest_tag", lambda *_a, **_k: "v0.32.0")
        monkeypatch.setattr(watch, "tag_exists", lambda *_a, **_k: True)
        real = watch.subprocess.run

        def gh_dies_on_contents(args, **kw):
            if args and args[0] == "gh" and any("contents" in str(a) for a in args):
                raise FileNotFoundError(2, "No such file or directory: 'gh'")
            return real(args, **kw)

        monkeypatch.setattr(watch.subprocess, "run", gh_dies_on_contents)
        result = watch.compare()
        assert result.status == "error"
        assert "says nothing about the feedstock" in result.reason

    def test_a_tag_that_does_not_exist_reads_differently_from_a_broken_gh(self, watch, monkeypatch):
        """DRIFT-RULES Rule 2: the two send a maintainer to different repositories.

        `gh` exits non-zero for both, so without the split a broken workflow
        reports that conda-forge is serving a version this project never
        released.
        """
        monkeypatch.setattr(watch, "fetch_remote", lambda url=watch.FEEDSTOCK_URL: RECIPE)
        monkeypatch.setattr(watch, "newest_tag", lambda *_a, **_k: "v0.32.0")
        monkeypatch.setattr(watch, "tag_exists", lambda *_a, **_k: False)
        absent_tag = watch.compare()
        monkeypatch.setattr(watch, "tag_exists", lambda *_a, **_k: None)
        broken_gh = watch.compare()
        assert absent_tag.status == broken_gh.status == "error"
        assert "no v0.32.0 tag" in absent_tag.reason
        assert "look at this workflow, not at conda-forge" in broken_gh.reason


class TestTrailing:
    def test_a_feedstock_on_the_newest_tag_is_not_trailing(self, watch, wire):
        wire(newest="v0.32.0")
        assert watch.compare().trailing is False

    def test_a_feedstock_a_release_behind_is_trailing_but_can_still_match(self, watch, wire):
        """Orthogonal to the comparison, which is why it is a field and not a status.

        A channel a release behind still carries exactly what this repo
        published for the version it is on. Collapsing the two would make the
        commonest healthy state unrepresentable.
        """
        wire(newest="v0.33.0")
        result = watch.compare()
        assert result.trailing is True
        assert result.status == "match"

    def test_an_unavailable_tag_list_does_not_invent_trailing(self, watch, wire):
        wire(newest=None)
        assert watch.compare().trailing is False


class TestMain:
    def test_writes_a_json_report(self, watch, wire, tmp_path, capsys):
        wire()
        out = tmp_path / "nested" / "feedstock-report.json"
        assert watch.main(["--out", str(out)]) == 0
        payload = json.loads(out.read_text(encoding="utf-8"))
        assert payload["status"] == "match"
        assert payload["remote_version"] == "0.32.0"

    def test_leaves_no_temporary_behind(self, watch, wire, tmp_path):
        wire()
        out = tmp_path / "feedstock-report.json"
        watch.main(["--out", str(out)])
        assert [p.name for p in tmp_path.iterdir()] == ["feedstock-report.json"]

    def test_a_finding_still_exits_zero(self, watch, wire, tmp_path):
        """Advisory: the artefact is in a repository no PR here can fix."""
        wire(remote=RECIPE.replace("eight backends", "four backends"))
        assert watch.main(["--out", str(tmp_path / "f.json")]) == 0

    def test_an_unwritable_destination_exits_one(self, watch, wire, tmp_path):
        """The one non-zero exit, and it is never a finding about the feedstock."""
        wire()
        blocker = tmp_path / "blocker"
        blocker.write_text("not a directory", encoding="utf-8")
        assert watch.main(["--out", str(blocker / "f.json")]) == 1

    def test_stdout_carries_the_report_without_out(self, watch, wire, capsys):
        wire()
        assert watch.main([]) == 0
        assert json.loads(capsys.readouterr().out)["status"] == "match"
