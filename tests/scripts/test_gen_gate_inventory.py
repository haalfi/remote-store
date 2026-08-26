"""Unit tests for scripts/gen_gate_inventory.py (ID-245)."""

from __future__ import annotations

import subprocess
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

REPORT_BLOCK = """
    Drift-gate::

        kind:       report
        surfaces:   which documents readers found unclear
        domain:     process
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
    def test_report_block_yields_surfaces_as_subject(self) -> None:
        """A report measures rather than asserts, so `rule:` would claim a check nobody makes."""
        (declaration,) = _mod.parse_declarations(_module(REPORT_BLOCK), "s.py")
        assert declaration.kind == "report"
        assert declaration.rule is None
        assert declaration.subject == "which documents readers found unclear"

    @pytest.mark.spec("ID-245")
    def test_report_carrying_rule_is_rejected(self) -> None:
        with pytest.raises(_mod.DeclarationError, match="must not carry `rule:`"):
            _mod.parse_declarations(
                _module("""
    Drift-gate::

        kind:       report
        surfaces:   something
        rule:       every test asserts something
        domain:     process
"""),
                "s.py",
            )

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
        with pytest.raises(_mod.DeclarationError, match="must be one of"):
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

    def _mechanism(self, *homes: str, gate_homes: frozenset[str] = frozenset({"all", "lint"})) -> _mod.Mechanism:
        declaration = _mod.Declaration(kind="pair", domain="process", compares="a <-> b")
        return _mod.Mechanism(path="scripts/check_x.py", declaration=declaration, homes=homes, gate_homes=gate_homes)

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


def _tree(tmp_path: Path, scripts: dict[str, str], lint: list[str] | None = None) -> Path:
    """Build a minimal repo: a hatch script table, workflows, and scripts/."""
    (tmp_path / "scripts").mkdir()
    for name, body in scripts.items():
        (tmp_path / "scripts" / name).write_text(body, encoding="utf-8")
    commands = lint if lint is not None else [f"python scripts/{name}" for name in scripts]
    rendered = ", ".join(f'"{c}"' for c in commands)
    (tmp_path / "pyproject.toml").write_text(
        f'[tool.hatch.envs.default.scripts]\nlint = [{rendered}]\nall = ["lint"]\n', encoding="utf-8"
    )
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "ci.yml").write_text("jobs:\n  lint:\n    steps:\n      - run: uvx hatch run lint\n", encoding="utf-8")
    return tmp_path


class TestBackstop:
    """`unknown is a failure, not a skip` is the clause the whole design rests on."""

    @pytest.mark.spec("ID-245")
    def test_wired_mechanism_without_a_block_is_a_problem(self, tmp_path: Path) -> None:
        root = _tree(tmp_path, {"check_x.py": '"""Summary, no declaration."""\n'})
        mechanisms, problems = _mod.collect(root)
        assert mechanisms == []
        assert problems == ["scripts/check_x.py: wired but carries no `Drift-gate::` declaration block"]

    @pytest.mark.spec("ID-245")
    def test_wired_non_mechanism_without_a_block_is_not_a_problem(self, tmp_path: Path) -> None:
        """The heuristic must drop `run_mutate.py` and fail `check_foo.py`, not both or neither."""
        root = _tree(tmp_path, {"run_mutate.py": '"""Summary, no declaration."""\n'})
        mechanisms, problems = _mod.collect(root)
        assert (mechanisms, problems) == ([], [])

    @pytest.mark.spec("ID-245")
    def test_every_backstop_prefix_fires(self, tmp_path: Path) -> None:
        names = ["check_a.py", "gen_a.py", "drift_a.py", "report_a.py"]
        root = _tree(tmp_path, dict.fromkeys(names, '"""Summary."""\n'))
        _mechanisms, problems = _mod.collect(root)
        assert sorted(p.split(":")[0] for p in problems) == sorted(f"scripts/{n}" for n in names)

    @pytest.mark.spec("ID-245")
    def test_a_declared_mechanism_collects_with_its_homes(self, tmp_path: Path) -> None:
        root = _tree(tmp_path, {"check_x.py": _module(PAIR_BLOCK)})
        (mechanism,), problems = _mod.collect(root)
        assert problems == []
        assert mechanism.path == "scripts/check_x.py"
        assert mechanism.homes == ("all", "lint")
        assert mechanism.enforcement == "gating"


class TestCallIsolation:
    """`collect(root)` must not leak derived state into a later call."""

    @pytest.mark.spec("ID-245")
    def test_a_foreign_ci_target_does_not_become_a_gate_home_globally(self, tmp_path: Path) -> None:
        """Enforcement is a function of the mechanism, not of what collect last saw."""
        foreign = tmp_path / "foreign"
        foreign.mkdir()
        _tree(foreign, {"check_x.py": _module(PAIR_BLOCK)})
        (foreign / ".github" / "workflows" / "ci.yml").write_text(
            "jobs:\n  smoke:\n    steps:\n      - run: uvx hatch run smoke\n", encoding="utf-8"
        )
        _mod.collect(foreign)

        home = tmp_path / "home"
        home.mkdir()
        _tree(
            home,
            {"check_y.py": _module(PAIR_BLOCK)},
            lint=["python scripts/check_y.py"],
        )
        (home / "pyproject.toml").write_text(
            '[tool.hatch.envs.default.scripts]\nsmoke = ["python scripts/check_y.py"]\n', encoding="utf-8"
        )
        (home / ".github" / "workflows" / "ci.yml").write_text("jobs: {}\n", encoding="utf-8")
        (mechanism,), _problems = _mod.collect(home)
        assert mechanism.homes == ("smoke",)
        assert mechanism.enforcement == "advisory"


class TestPathBoundary:
    """A `tests/scripts/` path is not an invocation of the `scripts/` file it suffixes."""

    @pytest.mark.spec("ID-245")
    def test_nested_test_path_is_not_read_as_a_scripts_invocation(self) -> None:
        assert _mod._invocations("python tests/scripts/run_examples.py") == []

    @pytest.mark.spec("ID-245")
    def test_shell_comment_line_is_not_wiring(self) -> None:
        assert _mod._invocations("# see python scripts/check_x.py for details") == []

    @pytest.mark.spec("ID-245")
    def test_a_real_invocation_beside_a_comment_still_counts(self) -> None:
        body = "# python scripts/check_a.py is documented below\npython scripts/check_b.py --check\n"
        assert _mod._invocations(body) == [("scripts/check_b.py", "--check")]


class TestCli:
    """main()'s exit codes, which nothing else covers."""

    @pytest.mark.spec("ID-245")
    def test_check_exits_zero_on_the_committed_tree(self) -> None:
        result = subprocess.run(
            [sys.executable, str(SCRIPTS / "gen_gate_inventory.py"), "--check"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr

    @pytest.mark.spec("ID-245")
    def test_check_exits_one_when_the_inventory_is_stale(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        stale = tmp_path / "GATE-INVENTORY.md"
        stale.write_text("# not what the generator renders\n", encoding="utf-8")
        monkeypatch.setattr(_mod, "OUTPUT", stale)
        monkeypatch.setattr(sys, "argv", ["gen_gate_inventory.py", "--check"])
        with pytest.raises(SystemExit) as exit_info:
            _mod.main()
        assert exit_info.value.code == 1
        assert "is out of date" in capsys.readouterr().err

    @pytest.mark.spec("ID-245")
    def test_write_mode_renders_to_the_output_path(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        out = tmp_path / "GATE-INVENTORY.md"
        monkeypatch.setattr(_mod, "OUTPUT", out)
        monkeypatch.setattr(sys, "argv", ["gen_gate_inventory.py"])
        _mod.main()
        mechanisms, _problems = _mod.collect()
        assert out.read_text(encoding="utf-8") == _mod.render(mechanisms)


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
