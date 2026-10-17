"""Run the local gate on what changed since the last green run (BK-403, BK-404).

``hatch run all`` runs every member for every diff. This launcher runs the same
members, but only those the change can affect, and for the test member only the
tests it selects. It is the first gate, not the last: CI's full gate on every PR
push stays the merge barrier, and no run here asserts the coverage floor. A miss
here costs one round, not a defect. Accepted misses: a test that reads a changed
file as text without importing it, an import spelled as a string, a session hook
in a conftest below the root.

What changed (``worktree_tree`` against ``green_tree``): the working tree, untracked files
included, against the tree of the last run that passed in this checkout. A
review round edits a few files, so it narrows even when the PR as a whole
touched ``pyproject.toml`` or a base module, which made Phase 0's per-PR
selector fall back to the full suite on 72.6% of code PRs
(``sdd/research/bk-403-phase-0/report.md``). With no green run recorded, or a
different interpreter, the base is the merge base with ``origin/master``. The
record lives in the checkout's git directory, so each worktree keeps its own.

Which members run (``plan_steps``): ``preflight``, ``lint``, ``format-check``,
``docs-check`` and ``check-links`` always, being cheap and where local failures
concentrate; ``typecheck``, ``examples``, ``notebooks`` and ``docs-build`` only
for paths they read; tests by ``select_tests``. Members run in ``all``'s order
(``STEP_ORDER``, its test member being ``test-cov-s1``) and stop at the first
failure, like ``all``.

Which tests (``select_tests``): the first matching rule per changed path, the
union over paths, any FULL winning. A FULL rule covers what everything imports
(root and shared fixture infrastructure, package ``__init__`` modules, the
modules those import, dependency and pytest configuration). A ``src/`` module
selects the test files that import it transitively, plus conformance and the
backend's own directory for every backend whose sources reach it; reaching
every backend is FULL. A backend source outside ``src/`` and the compiled Dafny
oracle select that backend the same way. Docs, specs and scripts select
``tests/scripts/``, whose tests read them. The test files with a failure last
time are always added, by file (``last_failed``). A selection
estimated above half the suite's time runs the full Stage-1 suite instead; the
estimate prefers this checkout's own timings, recorded from every test run
(``record_durations``), over CI's ``.test_durations_pass1``.

Usage::

    hatch run fast                 # select, run, record green on success
    hatch run fast --plan          # print the plan and the reason per path; run nothing
    hatch run fast --full          # every member, full Stage-1 suite
    hatch run fast --base <rev>    # diff against a revision instead; records no green run

``RS_FAST_GATE=full`` forces ``--full``. Exit code: the first failing member's.
A selected test run that collects nothing (pytest exit 5, e.g. a file marked
``live``) does not fail; a full run that collects nothing does.
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import shutil
import subprocess
import sys
import tomllib
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATE_NAME = "rs-fast-gate.json"
FULL = "FULL"
CONFORMANCE = "tests/backends/conformance/"
E2E = "tests/e2e/"
# The directories outside src/ and scripts/ a test puts on sys.path, by every
# `sys.path.insert` under tests/ (grepped 2026-10-17): these two
# (tests/backends/dafny/_helpers.py, tests/_kernel/test_protocol_oracle.py), and
# sdd/research/token-usage/ (tests/scripts/test_tokkit.py,
# test_token_kit_cuts.py), whose changes reach tests/scripts/ through
# select_tests' last branch.
DAFNY_ORACLE_DIR = "sdd/formal/MemoryBackend-py/"
KERNEL_ORACLE_DIR = "sdd/formal/KernelProtocol-py/"
KERNEL_ORACLE_TESTS = "tests/_kernel/test_protocol_oracle.py"
SCRIPTS_TESTS = "tests/scripts/"
# A selection above this share of the suite's estimated time runs the suite.
CUTOFF = 0.5
# Below this many summed test seconds a selection runs in one process: starting
# xdist workers, each collecting its own copy of the selection, costs more.
SERIAL_BELOW_SECONDS = 20.0
# pytest's exit code when it collected nothing (ExitCode.NO_TESTS_COLLECTED).
NO_TESTS_COLLECTED = 5
DURATIONS_NAME = "rs-fast-gate-durations.json"
JUNIT_NAME = "rs-fast-gate-junit.xml"

FULL_PATHS = frozenset(
    {
        ".python-version",
        ".test_durations_pass1",
        "scripts/run_tests.py",
        "tests/conftest.py",
        "tests/_helpers.py",
    }
)
# Fixture modules every backend test reaches through the registry, plus the
# per-fixture modules, whose registry consumers live outside conformance.
FIXTURES_DIR = "tests/backends/fixtures/"
# Modules whose src/ imports are FULL: every collected test imports them. A
# conftest below the root (tests/aio/, tests/e2e/) scopes to its directory instead.
ROOT_IMPORTERS = (
    "tests/conftest.py",
    "tests/backends/fixtures/registry.py",
    "tests/backends/fixtures/_loader.py",
    "tests/backends/fixtures/_state.py",
    "tests/backends/fixtures/__init__.py",
)
EXAMPLE_TESTS = ("tests/test_examples.py", "tests/test_snippets.py", "tests/backends/conformance/test_examples.py")
PII_TEST = "tests/backends/fixtures/test_cassettes.py"
# pyproject keys that change no test outcome beyond what tests/scripts/ checks.
TOOLING_KEYS = (
    "project.version",
    "tool.bumpversion",
    "tool.ruff",
    "tool.mypy",
    "tool.coverage",
    "tool.codespell",
)
# What `mkdocs build --strict` reads: mkdocstrings over src/; scripts/gen_pages.py
# renders all of sdd/ and examples/, copies assets/ and scans every tracked .md
# for dual pages; pymdownx.snippets includes files from docs-src/, examples/,
# benchmarks/ and README.md (every `--8<--` target, grepped 2026-10-11).
DOCS_BUILD_PREFIXES = ("docs-src/", "src/", "sdd/", "examples/", "assets/", "benchmarks/", "scripts/docs/")
DOCS_BUILD_FILES = frozenset({"mkdocs.yml", "pyproject.toml", "scripts/gen_pages.py", "scripts/mkdocs_hooks.py"})


# --------------------------------------------------------------------------- import graph


def module_of(path: str) -> str | None:
    """Dotted module name of a repo path, or None for a path that is not importable as one."""
    if not path.endswith(".py"):
        return None
    parts = path[:-3].split("/")
    if parts[0] == "src":
        parts = parts[1:]
    elif parts[0] not in ("tests", "scripts"):
        return None
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts) if parts else None


@dataclass
class _Imports:
    # (module, names); names empty for ``import module``
    refs: list[tuple[str, tuple[str, ...]]] = field(default_factory=list)


def _parse_imports(path: str, text: str) -> _Imports:
    out = _Imports()
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return out
    pkg = (module_of(path) or "").split(".")
    if not path.endswith("__init__.py"):
        pkg = pkg[:-1]
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out.refs.extend((a.name, ()) for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = pkg[: len(pkg) - (node.level - 1)] if node.level > 1 else pkg
                mod = ".".join([*base, node.module] if node.module else base)
            else:
                mod = node.module or ""
            out.refs.append((mod, tuple(a.name for a in node.names)))
    return out


class Graph:
    """Static import graph over ``src/``, ``tests/`` and ``scripts/``.

    A name imported from a package ``__init__`` resolves to the module that
    defines it, so ``from remote_store import Store`` depends on ``_store.py``
    and not on every module the package re-exports.
    """

    def __init__(self, files: dict[str, str]) -> None:
        self.files = files
        self.mod2path = {m: p for p in files if (m := module_of(p))}
        self.imports = {p: _parse_imports(p, t) for p, t in files.items() if p.endswith(".py")}
        self.hubs = {p for p in files if p.startswith("src/") and p.endswith("/__init__.py")}
        self.edges: dict[str, set[str]] = {p: self._edges(p) for p in self.imports}
        self.rev: dict[str, set[str]] = defaultdict(set)
        for a, ds in self.edges.items():
            for d in ds:
                self.rev[d].add(a)

    def _resolve_name(self, hub: str, name: str, seen: frozenset[str] = frozenset()) -> set[str]:
        hub_mod = module_of(hub) or ""
        sub = self.mod2path.get(f"{hub_mod}.{name}")
        if sub:
            return {sub}
        if hub in seen:
            return {hub}
        for mod, names in self.imports[hub].refs:
            if name not in names:
                continue
            direct = self.mod2path.get(f"{mod}.{name}")
            if direct:
                return {direct}
            target = self.mod2path.get(mod)
            if target is None:
                return set()
            if target in self.hubs:
                return self._resolve_name(target, name, seen | {hub})
            return {target}
        return {hub}

    def _edges(self, path: str) -> set[str]:
        deps: set[str] = set()
        for mod, names in self.imports[path].refs:
            target = self.mod2path.get(mod)
            if names:
                for n in names:
                    sub = self.mod2path.get(f"{mod}.{n}")
                    if sub:
                        deps.add(sub)
                    elif target in self.hubs:
                        deps |= self._resolve_name(target, n)
                    elif target:
                        deps.add(target)
            elif target:
                deps.add(target)
        deps.discard(path)
        return deps

    def dependents(self, path: str) -> set[str]:
        """Every module that imports ``path``, transitively, not including it."""
        seen: set[str] = set()
        todo = [path]
        while todo:
            for y in self.rev.get(todo.pop(), ()):
                if y not in seen:
                    seen.add(y)
                    todo.append(y)
        return seen

    def reach(self, path: str) -> set[str]:
        """``path`` and every ``src/`` module it imports, transitively."""
        seen = {path}
        todo = [path]
        while todo:
            for y in self.edges.get(todo.pop(), ()):
                if y.startswith("src/") and y not in seen:
                    seen.add(y)
                    todo.append(y)
        return seen


# --------------------------------------------------------------------------- selection


@dataclass
class Selection:
    """Tests to run: whole files or directories, plus conformance limited to fixture ids."""

    full_reasons: list[str] = field(default_factory=list)
    targets: dict[str, str] = field(default_factory=dict)  # path -> first reason
    conformance_ids: dict[str, str] = field(default_factory=dict)  # fixture id -> first reason

    @property
    def full(self) -> bool:
        return bool(self.full_reasons)

    @property
    def empty(self) -> bool:
        return not (self.full or self.targets or self.conformance_ids)

    def add(self, target: str, reason: str) -> None:
        # addopts ignores tests/e2e and `all` never runs it, but an explicit
        # target bypasses --ignore, so it is never named.
        if not target.startswith(E2E):
            self.targets.setdefault(target, reason)

    def add_ids(self, ids: set[str], reason: str) -> None:
        for i in sorted(ids):
            self.conformance_ids.setdefault(i, reason)


def _is_test_file(p: str) -> bool:
    return p.startswith("tests/") and p.rsplit("/", 1)[-1].startswith("test_") and p.endswith(".py")


def nearest_test_dir(repo: Repo, path: str) -> str:
    """The closest folder above ``path`` that holds a test file, ``tests/`` at worst.

    A fixture folder (``tests/scripts/fixtures/<x>/``) holds no test; its
    readers sit in a folder above it, and an empty selection collects nothing.
    """
    d = path.rsplit("/", 1)[0]
    while d != "tests" and not any(_is_test_file(f) and f.startswith(d + "/") for f in repo.files):
        d = d.rsplit("/", 1)[0]
    return d + "/"


def suite_files(repo: Repo) -> list[str]:
    """The test files the full Stage-1 run collects: every test file outside ``tests/e2e/``."""
    return [f for f in repo.files if _is_test_file(f) and not f.startswith(E2E)]


def _toml(text: str | None) -> dict:
    try:
        return tomllib.loads(text or "")
    except tomllib.TOMLDecodeError:
        return {}


def _flatten(d: object, prefix: str = "") -> dict[str, object]:
    if isinstance(d, dict):
        out: dict[str, object] = {}
        for k, v in d.items():
            out |= _flatten(v, f"{prefix}{k}.")
        return out
    return {prefix[:-1]: d}


def changed_pyproject_keys(old: str | None, new: str | None) -> set[str] | None:
    """Dotted keys whose value differs between two ``pyproject.toml`` texts; None if either fails to parse."""
    try:
        a = _flatten(tomllib.loads(old or ""))
        b = _flatten(tomllib.loads(new or ""))
    except tomllib.TOMLDecodeError:
        return None
    return {k for k in a.keys() | b.keys() if a.get(k) != b.get(k)}


def _tooling_key(key: str) -> bool:
    if any(key == p or key.startswith(p + ".") for p in TOOLING_KEYS):
        return True
    # A hatch script other than a test runner changes no test outcome.
    m = re.match(r"tool\.hatch\.envs\.[^.]+\.scripts\.([^.]+)", key)
    return bool(m) and not m.group(1).startswith("test")


class Repo:
    """The facts selection reads from the working tree."""

    def __init__(self, files: dict[str, str]) -> None:
        self.files = files
        self.graph = Graph(files)
        backends = _toml(files.get(f"{FIXTURES_DIR}backends.toml")).get("backend", {})
        self.backend_sources = {b: [*v.get("sources", []), *v.get("async_sources", [])] for b, v in backends.items()}
        fixtures = _toml(files.get(f"{FIXTURES_DIR}fixtures.toml")).get("fixture", {})
        self.stage1_ids: dict[str, set[str]] = defaultdict(set)
        for fid, blk in fixtures.items():
            if blk.get("stage", 1) == 1:
                self.stage1_ids[blk.get("backend", "?")].add(fid)
        self.backend_reach = {
            b: set().union(*(self.graph.reach(s) for s in srcs if s in files)) if srcs else set()
            for b, srcs in self.backend_sources.items()
        }
        self.root_src = set()
        for imp in ROOT_IMPORTERS:
            for d in self.graph.edges.get(imp, ()):
                if d.startswith("src/"):
                    self.root_src |= self.graph.reach(d)

    @classmethod
    def from_disk(cls, root: Path = ROOT) -> Repo:
        files: dict[str, str] = {}
        for p in _git_lines(["ls-files", "-co", "--exclude-standard", "--", "src", "tests", "scripts"], root):
            if p.endswith((".py", ".toml")):
                try:
                    files[p] = (root / p).read_text(encoding="utf-8")
                except (OSError, UnicodeDecodeError):
                    continue
        return cls(files)


def select_tests(repo: Repo, changes: list[tuple[str, str]], pyproject_keys: set[str] | None = None) -> Selection:
    """Pick the tests for ``changes`` (``(status, path)`` pairs from ``git diff --name-status``).

    ``pyproject_keys`` is the set of changed keys when ``pyproject.toml`` changed,
    None when it changed and did not parse.
    """
    sel = Selection()
    g = repo.graph
    every_backend = {b for b, r in repo.backend_reach.items() if r}

    def backends_reaching(p: str) -> set[str]:
        return {b for b, r in repo.backend_reach.items() if p in r}

    def add_backends(backs: set[str], reason: str) -> None:
        ids = set().union(*(repo.stage1_ids.get(b, set()) for b in backs))
        sel.add_ids(ids, reason)
        for b in backs:
            d = f"tests/backends/{b.split('_')[0]}/"
            if any(f.startswith(d) for f in repo.files):
                sel.add(d, reason)

    def add_dependents(p: str, reason: str) -> int:
        n = 0
        for d in g.dependents(p):
            if d in ROOT_IMPORTERS or d in FULL_PATHS:
                sel.full_reasons.append(f"{p}: imported by {d}")
                return n + 1
            if d.endswith("/conftest.py"):
                sel.add(d[: -len("conftest.py")], f"{reason} via {d}")
                n += 1
            elif _is_test_file(d):
                sel.add(d, reason)
                n += 1
        return n

    for status, p in changes:
        # A backend source outside src/ (the Dafny oracle's tests/backends/dafny/_helpers.py)
        # is not reached through src/, and the registry loads it with importlib.
        own = {b for b, srcs in repo.backend_sources.items() if p in srcs and not p.startswith("src/")}
        if own:
            add_backends(own, f"{p}: backend source")
        if p in FULL_PATHS or p.startswith("infra/") and p.endswith(".py"):
            sel.full_reasons.append(f"{p}: everything depends on it")
        elif p == "pyproject.toml":
            if pyproject_keys is None:
                sel.full_reasons.append("pyproject.toml: does not parse")
            elif bad := sorted(k for k in pyproject_keys if not _tooling_key(k)):
                sel.full_reasons.append(
                    f"pyproject.toml: key {bad[0]}" + (f" (+{len(bad) - 1})" if len(bad) > 1 else "")
                )
            elif pyproject_keys:
                sel.add(SCRIPTS_TESTS, "pyproject.toml: tooling keys only")
        elif p.startswith("src/"):
            if not p.endswith(".py"):
                sel.add(SCRIPTS_TESTS, f"{p}: non-Python file under src/")
            elif status in ("D", "R") or p not in repo.files:
                sel.full_reasons.append(f"{p}: src module added, deleted or renamed")
            elif p.endswith("/__init__.py"):
                sel.full_reasons.append(f"{p}: package __init__")
            elif p in repo.root_src:
                sel.full_reasons.append(f"{p}: imported by root test infrastructure")
            else:
                backs = backends_reaching(p)
                if every_backend and every_backend <= backs:
                    sel.full_reasons.append(f"{p}: every backend reaches it")
                    continue
                if backs:
                    add_backends(backs, f"{p}: reaches {', '.join(sorted(backs))}")
                add_dependents(p, f"{p}: imports it")
                # Whole-tree generators and text readers of src/ live in tests/scripts/.
                sel.add(SCRIPTS_TESTS, f"{p}: tests/scripts reads src/")
        elif p.startswith(FIXTURES_DIR) and not _is_test_file(p):
            m = re.match(r"tests/backends/fixtures/_cassettes_(\w+)\.py$", p)
            if m:
                add_backends({m.group(1)}, f"{p}: cassette profile")
                sel.add(PII_TEST, f"{p}: cassette profile")
            else:
                sel.full_reasons.append(f"{p}: fixture infrastructure")
        elif re.match(r"tests/backends/cassettes/", p):
            backend = p.split("/")[3] if p.count("/") > 3 else ""
            add_backends({backend} if backend in repo.backend_sources else set(), f"{p}: cassette")
            sel.add(PII_TEST, f"{p}: cassette")
        elif p.startswith("tests/") and p.endswith("conftest.py"):
            sel.add(p[: -len("conftest.py")], f"{p}: conftest scope")
        elif _is_test_file(p):
            if p in repo.files:
                sel.add(p, f"{p}: changed test")
            add_dependents(p, f"{p}: imports it")
        elif p.startswith("tests/") and p.endswith(".py"):
            if add_dependents(p, f"{p}: imports it") == 0:
                sel.add(nearest_test_dir(repo, p), f"{p}: helper with no static importer")
        elif p.startswith("examples/"):
            for t in EXAMPLE_TESTS:
                sel.add(t, f"{p}: example")
            sel.add(SCRIPTS_TESTS, f"{p}: tests/scripts reads examples/")
        elif p.startswith("tests/") and not p.endswith(".md"):
            # Data files read by tests: the nearest folder holding tests. A README is docs (next rule).
            sel.add(nearest_test_dir(repo, p), f"{p}: test data")
        else:
            if p.startswith(DAFNY_ORACLE_DIR):
                add_backends({"dafny"} & repo.backend_sources.keys(), f"{p}: compiled Dafny oracle")
            if p.startswith(KERNEL_ORACLE_DIR):
                sel.add(KERNEL_ORACLE_TESTS, f"{p}: compiled protocol oracle")
            # scripts/, docs, specs, skills, CI files: read by tests/scripts/.
            sel.add(SCRIPTS_TESTS, f"{p}: tests/scripts reads it")
    return sel


# --------------------------------------------------------------------------- members


STEP_ORDER = (
    "preflight",
    "lint",
    "format-check",
    "typecheck",
    "tests",
    "examples",
    "notebooks",
    "check-links",
    "docs-check",
    "docs-build",
)
ALWAYS = frozenset({"preflight", "lint", "format-check", "docs-check", "check-links"})


def plan_steps(paths: list[str], sel: Selection) -> dict[str, str]:
    """Members to run, each with the reason; an absent member is skipped."""
    out: dict[str, str] = {}
    for step in STEP_ORDER:
        reason = ""
        if step in ALWAYS:
            reason = "always"
        elif step == "typecheck":
            reason = next(
                (
                    p
                    for p in paths
                    if p == "pyproject.toml" or p.endswith((".py", ".pyi")) and p.startswith(("src/", "examples/"))
                ),
                "",
            )
        elif step == "tests":
            reason = "" if sel.empty else (FULL if sel.full else "selected")
        elif step == "examples":
            reason = next(
                (
                    p
                    for p in paths
                    if p == "pyproject.toml"
                    or p.startswith("src/")
                    or p.startswith("examples/")
                    and not p.startswith("examples/notebooks/")
                    or p == "tests/scripts/run_examples.py"
                ),
                "",
            )
        elif step == "notebooks":
            reason = next(
                (
                    p
                    for p in paths
                    if p == "pyproject.toml"
                    or p.startswith(("src/", "examples/notebooks/"))
                    or p == "tests/scripts/run_notebooks.py"
                ),
                "",
            )
        elif step == "docs-build":
            reason = next(
                (p for p in paths if p in DOCS_BUILD_FILES or p.startswith(DOCS_BUILD_PREFIXES) or p.endswith(".md")),
                "",
            )
        if reason:
            out[step] = reason
    return out


# --------------------------------------------------------------------------- git state


def _git(args: list[str], root: Path = ROOT, env: dict[str, str] | None = None) -> str:
    return subprocess.run(
        ["git", *args], cwd=root, check=True, capture_output=True, text=True, encoding="utf-8", env=env
    ).stdout


def _git_lines(args: list[str], root: Path = ROOT) -> list[str]:
    return [line for line in _git(args, root).splitlines() if line]


def worktree_tree(root: Path = ROOT) -> str:
    """Tree id of the working tree as it is now, untracked unignored files included.

    Built in a copy of the index, so stat data is reused and the real index is
    never touched.
    """
    index = Path(_git(["rev-parse", "--git-path", "index"], root).strip())
    if not index.is_absolute():
        index = root / index
    tmp = index.with_name("rs-fast-gate.index")
    if index.exists():
        shutil.copyfile(index, tmp)
    env = {**os.environ, "GIT_INDEX_FILE": str(tmp)}
    try:
        _git(["add", "-A", "."], root, env)
        return _git(["write-tree"], root, env).strip()
    finally:
        tmp.unlink(missing_ok=True)


def state_path(root: Path = ROOT) -> Path:
    return _git_path(STATE_NAME, root)


def _interpreter() -> str:
    return f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"


def green_tree(root: Path = ROOT) -> str | None:
    """The tree of the last green run in this checkout, if recorded under this interpreter."""
    try:
        state = json.loads(state_path(root).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if state.get("python") != _interpreter():
        return None
    return state.get("tree")


def record_green(tree: str, root: Path = ROOT) -> None:
    state_path(root).write_text(json.dumps({"tree": tree, "python": _interpreter()}), encoding="utf-8", newline="\n")


def merge_base_tree(root: Path = ROOT) -> str | None:
    for ref in ("origin/master", "master"):
        try:
            return _git(["rev-parse", f"{_git(['merge-base', 'HEAD', ref], root).strip()}^{{tree}}"], root).strip()
        except subprocess.CalledProcessError:
            continue
    return None


def diff_trees(base: str, head: str, root: Path = ROOT) -> list[tuple[str, str]]:
    toks = [
        t for t in _git(["diff-tree", "-r", "--no-renames", "--name-status", "-z", base, head], root).split("\0") if t
    ]
    return [(toks[i], toks[i + 1]) for i in range(0, len(toks) - 1, 2)]


def blob_text(tree: str, path: str, root: Path = ROOT) -> str | None:
    try:
        return _git(["show", f"{tree}:{path}"], root)
    except subprocess.CalledProcessError:
        return None


# --------------------------------------------------------------------------- estimates and commands


def _git_path(name: str, root: Path = ROOT) -> Path:
    p = Path(_git(["rev-parse", "--git-path", name], root).strip())
    return p if p.is_absolute() else root / p


def load_durations(root: Path = ROOT) -> dict[str, float]:
    """Per-test seconds: CI's ``.test_durations_pass1``, overridden by this checkout's own runs.

    CI's file has no ``tests/scripts/`` entries and Linux timings; the local
    record (``record_durations``) fills both gaps after the first run here.
    """
    out: dict[str, float] = {}
    for path in (root / ".test_durations_pass1", _git_path(DURATIONS_NAME, root)):
        try:
            out.update(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            continue
    return out


def junit_durations(xml_text: str, root: Path = ROOT) -> dict[str, float]:
    """Node id -> seconds from a pytest JUnit report; a case whose file cannot be found is dropped."""
    import xml.etree.ElementTree as ET

    out: dict[str, float] = {}
    for case in ET.fromstring(xml_text).iter("testcase"):
        parts = (case.get("classname") or "").split(".")
        for i in range(len(parts), 0, -1):
            path = "/".join(parts[:i]) + ".py"
            if (root / path).is_file():
                node = "::".join([path, *parts[i:], case.get("name") or ""])
                out[node] = float(case.get("time") or 0.0)
                break
    return out


def record_durations(junit: Path, root: Path = ROOT) -> None:
    """Merge one run's JUnit timings into this checkout's duration record; a missing report is skipped."""
    try:
        new = junit_durations(junit.read_text(encoding="utf-8"), root)
    except (OSError, ValueError):
        return
    path = _git_path(DURATIONS_NAME, root)
    try:
        old = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        old = {}
    path.write_text(json.dumps({**old, **new}), encoding="utf-8", newline="\n")


def estimate(sel: Selection, durations: dict[str, float], test_files: list[str]) -> tuple[float, float]:
    """``(selected, suite)`` summed test seconds.

    A test file with no recorded duration (new files, and before the first
    local run every ``tests/scripts/`` file) counts as the median recorded
    file, so an unrecorded directory is not free.
    """
    per_file: dict[str, float] = defaultdict(float)
    picked: dict[str, float] = defaultdict(float)
    ids = list(sel.conformance_ids)
    for node, secs in durations.items():
        path = node.split("::", 1)[0]
        per_file[path] += secs
        if path.startswith(CONFORMANCE) and ids and any(i in node for i in ids):
            picked[path] += secs
    recorded = sorted(per_file.values())
    fallback = recorded[len(recorded) // 2] if recorded else 1.0
    total = chosen = 0.0
    for f in test_files:
        secs = per_file.get(f, fallback)
        total += secs
        if any(f == t or t.endswith("/") and f.startswith(t) for t in sel.targets):
            chosen += secs
        else:
            chosen += picked.get(f, 0.0)
    return chosen, total


def last_failed(root: Path = ROOT) -> list[str]:
    """Test files with a failure in pytest's last-failed cache that the full Stage-1 run collects.

    By file, not node id: a node id that does not collect at Stage 1 (a Stage-2
    parameter, a test renamed since) makes pytest exit 4, and other suites
    (``tests/e2e/``, ``benchmarks/``) write the same cache.
    """
    try:
        data = json.loads((root / ".pytest_cache/v/cache/lastfailed").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    files = {n.split("::", 1)[0] for n in data}
    return sorted(f for f in files if _is_test_file(f) and not f.startswith(E2E) and (root / f).is_file())


def pytest_commands(sel: Selection, serial: bool, junit: Path | None = None, root: Path = ROOT) -> list[list[str]]:
    """Launcher invocations for the selection; conformance by fixture id runs separately, as ``-k`` is global.

    A target that no longer exists (a test directory moved since the last green
    run) is dropped: pytest answers a missing path with a usage error, exit 4.
    """
    base = [sys.executable, "scripts/run_tests.py", "-p", "no:benchmark", "--stage=1"]
    if serial:
        base += ["-n", "0"]
    if junit is not None:
        base.append(f"--junitxml={junit}")
    if sel.full:
        return [base]
    cmds = []
    plain = sorted(t for t in sel.targets if (root / t).exists())
    if plain:
        cmds.append([*base, *plain])
    if sel.conformance_ids and not any(CONFORMANCE.startswith(t) for t in sel.targets):
        cmds.append([*base, CONFORMANCE, "-k", " or ".join(sorted(sel.conformance_ids))])
    return cmds


# --------------------------------------------------------------------------- main


def _print_plan(
    changes: list[tuple[str, str]], base_desc: str, sel: Selection, steps: dict[str, str], share: float | None
) -> None:
    print(f"fast-gate: {len(changes)} changed path(s) since {base_desc}")
    for s, p in changes[:40]:
        print(f"  {s} {p}")
    if len(changes) > 40:
        print(f"  ... {len(changes) - 40} more")
    if sel.full:
        print(
            f"fast-gate: tests FULL ({sel.full_reasons[0]}"
            + (f"; +{len(sel.full_reasons) - 1} more)" if len(sel.full_reasons) > 1 else ")")
        )
    elif not sel.empty:
        share_txt = f", ~{share:.0%} of the suite" if share is not None else ""
        print(f"fast-gate: tests selected{share_txt}")
        for t, r in sorted(sel.targets.items()):
            print(f"  {t}  <- {r}")
        if sel.conformance_ids:
            print(f"  {CONFORMANCE} -k {' or '.join(sorted(sel.conformance_ids))}")
    skipped = [s for s in STEP_ORDER if s not in steps]
    print(f"fast-gate: run {', '.join(steps)}" + (f"; skip {', '.join(skipped)}" if skipped else ""))


def main(argv: list[str] | None = None, root: Path = ROOT) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n", 1)[0])
    ap.add_argument("--plan", action="store_true", help="print the plan and exit")
    ap.add_argument("--full", action="store_true", help="run every member and the full Stage-1 suite")
    ap.add_argument("--base", help="revision to diff against instead of the last green run")
    args = ap.parse_args(argv)
    force_full = args.full or os.environ.get("RS_FAST_GATE", "").lower() == "full"

    head = worktree_tree(root)
    if args.base:
        base, base_desc = _git(["rev-parse", f"{args.base}^{{tree}}"], root).strip(), args.base
    elif (green := green_tree(root)) is not None:
        base, base_desc = green, "the last green run"
    else:
        base, base_desc = merge_base_tree(root), "the merge base with master (no green run recorded)"
    if base is None:
        force_full, base_desc = True, "nothing (no base found)"

    changes = [] if base is None else diff_trees(base, head, root)
    if not changes and not force_full:
        print(f"fast-gate: nothing changed since {base_desc}; nothing to run.")
        return 0

    paths = [p for _, p in changes]
    share: float | None = None
    selected_seconds = 0.0
    if force_full:
        sel = Selection(full_reasons=["--full"])
        steps = {s: "--full" for s in STEP_ORDER}
    else:
        keys = None
        if "pyproject.toml" in paths and base is not None:
            keys = changed_pyproject_keys(
                blob_text(base, "pyproject.toml", root), blob_text(head, "pyproject.toml", root)
            )
        repo = Repo.from_disk(root)
        sel = select_tests(repo, changes, keys)
        if not sel.full and not sel.empty:
            for f in last_failed(root):
                sel.add(f, f"{f}: failed last run")
        steps = plan_steps(paths, sel)
        if "tests" in steps and not sel.full:
            selected_seconds, suite = estimate(sel, load_durations(root), suite_files(repo))
            share = selected_seconds / suite if suite else 1.0
            if share > CUTOFF:
                sel.full_reasons.append(f"selection is ~{share:.0%} of the suite, above {CUTOFF:.0%}")
    _print_plan(changes, base_desc, sel, steps, share)
    if args.plan:
        return 0

    serial = not sel.full and selected_seconds < SERIAL_BELOW_SECONDS
    junit = _git_path(JUNIT_NAME, root)
    for step in STEP_ORDER:
        if step not in steps:
            continue
        cmds = pytest_commands(sel, serial, junit, root) if step == "tests" else [["hatch", "run", step]]
        for cmd in cmds:
            print(f"fast-gate: {step}: {' '.join(cmd)}", flush=True)
            junit.unlink(missing_ok=True)
            rc = subprocess.run(cmd, cwd=root, check=False).returncode
            if step == "tests":
                record_durations(junit, root)
                if rc == NO_TESTS_COLLECTED and not sel.full:
                    # A selection whose every test is deselected (a file marked `live`) has nothing to fail.
                    print("fast-gate: tests: the selection collected no test at Stage 1.", flush=True)
                    rc = 0
            if rc != 0:
                print(f"fast-gate: {step} failed (exit {rc}); later members not run.", flush=True)
                return rc
    if args.base:
        # Only base..worktree was checked; recording would drop green..base from every later run.
        print(f"fast-gate: green against {args.base}; the last green run's record is unchanged.")
        return 0
    record_green(head, root)
    print("fast-gate: green; recorded this tree as the new base.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
