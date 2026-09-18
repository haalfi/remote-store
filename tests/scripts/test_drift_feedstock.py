"""Tests for scripts/drift_feedstock.py.

Every network call is mocked. What matters here is the taxonomy: the script's
whole design claim is that a failure of ours and a failure of the feedstock's
are different answers, so most of these pin which status a given failure
produces rather than that a failure was noticed.
"""

from __future__ import annotations

import json
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

    def test_a_real_change_is_not_excluded(self, watch):
        assert watch.comparable(RECIPE) != watch.comparable(RECIPE.replace("eight backends", "four backends"))


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

    def test_a_version_elsewhere_is_not_the_context_one(self, watch):
        """``package.version`` is a template reference, not the source of truth."""
        assert watch.remote_version('package:\n  version: "9.9.9"\n') is None

    @pytest.mark.parametrize(
        ("tag", "expected"), [("v0.32.0", (0, 32, 0)), ("v1.2", (1, 2)), ("0.32.0", None), ("vX", None)]
    )
    def test_version_tuples(self, watch, tag, expected):
        assert watch._version_tuple(tag) == expected


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
