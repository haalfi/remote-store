"""Unit tests for scripts/fast_gate.py (BK-403, BK-404).

Selection is tested on a small synthetic tree whose import shapes mirror the
real ones (a package ``__init__`` re-exporting, a root conftest, a scoped
conftest, two backends sharing a core module); the git half against a real
temporary repository, because what it must not touch is a real index.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "fast_gate.py"

# Git index copies, `--git-path` resolution and repo-relative paths differ by OS.
pytestmark = pytest.mark.os_sensitive


def _load_module():
    spec = importlib.util.spec_from_file_location("fast_gate", _SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("fast_gate", module)
    spec.loader.exec_module(module)
    return module


fg = _load_module()

BACKENDS_TOML = """
[backend.local]
sources = ["src/remote_store/backends/_local.py"]
[backend.s3]
sources = ["src/remote_store/backends/_s3.py", "src/remote_store/backends/_s3_base.py"]
[backend.s3_pyarrow]
sources = ["src/remote_store/backends/_s3_pyarrow.py"]
"""
FIXTURES_TOML = """
[fixture.local]
backend = "local"
stage = 1
[fixture.s3_moto]
backend = "s3"
stage = 1
[fixture.s3_live]
backend = "s3"
stage = 3
[fixture.s3_pyarrow_moto]
backend = "s3_pyarrow"
stage = 1
"""

FILES = {
    "src/remote_store/__init__.py": (
        "from remote_store._store import Store\nfrom remote_store._errors import NotFound\n"
    ),
    "src/remote_store/_store.py": "from remote_store._errors import NotFound\n",
    "src/remote_store/_errors.py": "class NotFound(Exception): ...\n",
    "src/remote_store/_util.py": "X = 1\n",
    "src/remote_store/backends/__init__.py": "",
    "src/remote_store/backends/_local.py": "from remote_store._errors import NotFound\n",
    "src/remote_store/backends/_s3_base.py": "from remote_store._util import X\n",
    "src/remote_store/backends/_s3.py": "from remote_store.backends._s3_base import X\n",
    "src/remote_store/backends/_s3_pyarrow.py": "from remote_store.backends._s3_base import X\n",
    "src/remote_store/backends/_sftp.py": "",
    "tests/conftest.py": "from remote_store import Store\n",
    "tests/e2e/conftest.py": "from remote_store.backends._sftp import *\n",
    "tests/e2e/test_flow.py": "def test_a(): ...\n",
    "tests/backends/fixtures/registry.py": "",
    "tests/backends/fixtures/backends.toml": BACKENDS_TOML,
    "tests/backends/fixtures/fixtures.toml": FIXTURES_TOML,
    "tests/backends/fixtures/local.py": "",
    "tests/backends/conformance/test_io.py": "def test_io(): ...\n",
    "tests/backends/s3/test_shared.py": "def test_s(): ...\n",
    "tests/backends/local/test_local.py": "from remote_store.backends._local import *\n",
    "tests/test_util.py": "from remote_store._util import X\n",
    "tests/test_store.py": "from remote_store import Store\n",
    "tests/_helpers_x.py": "from tests.test_util import X\n",
    "tests/test_uses_helper.py": "from tests._helpers_x import X\n",
    "tests/scripts/test_tool.py": "def test_t(): ...\n",
}


@pytest.fixture
def repo():
    return fg.Repo(dict(FILES))


def _select(repo, *paths: str, keys=None):
    return fg.select_tests(repo, [("M", p) for p in paths], keys)


# --------------------------------------------------------------------------- import graph


def test_name_from_a_package_init_resolves_to_its_defining_module(repo) -> None:
    edges = repo.graph.edges["tests/test_store.py"]
    assert edges == {"src/remote_store/_store.py"}


def test_dependents_are_transitive(repo) -> None:
    assert "tests/test_uses_helper.py" in repo.graph.dependents("src/remote_store/_util.py")


# --------------------------------------------------------------------------- selection


def test_module_the_root_conftest_reaches_is_full(repo) -> None:
    # tests/conftest.py imports Store -> _store.py -> _errors.py
    sel = _select(repo, "src/remote_store/_errors.py")
    assert sel.full
    assert "root test infrastructure" in sel.full_reasons[0]


def test_backend_source_selects_its_fixtures_dir_and_importers(repo) -> None:
    sel = _select(repo, "src/remote_store/backends/_local.py")
    assert not sel.full
    assert set(sel.conformance_ids) == {"local"}
    assert {"tests/backends/local/", "tests/backends/local/test_local.py", "tests/e2e/", "tests/scripts/"} <= set(
        sel.targets
    )
    assert "tests/test_store.py" not in sel.targets


def test_shared_helper_selects_every_backend_reaching_it_without_stage_2_or_3_ids(repo) -> None:
    sel = _select(repo, "src/remote_store/backends/_s3_base.py")
    assert set(sel.conformance_ids) == {"s3_moto", "s3_pyarrow_moto"}
    assert "tests/backends/s3/" in sel.targets


def test_module_every_backend_reaches_is_full() -> None:
    files = dict(FILES)
    files["src/remote_store/backends/_local.py"] = "from remote_store._util import X\n"
    sel = _select(fg.Repo(files), "src/remote_store/_util.py")
    assert sel.full
    assert "every backend" in sel.full_reasons[0]


def test_scoped_conftest_import_selects_its_directory_not_full(repo) -> None:
    sel = _select(repo, "src/remote_store/backends/_sftp.py")
    assert not sel.full
    assert "tests/e2e/" in sel.targets


def test_changed_test_runs_itself_and_its_importers(repo) -> None:
    # test_uses_helper.py imports it through tests/_helpers_x.py, which is no test itself.
    sel = _select(repo, "tests/test_util.py")
    assert set(sel.targets) == {"tests/test_util.py", "tests/test_uses_helper.py"}


def test_package_init_and_deleted_src_module_are_full(repo) -> None:
    assert _select(repo, "src/remote_store/__init__.py").full
    sel = fg.select_tests(repo, [("D", "src/remote_store/_gone.py")])
    assert sel.full


def test_root_conftest_and_fixture_infrastructure_are_full(repo) -> None:
    assert _select(repo, "tests/conftest.py").full
    assert _select(repo, "tests/backends/fixtures/local.py").full


def test_docs_specs_and_ci_files_select_tooling_tests_only(repo) -> None:
    sel = _select(repo, "sdd/BACKLOG.md", "docs-src/index.md", ".github/workflows/ci.yml", "scripts/x.py")
    assert not sel.full
    assert set(sel.targets) == {"tests/scripts/"}


@pytest.mark.parametrize(
    ("keys", "full"),
    [
        ({"tool.ruff.line-length"}, False),
        ({"tool.hatch.envs.default.scripts.fast"}, False),
        ({"project.version"}, False),
        ({"tool.hatch.envs.default.scripts.test-cov"}, True),
        ({"project.optional-dependencies.s3"}, True),
        ({"tool.pytest.ini_options.addopts"}, True),
        (None, True),  # did not parse
    ],
)
def test_pyproject_is_classified_per_changed_key(repo, keys, full) -> None:
    sel = _select(repo, "pyproject.toml", keys=keys)
    assert sel.full is full
    if not full:
        assert set(sel.targets) == {"tests/scripts/"}


def test_changed_pyproject_keys_flattens_and_diffs() -> None:
    old = '[tool.ruff]\nline-length = 100\n[project]\nversion = "1"\n'
    new = '[tool.ruff]\nline-length = 120\n[project]\nversion = "1"\n'
    assert fg.changed_pyproject_keys(old, new) == {"tool.ruff.line-length"}
    assert fg.changed_pyproject_keys(old, "[broken") is None


# --------------------------------------------------------------------------- members and commands


def test_specs_only_round_skips_typecheck_examples_notebooks_and_docs_build(repo) -> None:
    paths = ["sdd/BACKLOG.md", "sdd/traces/x.yml"]
    steps = fg.plan_steps(paths, _select(repo, *paths))
    assert set(steps) == {"preflight", "lint", "format-check", "tests", "docs-check", "check-links"}


def test_src_round_runs_typecheck_examples_notebooks_and_docs_build(repo) -> None:
    paths = ["src/remote_store/backends/_local.py"]
    steps = fg.plan_steps(paths, _select(repo, *paths))
    assert {"typecheck", "examples", "notebooks", "docs-build", "tests"} <= set(steps)


def test_empty_selection_skips_the_test_member() -> None:
    assert "tests" not in fg.plan_steps(["x.md"], fg.Selection())


def test_conformance_ids_run_as_their_own_invocation() -> None:
    sel = fg.Selection()
    sel.add("tests/test_a.py", "r")
    sel.add_ids({"local", "s3_moto"}, "r")
    cmds = fg.pytest_commands(sel, serial=True)
    assert len(cmds) == 2
    assert cmds[0][-1] == "tests/test_a.py"
    assert cmds[0][cmds[0].index("-n") + 1] == "0"
    assert cmds[1][-3:] == [fg.CONFORMANCE, "-k", "local or s3_moto"]


def test_directory_target_covering_conformance_drops_the_id_filtered_run() -> None:
    sel = fg.Selection()
    sel.add("tests/backends/", "conftest scope")
    sel.add_ids({"local"}, "r")
    cmds = fg.pytest_commands(sel, serial=False)
    assert len(cmds) == 1
    assert cmds[0][-1] == "tests/backends/"


def test_full_selection_is_one_unfiltered_stage_1_run_writing_junit(tmp_path: Path) -> None:
    junit = tmp_path / "j.xml"
    cmds = fg.pytest_commands(fg.Selection(full_reasons=["x"]), serial=False, junit=junit)
    assert len(cmds) == 1
    assert cmds[0][-2:] == ["--stage=1", f"--junitxml={junit}"]


def test_unrecorded_file_counts_as_the_median_recorded_file() -> None:
    durations = {"tests/a.py::t": 1.0, "tests/b.py::t": 3.0, "tests/c.py::t": 5.0}
    sel = fg.Selection()
    sel.add("tests/scripts/", "r")
    files = ["tests/a.py", "tests/b.py", "tests/c.py", "tests/scripts/test_x.py"]
    assert fg.estimate(sel, durations, files) == (3.0, 12.0)


def test_conformance_ids_count_only_their_own_cells() -> None:
    durations = {
        "tests/backends/conformance/test_io.py::test_a[local]": 2.0,
        "tests/backends/conformance/test_io.py::test_a[s3_moto]": 6.0,
    }
    sel = fg.Selection()
    sel.add_ids({"local"}, "r")
    assert fg.estimate(sel, durations, ["tests/backends/conformance/test_io.py"]) == (2.0, 8.0)


def test_junit_cases_map_back_to_node_ids(tmp_path: Path) -> None:
    (tmp_path / "tests" / "scripts").mkdir(parents=True)
    (tmp_path / "tests" / "scripts" / "test_x.py").write_text("", encoding="utf-8")
    xml = (
        "<testsuites><testsuite>"
        '<testcase classname="tests.scripts.test_x.TestC" name="test_a[p]" time="1.5"/>'
        '<testcase classname="tests.scripts.test_x" name="test_b" time="0.25"/>'
        '<testcase classname="tests.gone" name="test_c" time="9"/>'
        "</testsuite></testsuites>"
    )
    assert fg.junit_durations(xml, tmp_path) == {
        "tests/scripts/test_x.py::TestC::test_a[p]": 1.5,
        "tests/scripts/test_x.py::test_b": 0.25,
    }


# --------------------------------------------------------------------------- git state


def _git(root: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True).stdout


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "t@example.com")
    _git(tmp_path, "config", "user.name", "t")
    _git(tmp_path, "config", "commit.gpgsign", "false")
    (tmp_path / ".gitignore").write_text("ignored.txt\n", encoding="utf-8")
    (tmp_path / "a.txt").write_text("a\n", encoding="utf-8")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-q", "-m", "init")
    return tmp_path


def test_worktree_tree_sees_untracked_files_but_not_ignored_ones_and_leaves_the_index_alone(git_repo: Path) -> None:
    base = fg.worktree_tree(git_repo)
    (git_repo / "new.txt").write_text("n\n", encoding="utf-8")
    (git_repo / "ignored.txt").write_text("i\n", encoding="utf-8")
    (git_repo / "a.txt").write_text("changed\n", encoding="utf-8")
    head = fg.worktree_tree(git_repo)
    assert sorted(fg.diff_trees(base, head, git_repo)) == [("A", "new.txt"), ("M", "a.txt")]
    assert _git(git_repo, "status", "--porcelain").splitlines() == [" M a.txt", "?? new.txt"]


def test_green_record_round_trips_and_is_void_under_another_interpreter(git_repo: Path) -> None:
    assert fg.green_tree(git_repo) is None
    tree = fg.worktree_tree(git_repo)
    fg.record_green(tree, git_repo)
    assert fg.green_tree(git_repo) == tree
    path = fg.state_path(git_repo)
    path.write_text(json.dumps({"tree": tree, "python": "2.7.0"}), encoding="utf-8")
    assert fg.green_tree(git_repo) is None


def test_local_durations_override_ci_ones_and_merge_across_runs(git_repo: Path) -> None:
    (git_repo / ".test_durations_pass1").write_text(json.dumps({"t.py::a": 1.0, "t.py::b": 1.0}), encoding="utf-8")
    (git_repo / "t.py").write_text("", encoding="utf-8")
    for case, secs in (("a", "4"), ("c", "2")):
        junit = git_repo / "j.xml"
        junit.write_text(
            f'<testsuite><testcase classname="t" name="{case}" time="{secs}"/></testsuite>', encoding="utf-8"
        )
        fg.record_durations(junit, git_repo)
    assert fg.load_durations(git_repo) == {"t.py::a": 4.0, "t.py::b": 1.0, "t.py::c": 2.0}
    fg.record_durations(git_repo / "missing.xml", git_repo)  # a run that wrote no report changes nothing
    assert fg.load_durations(git_repo)["t.py::a"] == 4.0
