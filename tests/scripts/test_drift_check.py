"""Tests for scripts/drift_check.py (ID-182).

The script orchestrates pip resolution in a fresh venv (slow, network) and
docs rendering (cheap, pure). The unit tests below cover the pure helpers
that gate correctness of the drift report — the bucketing heuristic, the
freeze parser, the recursive direct-dependency walk, the lock-file
parser, idempotence of `render_docs`, and the no-op-refresh guard in
`write_lock`. ``resolve_extra`` itself is not unit-tested (it spawns a
venv and hits PyPI); the workflow's end-to-end run is its acceptance test.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPTS = ROOT / "scripts"


@pytest.fixture(scope="module")
def drift_check():
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    import drift_check

    return drift_check


class TestIsPrerelease:
    """``_is_prerelease`` decides whether a resolved version goes into the
    informational pre-release bucket rather than the loud stable-drift
    bucket. False negatives would let a 1.0.dev3 look like a GA break;
    false positives would silence a real stable upgrade. The regex covers
    PEP 440's pre / dev / rc / alpha / beta markers.
    """

    @pytest.mark.parametrize(
        "version",
        [
            "1.0.dev3",
            "1.0.dev0",
            "1.0a1",
            "1.0b2",
            "1.0rc1",
            "1.0.0.alpha1",
            "1.0.0.beta2",
            "1.0.pre1",
            "2.0.0rc3",
            "1.0.0RC1",  # case-insensitive
            "1.0.0.DEV0",
        ],
    )
    def test_classified_as_prerelease(self, drift_check, version):
        assert drift_check._is_prerelease(version) is True

    @pytest.mark.parametrize(
        "version",
        [
            "1.0.0",
            "0.27.0",
            "2026.5.20",
            "1.0.post1",
            "1.0.0+local",
            "1.0",
            "0.1.2.3",
        ],
    )
    def test_classified_as_stable(self, drift_check, version):
        assert drift_check._is_prerelease(version) is False


class TestParseFreeze:
    """``_parse_freeze`` is the gate between ``pip freeze`` output and the
    structured baseline. Any silent skip or accidental match would either
    flag a non-drift as drift, or hide a real upgrade. The bag of rules
    is small enough to enumerate.
    """

    def test_parses_simple_pin(self, drift_check):
        assert drift_check._parse_freeze("certifi==2026.5.20\n") == {"certifi": "2026.5.20"}

    def test_strips_remote_store_itself(self, drift_check):
        # The project under test is not a transitive dep of any extra.
        result = drift_check._parse_freeze("remote-store==0.25.0\nhttpx==0.27.0\n")
        assert "remote-store" not in result
        assert result == {"httpx": "0.27.0"}

    def test_strips_venv_bootstrap(self, drift_check):
        # pip / setuptools / wheel always appear in `pip freeze --all` and
        # are not extra dependencies.
        text = "pip==24.0\nsetuptools==79.0.1\nwheel==0.45.0\nhttpx==0.27.0\n"
        assert drift_check._parse_freeze(text) == {"httpx": "0.27.0"}

    def test_skips_editable_installs(self, drift_check):
        text = "-e git+https://example.com/repo.git#egg=foo\nhttpx==0.27.0\n"
        assert drift_check._parse_freeze(text) == {"httpx": "0.27.0"}

    def test_skips_direct_url_specs(self, drift_check):
        text = "foo @ https://example.com/foo.whl\nhttpx==0.27.0\n"
        assert drift_check._parse_freeze(text) == {"httpx": "0.27.0"}

    def test_skips_comments_and_blanks(self, drift_check):
        text = "# this is a comment\n\nhttpx==0.27.0\n   \n"
        assert drift_check._parse_freeze(text) == {"httpx": "0.27.0"}

    def test_normalises_package_names(self, drift_check):
        # PyPI normalises underscores to hyphens, lowercases the name.
        text = "PyYAML==6.0.1\nazure_storage_file_datalake==12.16.0\n"
        result = drift_check._parse_freeze(text)
        assert "pyyaml" in result
        assert "azure-storage-file-datalake" in result


class TestLockHeaderParsing:
    """Round-trip of write_lock -> read_lock against a stub and a populated
    file. The drift report keys off captured/python; a header-parse
    regression would lie about either field.
    """

    def test_stub_lock_is_empty(self, drift_check, tmp_path, monkeypatch):
        monkeypatch.setattr(drift_check, "LOCK_DIR", tmp_path)
        stub = tmp_path / "httpx.txt"
        stub.write_text(
            "# extra: httpx\n# python:\n# captured:\n"
            "# Stub baseline — first population pending.\n"
            "# Run: hatch run drift-check refresh-baseline httpx\n",
            encoding="utf-8",
        )
        lock = drift_check.read_lock("httpx")
        assert lock.is_empty is True
        assert lock.packages == {}

    def test_populated_lock_parses_header_and_pins(self, drift_check, tmp_path, monkeypatch):
        monkeypatch.setattr(drift_check, "LOCK_DIR", tmp_path)
        (tmp_path / "httpx.txt").write_text(
            "# extra: httpx\n# python: 3.13\n# captured: 2026-05-24\n"
            "# Regenerate with: hatch run drift-check refresh-baseline httpx\n"
            "\n"
            "certifi==2026.5.20\n"
            "httpx==0.27.0\n",
            encoding="utf-8",
        )
        lock = drift_check.read_lock("httpx")
        assert lock.is_empty is False
        assert lock.python == "3.13"
        assert lock.captured == "2026-05-24"
        assert lock.packages == {"certifi": "2026.5.20", "httpx": "0.27.0"}

    def test_missing_lock_returns_empty(self, drift_check, tmp_path, monkeypatch):
        monkeypatch.setattr(drift_check, "LOCK_DIR", tmp_path)
        lock = drift_check.read_lock("nonexistent")
        assert lock.is_empty is True


class TestWriteLockNoChurnOnNoOp:
    """The `captured:` date must not change when a refresh resolves the same
    package set on the same Python — otherwise repeated refreshes churn
    the lock file (and through render_docs, the docs page) for no reason.
    """

    def test_captured_preserved_when_packages_unchanged(self, drift_check, tmp_path, monkeypatch):
        monkeypatch.setattr(drift_check, "LOCK_DIR", tmp_path)
        pyver = f"{sys.version_info.major}.{sys.version_info.minor}"
        (tmp_path / "httpx.txt").write_text(
            f"# extra: httpx\n# python: {pyver}\n# captured: 2020-01-01\n"
            "# Regenerate with: hatch run drift-check refresh-baseline httpx\n"
            "\n"
            "httpx==0.27.0\n",
            encoding="utf-8",
        )
        drift_check.write_lock("httpx", {"httpx": "0.27.0"})
        lock = drift_check.read_lock("httpx")
        assert lock.captured == "2020-01-01"

    def test_captured_refreshed_when_packages_change(self, drift_check, tmp_path, monkeypatch):
        monkeypatch.setattr(drift_check, "LOCK_DIR", tmp_path)
        pyver = f"{sys.version_info.major}.{sys.version_info.minor}"
        (tmp_path / "httpx.txt").write_text(
            f"# extra: httpx\n# python: {pyver}\n# captured: 2020-01-01\n"
            "# Regenerate with: hatch run drift-check refresh-baseline httpx\n"
            "\n"
            "httpx==0.27.0\n",
            encoding="utf-8",
        )
        drift_check.write_lock("httpx", {"httpx": "0.28.0"})
        lock = drift_check.read_lock("httpx")
        assert lock.captured != "2020-01-01"
        assert lock.packages == {"httpx": "0.28.0"}


class TestDirectDepsFor:
    """``_direct_deps_for`` walks `[project.optional-dependencies]` and
    expands ``remote-store[<other>]`` references recursively. The docs
    page uses its result to project full transitive locks down to the
    top-level packages users actually care about.
    """

    def test_top_level_packages_extracted(self, drift_check):
        # From pyproject.toml's [sftp] = ["paramiko>=3.1", "tenacity>=8.0.1"].
        deps = drift_check._direct_deps_for("sftp")
        assert "paramiko" in deps
        assert "tenacity" in deps

    def test_normalises_package_names(self, drift_check):
        # azure-storage-file-datalake / azure-identity are both declared.
        deps = drift_check._direct_deps_for("azure")
        assert "azure-storage-file-datalake" in deps
        assert "azure-identity" in deps

    def test_strips_version_specifiers(self, drift_check):
        deps = drift_check._direct_deps_for("sftp")
        # Names only; no >= / == suffixes.
        for dep in deps:
            assert ">" not in dep
            assert "=" not in dep
            assert "<" not in dep


class TestDirectRequirementsFor:
    """``_direct_requirements_for`` keeps the specifier ``_direct_deps_for``
    discards. The docs page publishes the declared range beside the resolved
    version, and a package name alone cannot answer "what does this require at
    minimum?" — which is the question the page was previously silent on.
    """

    def test_keeps_the_version_specifier(self, drift_check):
        # From pyproject.toml's [sftp] = ["paramiko>=3.1", "tenacity>=8.0.1"].
        reqs = drift_check._direct_requirements_for("sftp")
        assert reqs["paramiko"] == ">=3.1"
        assert reqs["tenacity"] == ">=8.0.1"

    def test_keeps_a_ceiling_alongside_the_floor(self, drift_check):
        # [graph] caps httpx: the ceiling is the rarer half of a range and the
        # one a reader is most surprised by, so it must survive to the page.
        assert drift_check._direct_requirements_for("graph")["httpx"] == ">=0.24.0,<1.0"

    def test_keeps_the_environment_marker(self, drift_check):
        # [toml] is marker-gated; the page renders the marker as the reason it
        # carries no row, so the marker has to reach the caller intact.
        assert drift_check._direct_requirements_for("toml")["tomli"] == ">=1.1.0; python_version < '3.11'"

    def test_unions_a_package_declared_twice(self, drift_check):
        # [dev] reaches pyarrow through both [s3-pyarrow] (>=14.0.0) and
        # [sql-query] (>=12.0.0) — NOT [arrow], which [dev] does not aggregate.
        # Keeping one silently would hide that the two declarations disagree.
        pyarrow = drift_check._direct_requirements_for("dev")["pyarrow"]
        assert ">=14.0.0" in pyarrow
        assert ">=12.0.0" in pyarrow

    def test_a_package_declared_twice_identically_is_not_doubled(self, drift_check):
        # [graph] and [httpx] declare the identical multi-clause range, and
        # [dev] reaches both. Comparing a candidate against the accumulated
        # string split on `,` could never match a declaration containing a
        # comma, so this returned `>=0.24.0,<1.0,>=0.24.0,<1.0` — neither a
        # visible duplicate nor a range.
        assert drift_check._direct_requirements_for("dev")["httpx"] == ">=0.24.0,<1.0"

    def test_direct_deps_for_is_its_key_set(self, drift_check):
        for extra in drift_check.list_extras():
            assert drift_check._direct_deps_for(extra) == set(drift_check._direct_requirements_for(extra))


class TestExcludedExtras:
    """The excluded set is derived, not hand-kept — but only half of it is
    derived from an artifact that governs it.
    """

    def test_aggregate_set_equals_the_install_docs_exclusions(self, drift_check):
        # `gen_features._EXCLUDE_EXTRAS` answers a different question — which
        # extras the README's install list omits — and the two sets have always
        # been equal. Asserted rather than imported: that one is a presentation
        # list, so importing it would let a docs decision silently shrink the
        # drift matrix. This test is what makes a divergence loud instead.
        import gen_features

        assert drift_check._AGGREGATE_EXTRAS == gen_features._EXCLUDE_EXTRAS

    def test_marker_gated_extras_are_derived(self, drift_check):
        # Derived from the markers themselves, so a new marker-gated extra
        # excludes itself rather than waiting for someone to list it.
        assert drift_check._marker_gated_extras() == frozenset({"toml", "mutate"})

    def test_union_is_what_the_guard_skips(self, drift_check):
        assert drift_check.excluded_extras() == frozenset({"dev", "docs", "bench", "toml", "mutate"})


class TestMinPython:
    """The floor lane runs on the oldest supported interpreter, and the docs
    page names it. Both read it from ``requires-python`` so the minimum is not
    spelled a fourth time by hand.
    """

    def test_derives_the_lower_bound(self, drift_check):
        assert drift_check.min_python() == "3.10"

    def test_matches_the_lowest_python_classifier(self, drift_check):
        # The classifiers are the other published statement of the same fact;
        # a disagreement between them is the drift this derivation prevents.
        classifiers = drift_check._load_pyproject()["project"]["classifiers"]
        versions = sorted(
            tuple(int(p) for p in c.rsplit(" ", 1)[1].split("."))
            for c in classifiers
            if c.startswith("Programming Language :: Python :: 3.")
        )
        assert drift_check.min_python() == ".".join(str(p) for p in versions[0])

    def test_rejects_a_specifier_with_no_lower_bound(self, drift_check, monkeypatch):
        monkeypatch.setattr(drift_check, "_load_pyproject", lambda: {"project": {"requires-python": "<4"}})
        with pytest.raises(ValueError, match="lower bound"):
            drift_check.min_python()


class TestFloorReport:
    """``floor_report`` projects a resolution onto what the extra declares."""

    def test_projects_onto_declared_packages_only(self, drift_check):
        resolved = {"paramiko": "3.1.0", "tenacity": "8.0.1", "bcrypt": "5.0.0", "pynacl": "1.6.2"}
        report = drift_check.floor_report("sftp", resolved)
        # bcrypt and pynacl are transitive: `lowest-direct` leaves them newest,
        # so they are not a claim this lane makes.
        assert report["floor"] == {"paramiko": "3.1.0", "tenacity": "8.0.1"}

    def test_declares_its_lane_and_status(self, drift_check):
        report = drift_check.floor_report("yaml", {"pyyaml": "5.1"})
        assert report["lane"] == "floor"
        assert report["status"] == "resolved"

    def test_omits_a_declared_package_the_resolution_lacks(self, drift_check):
        # Rather than inventing a version. A missing row is readable; a wrong
        # one is not.
        assert drift_check.floor_report("sftp", {"paramiko": "3.1.0"})["floor"] == {"paramiko": "3.1.0"}


class TestUvInvocation:
    """``_uv`` and ``resolve_floor`` decide *which interpreter* the floors are
    installed into. Getting that wrong is the one failure here that is green
    and wrong rather than red, on a lane that runs weekly.
    """

    def test_strips_ambient_target_selection(self, drift_check, monkeypatch):
        # `setup-uv` is what lets other workflows run a bare `uv pip install`
        # against setup-python's interpreter with no venv in sight. Inheriting
        # that would install the floor into the runner Python — the same one the
        # smoke then uses — and the lane would pass having tested nothing.
        seen = {}

        def _fake_run(argv, **kwargs):
            seen["env"] = kwargs["env"]
            return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

        monkeypatch.setenv("UV_SYSTEM_PYTHON", "1")
        monkeypatch.setenv("VIRTUAL_ENV", "/somewhere/else")
        monkeypatch.setattr(drift_check.subprocess, "run", _fake_run)
        drift_check._uv(["pip", "freeze"])
        assert "UV_SYSTEM_PYTHON" not in seen["env"]
        assert "VIRTUAL_ENV" not in seen["env"]

    def test_surfaces_stderr_on_failure(self, drift_check, monkeypatch, capsys):
        # The stderr of a failed resolve IS the finding — it names the package
        # and why it would not install.
        def _fake_run(argv, **kwargs):
            raise subprocess.CalledProcessError(1, argv, stderr="no wheel for aiohttp 3.0.0")

        monkeypatch.setattr(drift_check.subprocess, "run", _fake_run)
        with pytest.raises(subprocess.CalledProcessError):
            drift_check._uv(["pip", "install", "."])
        assert "no wheel for aiohttp 3.0.0" in capsys.readouterr().err

    def test_resolve_floor_pins_the_interpreter_and_the_resolution(self, drift_check, monkeypatch):
        calls: list[list[str]] = []

        def _fake_uv(args, *, capture=False):
            calls.append(args)
            return "pyyaml==5.1\nremote-store @ file:///checkout\n" if capture else ""

        monkeypatch.setattr(drift_check, "_uv", _fake_uv)
        assert drift_check.resolve_floor("yaml") == {"pyyaml": "5.1"}

        venv_call, install_call, freeze_call = calls
        assert venv_call[:2] == ["venv", "--python"]
        # `lowest-direct`, never `lowest`: transitives stay newest, because the
        # claim under test is the one this project declares.
        assert "--resolution" in install_call
        assert install_call[install_call.index("--resolution") + 1] == "lowest-direct"
        assert ".[yaml]" in install_call
        # Every call names its target explicitly, so no ambient setting decides.
        for call in (install_call, freeze_call):
            assert "--python" in call


class TestFloorCommand:
    """``floor --out`` must not crash the leg: a resolve that fails IS the
    finding, and it has to reach the report job as data.
    """

    def test_a_failed_resolve_becomes_a_report_not_a_crash(self, drift_check, monkeypatch, tmp_path):
        def _boom(extra):
            raise subprocess.CalledProcessError(1, ["uv"], stderr="no wheel for aiohttp 3.0.0")

        monkeypatch.setattr(drift_check, "resolve_floor", _boom)
        out = tmp_path / "azure.json"
        assert drift_check.main(["floor", "azure", "--out", str(out)]) == 0

        report = json.loads(out.read_text(encoding="utf-8"))
        assert report["status"] == "error"
        assert report["lane"] == "floor"
        assert "no wheel for aiohttp 3.0.0" in report["reason"]

    def test_no_freeze_is_written_when_the_resolve_failed(self, drift_check, monkeypatch, tmp_path):
        # An empty constraints file would make the smoke run unpinned against a
        # set nothing recorded; the composite action reads its absence as
        # "skipped", which is the honest verdict.
        monkeypatch.setattr(drift_check, "resolve_floor", lambda extra: (_ for _ in ()).throw(RuntimeError("nope")))
        freeze = tmp_path / "azure.txt"
        drift_check.main(["floor", "azure", "--out", str(tmp_path / "azure.json"), "--emit-freeze", str(freeze)])
        assert not freeze.exists()

    def test_a_resolve_error_without_out_still_raises(self, drift_check, monkeypatch):
        # Interactively there is no report to write, so the error must surface.
        monkeypatch.setattr(drift_check, "resolve_floor", lambda extra: (_ for _ in ()).throw(RuntimeError("nope")))
        with pytest.raises(RuntimeError, match="nope"):
            drift_check.main(["floor", "azure"])


class TestSmokeReach:
    """The page publishes how far each extra's smoke reaches, derived from the
    one mapping the workflow dispatches on.
    """

    def test_import_only_targets_say_so(self, drift_check):
        assert drift_check._smoke_reach("otel") == "import of `remote_store.ext.otel` only"

    def test_pytest_targets_render_their_paths(self, drift_check):
        assert drift_check._smoke_reach("yaml") == "`tests/ext/test_yaml.py`"

    def test_selector_flags_never_reach_the_page(self, drift_check):
        # drift_smoke_map's [s3] entry carries `-k s3 and not s3_pyarrow and not
        # s3_boto3`, and [sftp]'s carries `-o addopts=`. Those are source facts
        # about the harness; a published reference page is the wrong home for
        # them, and the parked-PoC exclusion would read as a product statement.
        for extra in ("s3", "sftp"):
            reach = drift_check._smoke_reach(extra)
            assert "-k" not in reach
            assert "-o" not in reach
            assert "addopts" not in reach

    def test_every_tracked_extra_has_a_reach(self, drift_check):
        for extra in drift_check.list_extras():
            assert drift_check._smoke_reach(extra)


class TestRenderDocsIdempotent:
    """`render_docs` must produce byte-identical output across days when
    inputs are unchanged. The `--check` wiring in preflight depends on
    this: a date-stamp in the output would break `hatch run all` the day
    after the page was last regenerated.
    """

    def test_no_date_interpolation_in_pending_state(self, drift_check, tmp_path, monkeypatch):
        # All-stub lock dir: triggers the "first population pending" footer
        # — the spot that previously interpolated today's date.
        monkeypatch.setattr(drift_check, "LOCK_DIR", tmp_path)
        for extra in drift_check.list_extras():
            (tmp_path / f"{extra}.txt").write_text(
                f"# extra: {extra}\n# python:\n# captured:\n",
                encoding="utf-8",
            )
        rendered = drift_check.render_docs()
        # No ISO date in the output (pattern YYYY-MM-DD).
        import re

        assert re.search(r"\b\d{4}-\d{2}-\d{2}\b", rendered) is None

    def test_stable_across_repeated_calls(self, drift_check, tmp_path, monkeypatch):
        monkeypatch.setattr(drift_check, "LOCK_DIR", tmp_path)
        for extra in drift_check.list_extras():
            (tmp_path / f"{extra}.txt").write_text(
                f"# extra: {extra}\n# python:\n# captured:\n",
                encoding="utf-8",
            )
        assert drift_check.render_docs() == drift_check.render_docs()


class TestRenderDocsContent:
    """What the page must say, beyond being stable. Each assertion below is a
    question a reader brought to the page and could not previously answer.
    """

    def test_publishes_the_declared_range_beside_the_resolved_one(self, drift_check):
        rendered = drift_check.render_docs()
        assert "| Package | Declared | Tested up to |" in rendered
        # The floor a resolver is actually held to, for an extra a user installs.
        assert "`>=3.1`" in rendered

    def test_names_the_interpreter_the_floor_lane_runs_on(self, drift_check):
        assert f"Python {drift_check.min_python()}" in drift_check.render_docs()

    def test_names_every_extra_it_does_not_cover(self, drift_check):
        rendered = drift_check.render_docs()
        assert "## Extras this page does not cover" in rendered
        # `[toml]` is in the README's install list and has no row above, which
        # reads as "nothing changed" rather than "never checked" unless the page
        # says so where the row would have been.
        uncovered = drift_check._marker_gated_extras() - drift_check._AGGREGATE_EXTRAS
        for extra in uncovered:
            assert f"`[{extra}]`" in rendered

    def test_does_not_list_a_developer_aggregate_as_uncovered(self, drift_check):
        # `dev`, `docs` and `bench` never reach a user's environment; naming
        # them on a user-facing page would be noise, and it is the reason the
        # two exclusion halves are kept apart rather than merged.
        rendered = drift_check.render_docs().rsplit("## Extras this page does not cover", 1)[-1]
        for aggregate in ("`[dev]`", "`[docs]`", "`[bench]`"):
            assert aggregate not in rendered

    def test_states_each_extras_smoke_reach(self, drift_check):
        rendered = drift_check.render_docs()
        assert "_Smoke:_" in rendered
        # An import-only target is weaker evidence than a test suite, and the
        # page is where a reader can see which one backs a given row.
        assert "import of `remote_store.ext.otel` only" in rendered

    def test_carries_no_tracker_reference(self, drift_check):
        # The generated page is published; `check_no_tracker_refs.py` gates it,
        # and a leak would surface as a lint failure on the output rather than
        # on the template that caused it.
        import re as _re

        assert _re.search(r"\b[A-Z][A-Z0-9-]*-\d+\b", drift_check.render_docs()) is None


class TestListExtras:
    """The list of extras drives the drift matrix in the workflow. Anything
    in `[project.optional-dependencies]` that is not in the dev/build
    aggregates or marker-gated must appear; nothing else may.
    """

    def test_includes_every_backend_extra(self, drift_check):
        extras = drift_check.list_extras()
        for backend in ("s3", "s3-pyarrow", "azure", "sftp", "sql"):
            assert backend in extras

    def test_excludes_dev_aggregates(self, drift_check):
        extras = drift_check.list_extras()
        for excluded in ("dev", "docs", "bench"):
            assert excluded not in extras

    def test_excludes_marker_gated_toml(self, drift_check):
        # `toml` is gated to Python <3.11; resolution is python-version
        # dependent in a way that breaks the lock model. Drift guard skips.
        assert "toml" not in drift_check.list_extras()

    def test_excludes_dev_tooling_mutate(self, drift_check):
        # `mutate` carries the pytest-gremlins pin — a dev/CI test tool, not a
        # runtime dependency, and marker-gated to py>=3.11. Excluded for the
        # same reasons as the dev aggregates and `toml` (BUG-215).
        assert "mutate" not in drift_check.list_extras()

    def test_returns_sorted(self, drift_check):
        extras = drift_check.list_extras()
        assert extras == sorted(extras)


class TestDiffOutMode:
    """``diff --out PATH`` writes atomically (tempfile + os.replace) so a
    script-internal failure cannot leave a truncated JSON file under the
    artefact path. On an unrecoverable ``resolve_extra`` error the script
    writes a synthetic ``status: error`` report rather than exiting
    non-zero, so one extra's PyPI flake doesn't mask drift on the others.
    """

    def test_synthetic_error_report_written_on_resolve_failure(self, drift_check, tmp_path, monkeypatch):
        # Force resolve_extra to fail.
        def boom(_extra: str) -> dict[str, str]:
            raise RuntimeError("simulated PyPI 500")

        monkeypatch.setattr(drift_check, "resolve_extra", boom)
        out = tmp_path / "httpx.json"
        rc = drift_check.main(["diff", "httpx", "--out", str(out)])
        assert rc == 0  # Synthetic report path must not propagate the error.
        import json

        report = json.loads(out.read_text(encoding="utf-8"))
        assert report["status"] == "error"
        assert report["extra"] == "httpx"
        assert "simulated PyPI 500" in report["reason"]

    def test_atomic_write_leaves_no_temp_files(self, drift_check, tmp_path, monkeypatch):
        monkeypatch.setattr(drift_check, "LOCK_DIR", tmp_path / "locks")
        (tmp_path / "locks").mkdir()
        # Stub baseline -> needs_refresh -> still writes a valid report.
        (tmp_path / "locks" / "httpx.txt").write_text("# extra: httpx\n# python:\n# captured:\n", encoding="utf-8")

        def fake_resolve(_extra: str) -> dict[str, str]:
            return {"httpx": "0.27.0"}

        monkeypatch.setattr(drift_check, "resolve_extra", fake_resolve)
        out = tmp_path / "reports" / "httpx.json"
        drift_check.main(["diff", "httpx", "--out", str(out)])
        # Only the final file should exist; no .tmp leftover.
        siblings = sorted(p.name for p in out.parent.iterdir())
        assert siblings == ["httpx.json"]

    def test_stdout_mode_propagates_errors(self, drift_check, monkeypatch, capsys):
        # Without --out, errors must surface so the developer sees them.
        def boom(_extra: str) -> dict[str, str]:
            raise RuntimeError("loud failure")

        monkeypatch.setattr(drift_check, "resolve_extra", boom)
        with pytest.raises(RuntimeError, match="loud failure"):
            drift_check.main(["diff", "httpx"])


class TestEmitFreeze:
    """``diff --emit-freeze PATH`` writes the single resolved freeze so the
    smoke and the uploaded candidate baseline pin against exactly what the
    report was computed from (ID-231). Body must be a sorted ``name==version``
    block — a valid pip constraints file — and the extra must be resolved
    only once per invocation, not a second time for the freeze.
    """

    def test_emits_sorted_freeze_matching_resolution(self, drift_check, tmp_path, monkeypatch):
        monkeypatch.setattr(drift_check, "LOCK_DIR", tmp_path / "locks")
        (tmp_path / "locks").mkdir()
        # Populated baseline so the diff runs its normal (non-error) path.
        pyver = f"{sys.version_info.major}.{sys.version_info.minor}"
        (tmp_path / "locks" / "httpx.txt").write_text(
            f"# extra: httpx\n# python: {pyver}\n# captured: 2020-01-01\n"
            "# Regenerate with: hatch run drift-check refresh-baseline httpx\n"
            "\n"
            "certifi==2026.5.20\nhttpx==0.27.0\n",
            encoding="utf-8",
        )
        # Unsorted on purpose: the emitted freeze must be sorted regardless.
        resolved = {"httpx": "0.28.0", "certifi": "2026.5.20"}
        calls = {"n": 0}

        def fake_resolve(_extra: str) -> dict[str, str]:
            calls["n"] += 1
            return dict(resolved)

        monkeypatch.setattr(drift_check, "resolve_extra", fake_resolve)
        freeze = tmp_path / "candidates" / "httpx.txt"
        report = tmp_path / "reports" / "httpx.json"
        rc = drift_check.main(["diff", "httpx", "--out", str(report), "--emit-freeze", str(freeze)])
        assert rc == 0
        # Resolved exactly once — the freeze reuses the report's resolution.
        assert calls["n"] == 1
        assert freeze.read_text(encoding="utf-8") == "certifi==2026.5.20\nhttpx==0.28.0\n"

    def test_freeze_skipped_on_resolve_failure(self, drift_check, tmp_path, monkeypatch):
        # A failed resolve emits the synthetic error report but no freeze:
        # the smoke never runs (status != drift) and must not pin against a
        # stale or partial file.
        def boom(_extra: str) -> dict[str, str]:
            raise RuntimeError("simulated PyPI 500")

        monkeypatch.setattr(drift_check, "resolve_extra", boom)
        freeze = tmp_path / "candidates" / "httpx.txt"
        report = tmp_path / "reports" / "httpx.json"
        rc = drift_check.main(["diff", "httpx", "--out", str(report), "--emit-freeze", str(freeze)])
        assert rc == 0
        assert not freeze.exists()
        import json

        assert json.loads(report.read_text(encoding="utf-8"))["status"] == "error"

    def test_freeze_written_atomically_no_temp_left(self, drift_check, tmp_path, monkeypatch):
        monkeypatch.setattr(drift_check, "LOCK_DIR", tmp_path / "locks")
        (tmp_path / "locks").mkdir()
        (tmp_path / "locks" / "httpx.txt").write_text("# extra: httpx\n# python:\n# captured:\n", encoding="utf-8")
        monkeypatch.setattr(drift_check, "resolve_extra", lambda _e: {"httpx": "0.27.0"})
        freeze = tmp_path / "candidates" / "httpx.txt"
        drift_check.main(["diff", "httpx", "--out", str(tmp_path / "r.json"), "--emit-freeze", str(freeze)])
        siblings = sorted(p.name for p in freeze.parent.iterdir())
        assert siblings == ["httpx.txt"]
