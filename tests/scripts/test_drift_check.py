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
        # From pyproject.toml's [sftp] = ["paramiko>=3.0", "tenacity>=4.0"].
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

    def test_returns_sorted(self, drift_check):
        extras = drift_check.list_extras()
        assert extras == sorted(extras)
