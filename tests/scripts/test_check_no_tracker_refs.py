"""Unit tests for scripts/check_no_tracker_refs.py."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "check_no_tracker_refs.py"


def _load():
    spec = importlib.util.spec_from_file_location("check_no_tracker_refs", _SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("check_no_tracker_refs", mod)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


_mod = _load()


# ---------------------------------------------------------------------------
# Regex coverage
# ---------------------------------------------------------------------------


class TestPatterns:
    """One example per regex; if a pattern stops matching, this surfaces it."""

    @pytest.mark.parametrize(
        "snippet",
        [
            "see ID-211 for context",
            "follow-up to BK-243",
            "Fixes BUG-185",
            "Release blocker BL-001",
            "audit finding AF-007",
        ],
    )
    def test_backlog_patterns_match(self, snippet):
        out = _mod._scan_lines([snippet], path=Path("x.md"))
        assert len(out) == 1

    @pytest.mark.parametrize(
        "snippet",
        [
            # Prefixes that were in the original enumerated set.
            "see BE-008",
            "ASYNC-080 invariant",
            "WR-013 metadata",
            "SIO-009 lazy reads",
            "CFG-012 unknown keys",
            # Prefixes the original enumerated set MISSED and that the
            # structural pattern catches. If any of these stop matching,
            # the cleanup half of BK-246 is silently regressing.
            "see S3-026 routing",
            "AZ-014 HNS contract",
            "MEM-001 memory backend",
            "BATCH-005 stop on error",
            "AW-001 atomic write",
            "STREAM-004 lazy read",
            "PARQ-002 dataset",
            "HC-001 health check",
        ],
    )
    def test_spec_patterns_match(self, snippet):
        out = _mod._scan_lines([snippet], path=Path("x.md"))
        assert len(out) == 1

    def test_compound_prefix_matches(self):
        # ``SQL-BLOB-020`` is one token, not ``SQL`` + ``BLOB-020``.
        out = _mod._scan_lines(["See SQL-BLOB-020 for the lazy-read story"], path=Path("x.md"))
        assert len(out) == 1
        assert out[0].match == "SQL-BLOB-020"

    def test_numeric_spec_matches(self):
        out = _mod._scan_lines(["See spec 003 for details"], path=Path("x.md"))
        assert len(out) == 1
        assert out[0].match == "spec 003"

    def test_numeric_spec_above_099_matches(self):
        # ``\d{3,}`` keeps the pattern correct once specs cross 099.
        out = _mod._scan_lines(["See spec 100 for details"], path=Path("x.md"))
        assert len(out) == 1
        assert out[0].match == "spec 100"

    def test_internal_rfc_matches(self):
        out = _mod._scan_lines(["per RFC-0014 design"], path=Path("x.md"))
        assert len(out) == 1
        assert out[0].match == "RFC-0014"

    def test_internal_adr_matches(self):
        out = _mod._scan_lines(["per ADR-0025"], path=Path("x.md"))
        assert len(out) == 1
        assert out[0].match == "ADR-0025"

    def test_pr_ref_matches(self):
        out = _mod._scan_lines(["fixed in PR #686"], path=Path("x.md"))
        assert len(out) == 1
        assert out[0].match == "PR #686"

    # External / unrelated forms must NOT match.

    @pytest.mark.parametrize(
        "snippet",
        [
            # IETF-style RFCs (digits don't start with 0).
            "see RFC-3986 for URIs",
            "RFC-7230 §3.3",
            # External ADR (won't normally appear, but test the carve-out).
            "ADR-1024 from another project",
            # Hyphenated capitalized word with no digits.
            "Some-Name has hyphens",
            # Lowercase prefix.
            "bug-123 lowercase",
            # External standards / codes -- in ``_EXTERNAL_PREFIXES``.
            "HTTP-404 on every read",
            "CVE-2024-12345 advisory",
            "decode as UTF-8",
            "ISO-8601 timestamps",
            "IEEE-754 float semantics",
            "see PEP-484 for typing",
            "SHA-256 digest",
            "MD5-128 hash",
            # SSH protocol version (false positive seen in real prose).
            'banner "SSH-2.0-OpenSSH_8.9p1"',
            # Conda Enhancement Proposal -- the conda recipe's own format
            # marker, which ships in the header the feedstock copy carries.
            "v1 format (CEP-13 / rattler-build)",
        ],
    )
    def test_non_matches(self, snippet):
        assert _mod._scan_lines([snippet], path=Path("x.md")) == []

    def test_external_prefixes_documented(self):
        # If a new prefix is added to ``_EXTERNAL_PREFIXES`` it must be
        # exercised by ``test_non_matches`` above so the exemption is
        # locked behind a behavioural test. CVE is intentionally not
        # listed because its IDs are always compound (``CVE-YYYY-NNNN``)
        # and the carve-out lives in ``_is_internal_tracker``'s
        # leading-alpha branch, not the bare-prefix set.
        exercised = {
            "HTTP",
            "UTF",
            "ISO",
            "IEEE",
            "PEP",
            "SHA",
            "MD5",
            "SSH",
            "CEP",
        }
        # frozenset equality is the cheapest form of "any addition fails the test".
        assert frozenset(exercised) == _mod._EXTERNAL_PREFIXES, (
            "Add the new external prefix to test_non_matches above before extending the allowlist."
        )


# ---------------------------------------------------------------------------
# Allowlist
# ---------------------------------------------------------------------------


class TestAllowlist:
    def test_conda_forge_pr_allowlisted(self):
        line = "Until conda-forge/staged-recipes PR #32401 is merged"
        out = _mod._scan_lines([line], path=Path("x.md"))
        assert out == []

    def test_unrelated_pr_ref_still_flagged(self):
        # The allowlist substring is specific to conda-forge — a bare
        # ``PR #NNN`` on the same line as another allowlisted phrase
        # still flags.
        line = "PR #686 introduced the regression; see conda-forge/staged-recipes PR #32401 too"
        out = _mod._scan_lines([line], path=Path("x.md"))
        assert len(out) == 1
        assert out[0].match == "PR #686"


# ---------------------------------------------------------------------------
# Python scanner — only docstrings, never comments
# ---------------------------------------------------------------------------


class TestPythonScanner:
    def test_docstring_flagged(self, tmp_path):
        f = tmp_path / "mod.py"
        f.write_text(
            'def foo():\n    """Does the thing (BE-008)."""\n',
            encoding="utf-8",
        )
        out = _mod._scan_python_file(f)
        assert len(out) == 1
        assert out[0].match == "BE-008"

    def test_module_docstring_flagged(self, tmp_path):
        f = tmp_path / "mod.py"
        f.write_text('"""Module about ID-211."""\n', encoding="utf-8")
        out = _mod._scan_python_file(f)
        assert len(out) == 1
        assert out[0].match == "ID-211"

    def test_class_docstring_flagged(self, tmp_path):
        f = tmp_path / "mod.py"
        f.write_text(
            'class Foo:\n    """Describes WR-005."""\n    pass\n',
            encoding="utf-8",
        )
        out = _mod._scan_python_file(f)
        assert len(out) == 1
        assert out[0].match == "WR-005"

    def test_inline_comment_not_flagged(self, tmp_path):
        """A `# ID-211` comment never appears in any docstring AST node, so it cannot match."""
        f = tmp_path / "mod.py"
        f.write_text(
            'def foo():  # see ID-211\n    """Clean docstring."""\n    pass  # BE-008 also\n',
            encoding="utf-8",
        )
        out = _mod._scan_python_file(f)
        assert out == []

    def test_clean_file(self, tmp_path):
        f = tmp_path / "ok.py"
        f.write_text(
            'def foo():\n    """Behavioural description, no IDs."""\n    pass\n',
            encoding="utf-8",
        )
        assert _mod._scan_python_file(f) == []

    def test_syntax_error_is_silent_skip(self, tmp_path):
        f = tmp_path / "broken.py"
        f.write_text("def foo(:\n", encoding="utf-8")
        assert _mod._scan_python_file(f) == []


# ---------------------------------------------------------------------------
# Markdown scanner
# ---------------------------------------------------------------------------


class TestMarkdownScanner:
    def test_inline_id_flagged(self, tmp_path):
        f = tmp_path / "page.md"
        f.write_text("# Title\n\nDescribes ID-211.\n", encoding="utf-8")
        out = _mod._scan_markdown_file(f)
        assert len(out) == 1
        assert out[0].line == 3

    def test_clean_markdown(self, tmp_path):
        f = tmp_path / "page.md"
        f.write_text("# Title\n\nClean prose.\n", encoding="utf-8")
        assert _mod._scan_markdown_file(f) == []


# ---------------------------------------------------------------------------
# main + repo
# ---------------------------------------------------------------------------


class TestCondaRecipeScanner:
    """The one YAML file that leaves this repository.

    ``packaging/conda-forge/recipe.yaml`` is copied onto
    ``conda-forge/remote-store-feedstock``, where an internal coordinate
    points somewhere the reader cannot follow. The block above
    ``context:`` is exempt because ``gen_conda_feedstock.py`` replaces it.
    """

    def _write(self, tmp_path, text):
        f = tmp_path / "recipe.yaml"
        f.write_text(text, encoding="utf-8")
        return f

    def test_body_coordinate_is_flagged_at_its_real_line(self, tmp_path):
        f = self._write(
            tmp_path,
            '# header\n#\ncontext:\n  version: "1.0"\nbuild:\n  # see BUG-998\n  number: 0\n',
        )
        out = _mod._scan_conda_recipe(f)
        assert [(v.line, v.match) for v in out] == [(6, "BUG-998")]

    def test_header_coordinate_is_exempt(self, tmp_path):
        # The generator replaces everything above `context:`, so a coordinate
        # there never reaches the feedstock.
        f = self._write(tmp_path, '# tracked by BK-999\ncontext:\n  version: "1.0"\n')
        assert _mod._scan_conda_recipe(f) == []

    def test_cep_13_is_not_a_coordinate(self, tmp_path):
        # The recipe's format marker survives into the shipped header, so it
        # must not read as a tracker wherever it appears.
        f = self._write(tmp_path, 'context:\n  version: "1.0"\n# v1 format (CEP-13)\n')
        assert _mod._scan_conda_recipe(f) == []

    def test_a_recipe_without_the_marker_is_scanned_whole(self, tmp_path):
        # The marker is how the exemption is bounded. A file that has lost it
        # has no established exempt block, and scanning nothing would report
        # clean while checking nothing.
        f = self._write(tmp_path, "# BK-999 above\npackage:\n  name: x\n")
        assert [v.match for v in _mod._scan_conda_recipe(f)] == ["BK-999"]

    def test_an_absent_recipe_is_refused_rather_than_passed(self, tmp_path, capsys):
        """The success message names surfaces the run covered.

        Returning 0 here would put "no tracker IDs found in published
        surfaces" over a file that was never opened -- the unearned claim the
        marker-less case is already careful to avoid.
        """
        src_empty = tmp_path / "_empty_src"
        src_empty.mkdir()
        rc = _mod.main(
            [
                "--src-root",
                str(src_empty),
                "--docs-root",
                str(src_empty),
                "--conda-recipe",
                str(tmp_path / "absent.yaml"),
            ]
        )
        assert rc == 1
        assert "cannot say the conda recipe is clean" in capsys.readouterr().err

    def test_a_recipe_that_cannot_be_read_is_refused_by_the_scanner_too(self, tmp_path):
        """Not only an absent one, which ``is_file()`` already catches.

        The enumeration's guard answers "is there a file here"; it cannot
        answer "could its bytes be read". A recipe that exists and is not
        valid UTF-8 passed that guard and then returned no violations, so the
        gate printed "no tracker IDs found in published surfaces" over a file
        it had not read -- the exact outcome the guard one level up exists to
        prevent.
        """
        undecodable = tmp_path / "recipe.yaml"
        undecodable.write_bytes(b"context:\n  version: \xff\xfe not utf-8\n")
        with pytest.raises(_mod.MissingRecipeError):
            _mod._scan_conda_recipe(undecodable)

    def test_an_unreadable_recipe_reaches_main_as_a_refusal(self, tmp_path, capsys):
        undecodable = tmp_path / "recipe.yaml"
        undecodable.write_bytes(b"context:\n  version: \xff\xfe not utf-8\n")
        src_empty = tmp_path / "_empty_src"
        src_empty.mkdir()
        rc = _mod.main(
            [
                "--src-root",
                str(src_empty),
                "--docs-root",
                str(src_empty),
                "--conda-recipe",
                str(undecodable),
            ]
        )
        assert rc == 1
        assert "cannot say the conda recipe is clean" in capsys.readouterr().err

    def test_the_committed_recipe_is_clean(self):
        """Integration guard: the real recipe carries no coordinate below ``context:``."""
        assert _mod._scan_conda_recipe(_mod._CONDA_RECIPE) == []


class TestMain:
    def _args(self, tmp_path, **over):
        """Every root explicitly pinned away from the real tree.

        Defaulting any of them would make an unrelated test assert on the
        repository's own contents, which is the dependency this signature
        exists to remove. The recipe is a real, clean stub rather than an
        absent path, because an absent one is now a refusal in its own right.
        """
        stub = tmp_path / "stub-recipe.yaml"
        stub.write_text('# header\ncontext:\n  version: "1.0"\n', encoding="utf-8")
        args = {
            "--src-root": str(tmp_path),
            "--docs-root": str(tmp_path),
            "--conda-recipe": str(stub),
        }
        args.update(over)
        return [part for pair in args.items() for part in pair]

    def test_clean_subtrees_return_zero(self, tmp_path):
        # Empty src + empty docs-src + no root MD files + a clean stub recipe
        # (`_args` writes one, because an absent recipe is its own refusal).
        assert _mod.main(self._args(tmp_path)) == 0

    def test_violation_returns_one(self, tmp_path, capsys):
        bad = tmp_path / "page.md"
        bad.write_text("References ID-999.\n", encoding="utf-8")
        # Point docs-root at tmp_path so the synthetic page is in scope;
        # use an empty src-root so the real source tree isn't scanned.
        src_empty = tmp_path / "_empty_src"
        src_empty.mkdir()
        rc = _mod.main(self._args(tmp_path, **{"--src-root": str(src_empty)}))
        assert rc == 1
        captured = capsys.readouterr()
        assert "ID-999" in captured.err

    def test_the_recipe_reaches_main(self, tmp_path, capsys):
        # The scanner is wired into the entry point, not merely importable.
        recipe = tmp_path / "recipe.yaml"
        recipe.write_text('context:\n  version: "1.0"\n# BUG-997\n', encoding="utf-8")
        src_empty = tmp_path / "_empty_src"
        src_empty.mkdir()
        rc = _mod.main(
            self._args(
                tmp_path,
                **{"--src-root": str(src_empty), "--docs-root": str(src_empty), "--conda-recipe": str(recipe)},
            )
        )
        assert rc == 1
        assert "BUG-997" in capsys.readouterr().err

    def test_real_repo_is_clean(self):
        """Integration guard: every shipped surface stays free of tracker IDs.

        Runs against the default repo paths -- the same scope CI exercises.
        """
        assert _mod.main([]) == 0


# ---------------------------------------------------------------------------
# Spec-prefix discoverability
# ---------------------------------------------------------------------------


class TestSpecPrefixDiscovery:
    """Verify every spec section ID actually used in ``sdd/specs/`` is flagged.

    The structural ``_TRACKER_RE`` plus ``_EXTERNAL_PREFIXES`` carve-out
    is meant to catch every present and future spec prefix without
    enumeration; before this discovery test, the gate enumerated a
    closed list of 24 prefixes and silently missed every spec ID
    outside it (``S3-``, ``AZ-``, ``MEM-``, ``GLOB-``, ``CACHE-``,
    ``BATCH-``, ``XFER-``, ``RETRY-``, ``HC-``, ``ITER-``, ``WT-``,
    ``HTTP-``, ``STREAM-``, ``INTEG-``, ``DIGEST-``, ``SEEK-``, ``TLS-``,
    ``PARQ-``, ``XW-``, ``AW-``, ``S3PA-``, ``PA-``, ``SQL-QUERY-``,
    etc.). This test sweeps ``sdd/specs/*.md`` to keep the guarantee
    live: adding a new spec without updating the regex (or extending
    ``_EXTERNAL_PREFIXES`` when an external code matches the structural
    shape) fails a test instead of silently widening the leak surface.
    """

    _SPECS_DIR = Path(__file__).resolve().parents[2] / "sdd" / "specs"
    # Same shape as the gate's tracker matcher.
    _TOKEN_RE = __import__("re").compile(r"\b([A-Z][A-Z0-9-]*)-(\d+)\b")

    @classmethod
    def _discover_spec_prefixes(cls) -> set[str]:
        """Return every PREFIX seen in a ``PREFIX-NNN`` token across spec markdown."""
        found: set[str] = set()
        for path in sorted(cls._SPECS_DIR.glob("*.md")):
            for line in path.read_text(encoding="utf-8").splitlines():
                for m in cls._TOKEN_RE.finditer(line):
                    prefix = m.group(1)
                    # Skip the external-codes carve-out -- spec text legitimately
                    # references HTTP-404, RFC-3986, etc., and those are exempt
                    # from the gate by design.
                    if prefix in _mod._EXTERNAL_PREFIXES:
                        continue
                    found.add(prefix)
        return found

    def test_every_spec_prefix_is_flagged(self):
        prefixes = self._discover_spec_prefixes()
        assert prefixes, "Did not discover any spec prefixes — _SPECS_DIR misconfigured?"
        failures: list[str] = []
        for prefix in sorted(prefixes):
            # Skip RFC/ADR -- the gate flags only the leading-zero internal
            # form. Specs that cite IETF RFCs or external ADRs are exempt
            # by design.
            if prefix in {"RFC", "ADR"}:
                continue
            out = _mod._scan_lines([f"see {prefix}-001 for the contract"], path=Path("x.md"))
            if not out:
                failures.append(prefix)
        assert not failures, (
            f"The gate failed to flag {len(failures)} spec prefix(es) actually used in sdd/specs/: "
            f"{', '.join(failures)}. Either extend _TRACKER_RE to cover the missing shape, or add "
            "the prefix to _EXTERNAL_PREFIXES if it refers to an external code rather than a "
            "spec section."
        )
