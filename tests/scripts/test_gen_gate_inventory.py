"""Unit tests for scripts/gen_gate_inventory.py (ID-245)."""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"

if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import gen_gate_inventory as _mod  # noqa: E402


def _module(body: str) -> str:
    """Wrap *body* as a module docstring followed by a token of code."""
    return f'"""Summary line.\n\n{textwrap.dedent(body)}"""\n\nX = 1\n'


PAIR_BLOCK = """
    Drift-gate::

        kind:       pair
        compares:   a.md <-> b.json
        domain:     process
"""

RULE_BLOCK = """
    Drift-gate::

        kind:       rule
        rule:       every test asserts something
        domain:     verification
"""


class TestParseDeclarations:
    """The docstring block is the only authored input; parsing it must be strict."""

    @pytest.mark.spec("ID-245")
    def test_pair_block_yields_compares_and_domain(self) -> None:
        (declaration,) = _mod.parse_declarations(_module(PAIR_BLOCK), "s.py")
        assert declaration.kind == "pair"
        assert declaration.compares == "a.md <-> b.json"
        assert declaration.domain == "process"
        assert declaration.subject == "a.md <-> b.json"

    @pytest.mark.spec("ID-245")
    def test_rule_block_yields_rule_as_subject(self) -> None:
        (declaration,) = _mod.parse_declarations(_module(RULE_BLOCK), "s.py")
        assert declaration.kind == "rule"
        assert declaration.compares is None
        assert declaration.subject == "every test asserts something"

    @pytest.mark.spec("ID-245")
    def test_no_block_yields_no_declaration(self) -> None:
        assert _mod.parse_declarations(_module("\nJust prose, no block.\n"), "s.py") == []

    @pytest.mark.spec("ID-245")
    def test_continuation_line_appends_to_previous_field(self) -> None:
        (declaration,) = _mod.parse_declarations(
            _module("""
    Drift-gate::

        kind:       pair
        compares:   a.md
            <-> b.json
        domain:     process
"""),
            "s.py",
        )
        assert declaration.compares == "a.md <-> b.json"

    @pytest.mark.spec("ID-245")
    def test_pair_without_compares_is_rejected(self) -> None:
        with pytest.raises(_mod.DeclarationError, match="needs a `compares:`"):
            _mod.parse_declarations(
                _module("\n    Drift-gate::\n\n        kind:       pair\n        domain:     process\n"), "s.py"
            )

    @pytest.mark.spec("ID-245")
    def test_rule_carrying_compares_is_rejected(self) -> None:
        with pytest.raises(_mod.DeclarationError, match="must not carry `compares:`"):
            _mod.parse_declarations(
                _module("""
    Drift-gate::

        kind:       rule
        rule:       something
        compares:   a.md <-> b.json
        domain:     verification
"""),
                "s.py",
            )

    @pytest.mark.spec("ID-245")
    def test_missing_domain_is_rejected(self) -> None:
        with pytest.raises(_mod.DeclarationError, match="needs a `domain:`"):
            _mod.parse_declarations(
                _module("\n    Drift-gate::\n\n        kind:       pair\n        compares:   a <-> b\n"), "s.py"
            )

    @pytest.mark.spec("ID-245")
    def test_unknown_kind_is_rejected(self) -> None:
        with pytest.raises(_mod.DeclarationError, match="must be pair or rule"):
            _mod.parse_declarations(
                _module("\n    Drift-gate::\n\n        kind:       vibes\n        domain:     process\n"), "s.py"
            )

    @pytest.mark.spec("ID-245")
    def test_unknown_field_is_rejected(self) -> None:
        with pytest.raises(_mod.DeclarationError, match="unknown Drift-gate field"):
            _mod.parse_declarations(
                _module("""
    Drift-gate::

        kind:       pair
        compares:   a <-> b
        domain:     process
        severity:   high
"""),
                "s.py",
            )

    @pytest.mark.spec("ID-245")
    def test_multiple_blocks_need_entrypoints(self) -> None:
        """Without entrypoints nothing matches an argv, so every row would drop in silence."""
        with pytest.raises(_mod.DeclarationError, match="needs an `entrypoint:`"):
            _mod.parse_declarations(_module(PAIR_BLOCK + RULE_BLOCK), "s.py")

    @pytest.mark.spec("ID-245")
    def test_multiple_blocks_with_entrypoints_are_accepted(self) -> None:
        declarations = _mod.parse_declarations(
            _module("""
    Drift-gate::

        kind:       pair
        entrypoint: diff
        compares:   resolved set <-> baseline
        domain:     process

    Drift-gate::

        kind:       pair
        entrypoint: render-docs
        compares:   locks <-> page
        domain:     explanation
"""),
            "s.py",
        )
        assert [d.entrypoint for d in declarations] == ["diff", "render-docs"]

    @pytest.mark.spec("ID-245")
    def test_block_is_read_only_from_the_module_docstring(self) -> None:
        """A block in a comment or a function docstring is not a declaration."""
        source = (
            '"""Summary."""\n\n'
            "# Drift-gate::\n#\n#     kind: pair\n\n"
            "def f():\n"
            '    """Drift-gate::\n\n'
            "    kind:       pair\n"
            "    compares:   a <-> b\n"
            "    domain:     process\n"
            '    """\n'
        )
        assert _mod.parse_declarations(source, "s.py") == []


class TestWiringDerivation:
    """The claim space is what the repo runs, not a glob over script names."""

    @pytest.mark.spec("ID-245")
    def test_composed_targets_expand_transitively(self) -> None:
        table = {
            "docs-gate": ["check-links", "docs-build"],
            "check-links": ["python scripts/docs/check_links.py --root ."],
            "docs-build": ["mkdocs build --strict"],
        }
        assert _mod._resolve("docs-gate", table, frozenset()) == [("scripts/docs/check_links.py", "--root .")]

    @pytest.mark.spec("ID-245")
    def test_resolution_survives_a_cycle(self) -> None:
        table = {"a": ["b"], "b": ["a", "python scripts/check_x.py"]}
        assert _mod._resolve("a", table, frozenset()) == [("scripts/check_x.py", "")]

    @pytest.mark.spec("ID-245")
    def test_invocation_captures_trailing_argv(self) -> None:
        assert _mod._invocations("python scripts/drift_check.py render-docs --check") == [
            ("scripts/drift_check.py", "render-docs --check")
        ]

    @pytest.mark.spec("ID-245")
    def test_nested_script_paths_are_reached(self) -> None:
        """The `scripts/check_*.py` glob misses this one; the wiring does not."""
        assert _mod._invocations("python scripts/docs/check_links.py") == [("scripts/docs/check_links.py", "")]

    @pytest.mark.spec("ID-245")
    def test_entrypoint_matches_by_argv_prefix(self) -> None:
        diff = _mod.Declaration(kind="pair", domain="process", compares="a <-> b", entrypoint="diff")
        render = _mod.Declaration(kind="pair", domain="process", compares="c <-> d", entrypoint="render-docs")
        assert _mod._match([diff, render], "render-docs --check") is render
        assert _mod._match([diff, render], "extras") is None


class TestEnforcement:
    """Enforcement is derived from wiring; a declaration cannot claim it."""

    def _mechanism(self, *homes: str) -> _mod.Mechanism:
        declaration = _mod.Declaration(kind="pair", domain="process", compares="a <-> b")
        return _mod.Mechanism(path="scripts/check_x.py", declaration=declaration, homes=homes)

    @pytest.mark.spec("ID-245")
    def test_gate_bundle_is_gating(self) -> None:
        assert self._mechanism("all", "lint").enforcement == "gating"

    @pytest.mark.spec("ID-245")
    def test_ci_job_is_gating(self) -> None:
        assert self._mechanism("ci.yml:verify-formal").enforcement == "gating"

    @pytest.mark.spec("ID-245")
    def test_non_ci_workflow_is_scheduled(self) -> None:
        assert self._mechanism("drift-guard.yml:check").enforcement == "scheduled"

    @pytest.mark.spec("ID-245")
    def test_bare_hatch_target_is_advisory(self) -> None:
        assert self._mechanism("report-trace-outcomes").enforcement == "advisory"


class TestLocalization:
    """DRIFT-RULES Rule 2: report which element differs, not that a difference exists."""

    @pytest.mark.spec("ID-245")
    def test_changed_row_names_its_mechanism(self) -> None:
        was = "| `scripts/check_x.py` | a <-> b | process | `lint` | gating |"
        now = "| `scripts/check_x.py` | a <-> c | process | `lint` | gating |"
        assert _mod._differing_rows(was, now) == ["  row differs:        `scripts/check_x.py`"]

    @pytest.mark.spec("ID-245")
    def test_added_row_names_its_mechanism(self) -> None:
        row = "| `scripts/check_new.py` | a <-> b | process | `lint` | gating |"
        assert _mod._differing_rows("", row) == ["  added or changed:   `scripts/check_new.py`"]


class TestRepoState:
    """The gate against the real repo, which is what CI runs."""

    @pytest.mark.spec("ID-245")
    def test_every_wired_mechanism_declares(self) -> None:
        _mechanisms, problems = _mod.collect()
        assert problems == []

    @pytest.mark.spec("ID-245")
    def test_committed_inventory_matches_a_fresh_render(self) -> None:
        mechanisms, _problems = _mod.collect()
        assert _mod.render(mechanisms) == _mod.OUTPUT.read_text(encoding="utf-8")

    @pytest.mark.spec("ID-245")
    def test_the_generator_inventories_itself(self) -> None:
        """An inventory exempting its own generator reproduces the hole it closes."""
        mechanisms, _problems = _mod.collect()
        assert any(m.path == "scripts/gen_gate_inventory.py" for m in mechanisms)

    @pytest.mark.spec("ID-245")
    def test_the_nested_gate_the_glob_misses_is_present(self) -> None:
        mechanisms, _problems = _mod.collect()
        assert any(m.path == "scripts/docs/check_links.py" for m in mechanisms)

    @pytest.mark.spec("ID-245")
    def test_non_mechanism_scripts_are_not_inventoried(self) -> None:
        """`run_tests.py` and friends are wired but compare nothing."""
        mechanisms, _problems = _mod.collect()
        paths = {m.path for m in mechanisms}
        assert paths.isdisjoint({"scripts/run_tests.py", "scripts/run_mutate.py", "scripts/mutation_report.py"})
