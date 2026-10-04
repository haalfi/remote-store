"""Throwaway RFC-0019 D5 selector: pilot and precision rule sets.

Phase 0 research, not a gate, not shipped. Stdlib only; reads every file from
the commit under test through ``p0tree.Tree``.

Input: a base tree, a head tree, and the changed paths between them.
Output: ``Result`` with ``mode`` FULL (and the reasons) or SELECTED (targets
with the rule behind each, and the D6 jobs).

Variants (plan.md § Selector variants):

- ``pilot``: every layer-1 row plus layer 4's mapped readers; layers 2 and 3
  absent. A ``src/`` path is FULL unless it is a leaf backend module; a
  ``tests/`` or ``scripts/`` module another module imports is FULL (D5 pilot
  cases 1-4).
- ``precision``: layer 1 plus layer 2 (hub-resolved import graph over
  ``src/``, ``tests/``, ``scripts/``, string imports, import-time scan for the
  core list, registry-consumer edges), transitive layer 3, notebook parsing.

Both variants extend layer 4 to every tracked file a test reads, so a path
outside ``CODE_PAT`` contributes its readers instead of FULL (plan.md,
maintainer decision 2026-10-04).

Interpretations the RFC leaves open, each listed in the Phase 0 report:

- I1 ``tests/**/__init__.py`` (other than the fixture package) selects every
  test under its directory, like a conftest without session hooks.
- I2 A non-test module under ``tests/`` (helpers) has no layer-1 selection of
  its own; precision takes its layer-2 dependents, pilot is FULL (case 2).
- I3 A path whose layer 1-4 contributions are all empty runs FULL
  ("no dependents found"): an empty mapping is never an empty selection.
- I4 Reaching ``tests/conftest.py`` or shared fixture infrastructure through
  layer 2 is FULL; reaching another conftest selects its directory; reaching a
  fixture module selects conformance limited to its ids plus its registry
  consumers.
- I5 A core module by import-time effect must be eagerly imported by
  ``remote_store/__init__.py``; a lazily imported module's top level does not
  run in every test.
- I6 Registry consumers are test files; a conftest consumer is covered by the
  backend-dir rule, and a fixture-module import error already fails every
  selected test under ``tests/backends/``.
- I7 The always-run set (non-literal dynamic imports) applies when the diff
  touches ``src/``; D5's "every code change" contradicts D7's e2e-only
  empty-survival seed (``always_run_scope="code"`` restores the wording).
"""

from __future__ import annotations

import fnmatch
import json
import re
import tomllib
from collections import defaultdict
from dataclasses import dataclass, field
from functools import cached_property
from pathlib import Path

from p0tree import Tree, bare_script_name, facts, module_of

HERE = Path(__file__).resolve().parent
RULES_REVISION = "phase0-r1"

CODE_PAT = re.compile(
    r"^(src|tests|examples|scripts)/|^pyproject\.toml$|^\.python-version$|^\.test_durations_pass1$"
    r"|^docs-src/reference/FEATURES\.md$|^docs-src/_data/graph/|^\.github/workflows/|^\.github/actions/"
)

FULL_LITERALS = {
    "tests/conftest.py",
    "tests/_helpers.py",
    "pyproject.toml",
    ".python-version",
    ".test_durations_pass1",
    "scripts/run_tests.py",
}
SHARED_FIXTURE_INFRA = {
    "tests/backends/fixtures/registry.py",
    "tests/backends/fixtures/_loader.py",
    "tests/backends/fixtures/_state.py",
    "tests/backends/fixtures/_live_env.py",
    "tests/backends/fixtures/_cassette_pytest.py",
    "tests/backends/fixtures/__init__.py",
    "tests/backends/fixtures/backends.toml",
}
CONFORMANCE = "tests/backends/conformance/"
FIXTURES_DIR = "tests/backends/fixtures/"
PII_TEST = "tests/backends/fixtures/test_cassettes.py"
EXAMPLE_TESTS = ("tests/test_examples.py", "tests/test_snippets.py", "tests/backends/conformance/test_examples.py")
GENERATED = {
    "FEATURES.md": ("tests/scripts/test_gen_features.py",),
}
GENERATED_PREFIX = {
    "docs-src/_data/graph/": ("tests/scripts/test_gen_graph.py", "tests/scripts/test_gen_graph_viz.py"),
}
PYARROW_JOB_FILES = {
    "tests/backends/s3/test_pyarrow.py",
    "tests/ext/test_arrow.py",
    "tests/ext/test_parquet.py",
    "tests/backends/sqlquery/test_config.py",
    "tests/backends/sqlblob/test_config.py",
}
BACKEND_TEST_DIR = {
    "s3": "tests/backends/s3/",
    "s3_pyarrow": "tests/backends/s3/",
    "s3_boto3": "tests/backends/s3/",
}
CODE_JOBS = [
    "lint",
    "typecheck",
    "prepare-images",
    "test",
    "test-primary",
    "test-primary-sftp",
    "test-cassette-pii",
    "coverage-gate",
    "tooling-tests",
    "pyarrow-major-check",
    "test-cross-platform",
    "notebooks",
    "examples",
    "e2e",
    "package",
]


def is_test_file(p: str) -> bool:
    return p.startswith("tests/") and p.rsplit("/", 1)[-1].startswith("test_") and p.endswith(".py")


# --------------------------------------------------------------------------- per-tree analysis


class Analysis:
    """Import graph, registry facts and derived lists for one tree."""

    def __init__(self, tree: Tree) -> None:
        self.tree = tree
        self.py = [p for p in tree.py_files if p.startswith(("src/", "tests/", "scripts/", "examples/"))]
        self.mod2path: dict[str, str] = {}
        for p in self.py:
            m = module_of(p)
            if m:
                self.mod2path[m] = p
        self.bare: dict[str, str] = {}
        for p in self.py:
            b = bare_script_name(p)
            if b:
                self.bare[b] = p
        # Bare names of .py files anywhere else (sys.path inserts, e.g. sdd/formal).
        self.bare_other: dict[str, set[str]] = defaultdict(set)
        for p in tree.py_files:
            if p.startswith(("src/", "tests/", "examples/")):
                continue
            stem = p.rsplit("/", 1)[-1][:-3]
            if stem not in {"__init__", "conftest"} and not stem.startswith("test_"):
                self.bare_other[stem].add(p)
        self.hubs = {p for p in self.py if p.startswith("src/") and p.endswith("/__init__.py")}

    # ---- import resolution

    def _resolve_hub_name(self, hub: str, name: str, seen: frozenset[str] = frozenset()) -> set[str]:
        if hub in seen:
            return {hub}
        hf = facts(self.tree, hub)
        hub_mod = module_of(hub) or ""
        sub = self.mod2path.get(f"{hub_mod}.{name}")
        if sub:
            return {sub}
        for ref in hf.imports:
            if name in ref.names:
                target_sub = self.mod2path.get(f"{ref.module}.{name}")
                if target_sub:
                    return {target_sub}
                tp = self.mod2path.get(ref.module)
                if tp is None:
                    return set()  # third party
                if tp in self.hubs:
                    return self._resolve_hub_name(tp, name, seen | {hub})
                return {tp}
        if name in hf.defined_names:
            return {hub}
        return self._hub_all(hub)  # fail open: star, getattr, lazy __getattr__

    def _hub_all(self, hub: str) -> set[str]:
        out: set[str] = {hub}
        for ref in facts(self.tree, hub).imports:
            tp = self.mod2path.get(ref.module)
            if tp is None:
                continue
            if ref.names:
                for n in ref.names:
                    s = self.mod2path.get(f"{ref.module}.{n}")
                    out.add(s or tp)
            else:
                out.add(tp)
        return {p for p in out if p not in self.hubs} | {hub}

    def _resolve_dotted(self, dotted: str) -> set[str]:
        """Longest module prefix of ``dotted``, hub-resolving the remainder."""
        parts = dotted.split(".")
        for i in range(len(parts), 0, -1):
            m = ".".join(parts[:i])
            p = self.mod2path.get(m)
            if p is None:
                continue
            if p in self.hubs:
                if i < len(parts):
                    return self._resolve_hub_name(p, parts[i])
                return self._hub_all(p)
            return {p}
        return set()

    @cached_property
    def edges(self) -> dict[str, set[str]]:
        out: dict[str, set[str]] = {}
        for a in self.py:
            out[a] = self._edges_of(a)
        return out

    def _edges_of(self, a: str) -> set[str]:
        f = facts(self.tree, a)
        if not f.parse_ok:
            return set()
        deps: set[str] = set()
        bare_ok = a.startswith(("tests/", "scripts/"))
        aliases: dict[str, str] = {}
        for ref in f.imports:
            if ref.star:
                p = self.mod2path.get(ref.module)
                if p in self.hubs:
                    deps |= self._hub_all(p)
                elif p:
                    deps.add(p)
            if ref.names:
                base = self.mod2path.get(ref.module)
                if base is None and bare_ok:
                    base = self.bare.get(ref.module)
                for n in ref.names:
                    sub = self.mod2path.get(f"{ref.module}.{n}") or (
                        self.bare.get(f"{ref.module}.{n}") if bare_ok else None
                    )
                    if sub:
                        deps.add(sub)
                    elif base in self.hubs:
                        deps |= self._resolve_hub_name(base, n)
                    elif base:
                        deps.add(base)
                if base is None and bare_ok:
                    deps |= self.bare_other.get(ref.module.rsplit(".", 1)[-1], set())
            elif not ref.star:
                p = self.mod2path.get(ref.module)
                if p is None and bare_ok:
                    p = self.bare.get(ref.module)
                    if p is None:
                        deps |= self.bare_other.get(ref.module.rsplit(".", 1)[-1], set())
                if p is None:
                    continue
                if p in self.hubs:
                    aliases[ref.asname or ref.module] = ref.module
                else:
                    deps.add(p)
        for alias, real in aliases.items():
            chains = [c for c in f.attr_chains if c.startswith(alias + ".")]
            if not chains:
                deps |= self._hub_all(self.mod2path[real])
            for c in chains:
                deps |= self._resolve_dotted(real + c[len(alias) :])
        if a.startswith("tests/"):
            for s in f.strings:
                s2 = s.split(":", 1)[0]
                if s2.startswith(("remote_store.", "tests.")) or s2 in ("remote_store",):
                    deps |= self._resolve_dotted(s2)
        if bare_ok:
            for s in f.strings:
                name = s[:-3] if s.endswith(".py") else s
                if name in self.bare:
                    deps.add(self.bare[name])
        deps.discard(a)
        return deps

    @cached_property
    def rev(self) -> dict[str, set[str]]:
        r: dict[str, set[str]] = defaultdict(set)
        for a, ds in self.edges.items():
            for d in ds:
                r[d].add(a)
        return r

    def dependents(self, path: str) -> set[str]:
        """Every module that transitively imports ``path`` (not including it)."""
        seen: set[str] = set()
        todo = [path]
        while todo:
            x = todo.pop()
            for y in self.rev.get(x, ()):
                if y not in seen:
                    seen.add(y)
                    todo.append(y)
        return seen

    def reach(self, path: str) -> set[str]:
        """``path`` plus the src modules it reaches (first hop from any start)."""
        seen = {path}
        todo = [path]
        while todo:
            x = todo.pop()
            for y in self.edges.get(x, ()):
                if y.startswith("src/") and y not in seen:
                    seen.add(y)
                    todo.append(y)
        return seen

    # ---- registry facts

    @cached_property
    def backends(self) -> dict[str, list[str]]:
        raw = tomllib.loads(self.tree.text("tests/backends/fixtures/backends.toml") or "")
        return {
            name: [*b.get("sources", []), *b.get("async_sources", [])] for name, b in raw.get("backend", {}).items()
        }

    @cached_property
    def fixtures_toml(self) -> dict[str, dict]:
        try:
            return tomllib.loads(self.tree.text("tests/backends/fixtures/fixtures.toml") or "").get("fixture", {})
        except tomllib.TOMLDecodeError:
            return {}

    @cached_property
    def ids_by_backend(self) -> dict[str, set[str]]:
        out: dict[str, set[str]] = defaultdict(set)
        for fid, blk in self.fixtures_toml.items():
            out[blk.get("backend", "?")].add(fid)
        return out

    @cached_property
    def module_for(self) -> dict[str, str]:
        """``_MODULE_FOR`` read as a literal dict from the fixture package."""
        import ast

        text = self.tree.text("tests/backends/fixtures/__init__.py") or ""
        for node in ast.walk(ast.parse(text)):
            if isinstance(node, ast.AnnAssign) and getattr(node.target, "id", "") == "_MODULE_FOR":
                return ast.literal_eval(node.value)
            if isinstance(node, ast.Assign) and any(getattr(t, "id", "") == "_MODULE_FOR" for t in node.targets):
                return ast.literal_eval(node.value)
        return {}

    @cached_property
    def ids_by_fixture_module(self) -> dict[str, set[str]]:
        out: dict[str, set[str]] = defaultdict(set)
        for fid in self.fixtures_toml:
            out[f"{FIXTURES_DIR}{self.module_for.get(fid, fid)}.py"].add(fid)
        return out

    @cached_property
    def backend_reach(self) -> dict[str, set[str]]:
        out = {}
        for b, srcs in self.backends.items():
            r: set[str] = set()
            for s in srcs:
                if s in self.tree.files:
                    r |= self.reach(s)
            out[b] = r
        return out

    def backends_reaching(self, path: str) -> set[str]:
        return {b for b, r in self.backend_reach.items() if path in r}

    @cached_property
    def eager(self) -> set[str]:
        """src modules executed by ``import remote_store`` (hub imports followed)."""
        root = "src/remote_store/__init__.py"
        seen = {root}
        todo = [root]
        while todo:
            x = todo.pop()
            f = facts(self.tree, x)
            for ref in f.top_imports:
                p = self.mod2path.get(ref.module)
                targets = set()
                if p:
                    targets.add(p)
                for n in ref.names:
                    s = self.mod2path.get(f"{ref.module}.{n}")
                    if s:
                        targets.add(s)
                for t in targets:
                    if t.startswith("src/") and t not in seen:
                        seen.add(t)
                        todo.append(t)
        return seen

    @cached_property
    def core(self) -> dict[str, str]:
        """Core-module list (layer 1): path -> reason."""
        out: dict[str, str] = {}
        all_b = [b for b, r in self.backend_reach.items() if r]
        for p in self.py:
            if not p.startswith("src/") or p in self.hubs:
                continue
            if all(p in self.backend_reach[b] for b in all_b):
                out[p] = "every backend reaches it"
            elif p in self.eager and p not in self.hubs:
                eff = facts(self.tree, p).top_effects
                if eff:
                    out[p] = "import-time effect: " + eff[0]
        return out

    @cached_property
    def top_effect_modules(self) -> dict[str, list[str]]:
        return {
            p: facts(self.tree, p).top_effects
            for p in self.py
            if p.startswith("src/") and p not in self.hubs and facts(self.tree, p).top_effects
        }

    @cached_property
    def registry_consumers(self) -> set[str]:
        """Test files outside conformance and the fixture package that read the
        registry (I6: conftests are not targets; a conftest consumer's directory
        is selected by the backend-dir rule, and an import error in any fixture
        module already fails every selected test under ``tests/backends/``)."""
        out = set()
        for p in self.py:
            if not is_test_file(p) or p.startswith(FIXTURES_DIR) or p.startswith(CONFORMANCE):
                continue
            f = facts(self.tree, p)
            if f.registry_calls or any(
                r.module in ("tests.backends.fixtures", "tests.backends.fixtures.registry") for r in f.imports
            ):
                out.add(p)
        return out

    @cached_property
    def os_sensitive_files(self) -> set[str]:
        return {p for p in self.py if is_test_file(p) and facts(self.tree, p).os_sensitive}

    @cached_property
    def os_sensitive_ids(self) -> set[str]:
        out = set()
        for mod, ids in self.ids_by_fixture_module.items():
            if facts(self.tree, mod).os_sensitive:
                out |= ids
        return out

    @cached_property
    def always_run(self) -> set[str]:
        return {p for p in self.py if is_test_file(p) and facts(self.tree, p).dyn_nonliteral}

    def importers_other_than_own_test(self, path: str) -> set[str]:
        own = mapped_script_test(path)
        return {a for a in self.rev.get(path, ()) if a != own and a != path}

    def example_reach(self) -> set[str]:
        out: set[str] = set()
        for p in self.py:
            if p.startswith("examples/") and not p.startswith("examples/notebooks/"):
                for d in self.edges.get(p, ()):
                    if d.startswith("src/"):
                        out |= self.reach(d)
        return out

    @cached_property
    def notebook_reach(self) -> set[str]:
        out: set[str] = set()
        for p in self.tree.files:
            if not (p.startswith("examples/notebooks/") and p.endswith(".ipynb")):
                continue
            try:
                nb = json.loads(self.tree.text(p) or "{}")
            except json.JSONDecodeError:
                continue
            for cell in nb.get("cells", []):
                if cell.get("cell_type") != "code":
                    continue
                src = "".join(cell.get("source", []))
                for m in re.finditer(r"^\s*(?:from\s+([\w.]+)\s+import\s+([\w, ]+)|import\s+([\w.]+))", src, re.M):
                    mod = m.group(1) or m.group(3)
                    if not mod.startswith("remote_store"):
                        continue
                    names = [n.strip() for n in (m.group(2) or "").split(",") if n.strip()]
                    targets = self._resolve_dotted(mod) if not names else set()
                    for n in names:
                        targets |= self._resolve_dotted(f"{mod}.{n}")
                    for t in targets:
                        out |= self.reach(t)
        return out

    @cached_property
    def examples_reach(self) -> set[str]:
        return self.example_reach()


def mapped_script_test(path: str) -> str | None:
    if not (path.startswith("scripts/") and path.endswith(".py")):
        return None
    stem = path.rsplit("/", 1)[-1][:-3].lstrip("_")
    return f"tests/scripts/test_{stem}.py"


_ANALYSES: dict[str | None, Analysis] = {}


def analysis(tree: Tree) -> Analysis:
    key = tree.rev if tree.rev is not None else f"disk:{tree.disk_root}"
    if key not in _ANALYSES:
        _ANALYSES[key] = Analysis(tree)
    return _ANALYSES[key]


# --------------------------------------------------------------------------- layer 4


class Readers:
    """Layer-4 table: repo path / scanned dir / subprocess target -> readers.

    A reader is a test file, or ``dir:<d>/`` for a conftest scope.
    """

    def __init__(self, data: dict) -> None:
        self.reads: dict[str, set[str]] = {k: set(v) for k, v in data.get("reads", {}).items()}
        self.scans: dict[str, set[str]] = {k: set(v) for k, v in data.get("scans", {}).items()}

    @classmethod
    def load(cls, path: Path | None = None) -> Readers:
        path = path or HERE / "readers.json"
        if not path.exists():
            return cls({})
        return cls(json.loads(path.read_text(encoding="utf-8")))

    def for_path(self, path: str, base: Tree) -> set[str]:
        out = set(self.reads.get(path, ()))
        parent = path.rsplit("/", 1)[0] if "/" in path else "."
        while parent not in base.dirs and parent != "." and "/" in parent:
            parent = parent.rsplit("/", 1)[0]
        if parent not in base.dirs and "/" not in parent:
            parent = parent if parent in base.dirs else "."
        out |= self.scans.get(parent, set())
        for pat, rs in self.scans.items():
            if "*" in pat and fnmatch.fnmatch(path, pat):
                out |= rs
        return out


# --------------------------------------------------------------------------- result


@dataclass
class Result:
    variant: str
    mode: str = "SELECTED"
    full_reasons: list[str] = field(default_factory=list)
    # target path (file or dir/) -> allowlist of fixture ids (None = unrestricted)
    targets: dict[str, set[str] | None] = field(default_factory=dict)
    why: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))
    jobs: dict[str, str] = field(default_factory=dict)
    changed: list[str] = field(default_factory=list)
    rules_revision: str = RULES_REVISION

    def full(self, reason: str) -> None:
        self.mode = "FULL"
        self.full_reasons.append(reason)

    def add(self, target: str, rule: str, allow: set[str] | None = None) -> None:
        if target in self.targets:
            cur = self.targets[target]
            self.targets[target] = None if (cur is None or allow is None) else cur | allow
        else:
            self.targets[target] = None if allow is None else set(allow)
        self.why[target].add(rule)

    def to_json(self) -> dict:
        return {
            "variant": self.variant,
            "mode": self.mode,
            "full_reasons": self.full_reasons,
            "targets": {k: (sorted(v) if v is not None else None) for k, v in sorted(self.targets.items())},
            "why": {k: sorted(v) for k, v in sorted(self.why.items())},
            "jobs": self.jobs,
            "changed": self.changed,
            "rules_revision": self.rules_revision,
        }


# --------------------------------------------------------------------------- selection


def changed_paths(base_rev: str, head_rev: str) -> list[tuple[str, str]]:
    from p0tree import git

    out = git("diff", "--name-status", "--no-renames", "-z", base_rev, head_rev)
    toks = [t for t in out.split("\0") if t]
    return [(toks[i], toks[i + 1]) for i in range(0, len(toks) - 1, 2)]


def _conftest_hooks(base: Tree, head: Tree, p: str) -> set[str]:
    hooks: set[str] = set()
    for t in (base, head):
        if p in t.files:
            f = facts(t, p)
            if not f.parse_ok:
                hooks.add("unparseable")
            hooks |= f.session_hooks
    return hooks


def _changed_fixture_ids(base: Tree, head: Tree) -> set[str] | None:
    try:
        a = tomllib.loads(base.text("tests/backends/fixtures/fixtures.toml") or "").get("fixture", {})
        b = tomllib.loads(head.text("tests/backends/fixtures/fixtures.toml") or "").get("fixture", {})
    except tomllib.TOMLDecodeError:
        return None
    return {k for k in set(a) | set(b) if a.get(k) != b.get(k)}


def select(
    base: Tree,
    head: Tree,
    changes: list[tuple[str, str]],
    variant: str,
    readers: Readers | None = None,
    literal: bool = False,
    always_run_scope: str = "src",
) -> Result:
    readers = readers or Readers.load()
    res = Result(variant=variant, changed=[f"{s}\t{p}" for s, p in changes])
    A_head, A_base = analysis(head), analysis(base)
    precision = variant == "precision"
    jobs_extra: set[str] = set()
    pii = False

    def tree_for(p: str) -> Tree:
        return head if p in head.files else base

    def A_for(p: str) -> Analysis:
        return A_head if p in head.files else A_base

    def registry_consumer_targets(backs: set[str], rule: str) -> None:
        for b in backs:
            d = BACKEND_TEST_DIR.get(b, f"tests/backends/{b}/")
            if d.rstrip("/") in head.dirs:
                res.add(d, rule)
        for c in A_head.registry_consumers | A_base.registry_consumers:
            res.add(c, rule + " (registry consumer)")

    def layer2(p: str, rule: str, allow: set[str] | None) -> int:
        """Dependents of ``p`` in base and head; returns how many targets it added."""
        n = 0
        deps = A_head.dependents(p) | A_base.dependents(p)
        for d in deps:
            if d == "tests/conftest.py":
                res.full(f"{p}: reaches tests/conftest.py (layer 2)")
                return n + 1
            if d in SHARED_FIXTURE_INFRA:
                res.full(f"{p}: reaches fixture infrastructure {d} (layer 2)")
                return n + 1
            if d.endswith("/conftest.py"):
                res.add(d[: -len("conftest.py")], f"{rule}: via {d}")
                n += 1
            elif d.startswith(FIXTURES_DIR) and d in A_for(d).ids_by_fixture_module:
                ids = A_for(d).ids_by_fixture_module[d]
                res.add(CONFORMANCE, f"{rule}: via fixture module {d}", ids)
                res.add(FIXTURES_DIR, f"{rule}: via fixture module {d}")
                registry_consumer_targets({A_for(d).fixtures_toml[i].get("backend") for i in ids}, rule)
                n += 1
            elif is_test_file(d):
                res.add(d, rule, allow if d.startswith(CONFORMANCE) else None)
                n += 1
        return n

    for status, p in changes:
        A = A_for(p)
        contributed = 0
        readers_of = readers.for_path(p, base)
        for r in readers_of:
            if r == "dir:tests/":
                res.full(f"{p}: read by the root conftest (layer 4)")
            elif r.startswith("dir:"):
                res.add(r[4:], f"{p}: layer 4 reader (conftest scope)")
            else:
                res.add(r, f"{p}: layer 4 reader")
            contributed += 1
        is_code = bool(CODE_PAT.search(p))

        # ---- layer 1, first matching row
        if p in FULL_LITERALS or p.startswith(".github/"):
            res.full(f"{p}: FULL row")
            continue
        if p.startswith("src/") and p.endswith("/__init__.py"):
            res.full(f"{p}: package __init__ (re-export hub)")
            continue
        if precision and p in A_head.core:
            res.full(f"{p}: core module ({A_head.core[p]})")
            continue
        if precision and p in A_base.core:
            res.full(f"{p}: core module ({A_base.core[p]})")
            continue
        if p in SHARED_FIXTURE_INFRA:
            res.full(f"{p}: shared fixture infrastructure")
            continue
        if p.startswith("tests/") and p.endswith("conftest.py"):
            hooks = _conftest_hooks(base, head, p)
            if hooks:
                res.full(f"{p}: conftest with session-wide hook ({', '.join(sorted(hooks))})")
            else:
                res.add(p[: -len("conftest.py")], f"{p}: conftest scope")
            continue
        if p.startswith("tests/") and p.endswith("/__init__.py"):  # I1
            res.add(p[: -len("__init__.py")], f"{p}: test package __init__ (I1)")
            continue
        if p.startswith("src/") and p.endswith(".py"):
            if not precision:
                leaf = _pilot_leaf(A_head, A_base, p)
                if leaf is None:
                    res.full(f"{p}: src module, not a leaf backend module (pilot)")
                    continue
                backs, ids = leaf
                res.add(CONFORMANCE, f"{p}: leaf backend module (pilot)", ids)
                for b in backs:
                    res.add(BACKEND_TEST_DIR.get(b, f"tests/backends/{b}/"), f"{p}: leaf backend module (pilot)")
                continue
            backs = A_head.backends_reaching(p) | A_base.backends_reaching(p)
            allow: set[str] | None = None
            if backs:
                all_b = {b for b, r in A_head.backend_reach.items() if r}
                if all_b <= backs:
                    res.full(f"{p}: reaches every backend (layer 3)")
                    continue
                allow = set().union(*(A_head.ids_by_backend.get(b, set()) for b in backs))
                res.add(CONFORMANCE, f"{p}: layer 3 backends {sorted(backs)}", allow)
                for b in backs:
                    d = BACKEND_TEST_DIR.get(b, f"tests/backends/{b}/")
                    if d.rstrip("/") in head.dirs:
                        res.add(d, f"{p}: layer 3 backend {b}")
                contributed += 1
            contributed += layer2(p, f"{p}: layer 2", allow)
            if p in A_head.examples_reach or p in A_base.examples_reach:
                jobs_extra.add("examples")
            if p in A_head.notebook_reach or p in A_base.notebook_reach:
                jobs_extra.add("notebooks")
            if status in ("A", "D"):
                jobs_extra.add("package")
            if contributed == 0:
                res.full(f"{p}: no dependents found (I3)")
            continue
        if is_test_file(p):
            if not precision and A.importers_other_than_own_test(p):
                res.full(f"{p}: test module imported by another module (pilot case 2)")
                continue
            res.add(p, f"{p}: test file")
            if precision:
                layer2(p, f"{p}: layer 2 (test module imported)", None)
            if p == PII_TEST:
                pii = True
            continue
        m = re.match(r"tests/(?:.*/)?cassettes/([^/]+)/", p)
        if m:
            b = m.group(1)
            replay = {
                i for i, blk in A_head.fixtures_toml.items() if blk.get("backend") == b and blk.get("kind") == "replay"
            }
            res.add(CONFORMANCE, f"{p}: cassette ({b} replay)", replay)
            res.add(BACKEND_TEST_DIR.get(b, f"tests/backends/{b}/"), f"{p}: cassette backend dir")
            res.add(PII_TEST, f"{p}: PII sweep")
            pii = True
            continue
        if re.match(r"tests/backends/fixtures/_cassettes\w*\.py$", p):
            if not precision:
                res.full(f"{p}: _cassettes row (FULL in the pilot)")
                continue
            prof = re.match(r"tests/backends/fixtures/_cassettes_(\w+)\.py$", p)
            b = prof.group(1) if prof else None
            replay = {
                i
                for i, blk in A_head.fixtures_toml.items()
                if blk.get("kind") == "replay" and (b is None or blk.get("backend") == b)
            }
            res.add(FIXTURES_DIR, f"{p}: _cassettes row")
            res.add(CONFORMANCE, f"{p}: _cassettes row (replay fixtures)", replay)
            if b:
                res.add(BACKEND_TEST_DIR.get(b, f"tests/backends/{b}/"), f"{p}: _cassettes row backend dir")
            layer2(p, f"{p}: layer 2 (_cassettes importer)", None)
            pii = True
            continue
        if p.startswith(FIXTURES_DIR) and p.endswith(".py") and not is_test_file(p):
            ids = A_head.ids_by_fixture_module.get(p) or A_base.ids_by_fixture_module.get(p)
            if ids:
                if not precision:
                    res.full(f"{p}: fixture module (FULL in the pilot)")
                    continue
                res.add(CONFORMANCE, f"{p}: fixture module ids", ids)
                res.add(FIXTURES_DIR, f"{p}: fixture module")
                registry_consumer_targets({A_head.fixtures_toml.get(i, {}).get("backend") for i in ids} - {None}, p)
                layer2(p, f"{p}: layer 2", None)
                continue
        if p == "tests/backends/fixtures/fixtures.toml":
            if not precision:
                res.full(f"{p}: fixtures.toml (FULL in the pilot)")
                continue
            ids = _changed_fixture_ids(base, head)
            if ids is None:
                res.full(f"{p}: fixtures.toml does not parse")
                continue
            res.add(CONFORMANCE, f"{p}: changed fixture blocks", ids)
            res.add(FIXTURES_DIR, f"{p}: fixtures.toml")
            backs = {(A_head.fixtures_toml.get(i) or A_base.fixtures_toml.get(i) or {}).get("backend") for i in ids}
            registry_consumer_targets(backs - {None}, p)
            continue
        if p.startswith("examples/notebooks/"):
            jobs_extra.add("notebooks")
            continue
        if p.startswith("examples/"):
            jobs_extra.add("examples")
            for et in EXAMPLE_TESTS:
                res.add(et, f"{p}: examples row")
            continue
        if p in ("tests/scripts/run_examples.py", "tests/scripts/run_notebooks.py"):
            jobs_extra.add("examples" if "examples" in p else "notebooks")
            if not precision:
                res.full(f"{p}: runner row (FULL in the pilot)")
                continue
            layer2(p, f"{p}: layer 2", None)
            continue
        if p.startswith("scripts/") and p.endswith(".py"):
            own = mapped_script_test(p)
            if own not in head.files and own not in base.files:
                res.full(f"{p}: script with no mapped test ({own})")
                continue
            if not precision:
                other = A_head.importers_other_than_own_test(p) | A_base.importers_other_than_own_test(p)
                if other:
                    res.full(f"{p}: script imported by {sorted(other)[0]} (pilot case 2)")
                    continue
            res.add(own, f"{p}: mapped script test")
            if precision:
                layer2(p, f"{p}: layer 2 (script imported)", None)
            continue
        if p in GENERATED:
            for g in GENERATED[p]:
                res.add(g, f"{p}: generated artifact")
            continue
        gp = next((k for k in GENERATED_PREFIX if p.startswith(k)), None)
        if gp:
            for g in GENERATED_PREFIX[gp]:
                res.add(g, f"{p}: generated artifact")
            continue
        if p.startswith("tests/") and p.endswith(".py"):  # I2: helper module
            if not precision and (A.rev.get(p) or A_base.rev.get(p)):
                res.full(f"{p}: tests/ module imported by another module (pilot case 2)")
                continue
            n = layer2(p, f"{p}: layer 2 (helper)", None)
            if n + contributed == 0:
                res.full(f"{p}: no dependents found (I3)")
            continue
        if not is_code and literal:
            res.full(f"{p}: non-code path, unmatched (D5 as written)")
            continue
        if not is_code:
            # Non-code-class path: readers only (plan.md decision). A .py file
            # outside the importable roots also selects its bare-name importers.
            if p.endswith(".py"):
                stem = p.rsplit("/", 1)[-1][:-3]
                for a in (A_head, A_base):
                    for imp, deps in a.edges.items():
                        if p in deps:
                            for d in {imp} | a.dependents(imp):
                                if is_test_file(d):
                                    res.add(d, f"{p}: bare import of {stem}")
            continue
        res.full(f"{p}: unmatched (layer 1)")

    if res.mode == "FULL":
        res.targets.clear()
        res.jobs = {j: "FULL" for j in CODE_JOBS}
        return res

    # Always-run set (dynamic imports with a non-literal argument). I7: applied
    # when the diff touches src/, whose modules are what those imports load;
    # D5 says "every code change", which contradicts D7's e2e-only
    # empty-survival seed. ``always_run_scope="code"`` restores the wording.
    trigger = (lambda p: CODE_PAT.search(p)) if always_run_scope == "code" else (lambda p: p.startswith("src/"))
    if precision and any(trigger(p) for _, p in changes):
        for a in A_head.always_run:
            res.add(a, "dynamic import target not a literal (always-run)")

    res.jobs = _jobs(res, A_head, changes, jobs_extra, pii)
    return res


def _pilot_leaf(A_head: Analysis, A_base: Analysis, p: str) -> tuple[set[str], set[str]] | None:
    for A in (A_head, A_base):
        backs = {b for b, srcs in A.backends.items() if p in srcs}
        if not backs:
            return None
        if any(a.startswith("src/") for a in A.rev.get(p, ())):
            return None
        dirs = [BACKEND_TEST_DIR.get(b, f"tests/backends/{b}/") for b in backs]
        for a in A.rev.get(p, ()):
            if not any(a.startswith(d) for d in dirs):
                return None
    backs = {b for b, srcs in A_head.backends.items() if p in srcs}
    ids = set().union(*(A_head.ids_by_backend.get(b, set()) for b in backs))
    return backs, ids


def covers(k: str, f: str) -> bool:
    """Target ``k`` (file or ``dir/``) includes path ``f``."""
    return k == f or (k.endswith("/") and f.startswith(k))


def overlaps(k: str, d: str) -> bool:
    """Target ``k`` and directory ``d`` (``dir/``) share a test."""
    return k.startswith(d) or (k.endswith("/") and d.startswith(k))


def _jobs(res: Result, A: Analysis, changes, extra: set[str], pii: bool) -> dict[str, str]:
    """D6 fast-lane job rules, with per-job survival at file granularity."""
    t = res.targets
    jobs = {"lint": "always", "typecheck": "always"}
    keys = list(t)
    stage1 = [
        k
        for k in keys
        if k.startswith("tests/") and not overlaps(k, "tests/scripts/") and not overlaps(k, "tests/e2e/")
    ]
    stage1 += [k for k in keys if k == "tests/" or (k.endswith("/") and "tests/scripts/".startswith(k))]
    if stage1:
        jobs["test"] = "selected tests outside tests/scripts"
        jobs["test-primary"] = "selected tests outside tests/scripts"
    conf = [k for k in keys if overlaps(k, CONFORMANCE)]
    unrestricted = any(t[k] is None for k in conf)
    allow = set().union(*(t[k] for k in conf if t[k] is not None)) if conf else set()
    # -k sftp_docker survives only in conformance files with sync backend cells.
    sftp_files = [
        f for f in A.py if is_test_file(f) and f.startswith(CONFORMANCE) and facts(A.tree, f).sync_backend_cells
    ]
    if any(covers(k, f) and (t[k] is None or "sftp_docker" in t[k]) for k in keys for f in sftp_files):
        jobs["test-primary-sftp"] = "selected conformance file with sync backend cells, sftp_docker allowed"
    if pii or any(covers(k, PII_TEST) for k in keys):
        jobs["test-cassette-pii"] = "PII sweep selected"
    if any(overlaps(k, "tests/scripts/") for k in keys):
        jobs["tooling-tests"] = "selected tests/scripts"
    if any(covers(k, f) for k in keys for f in PYARROW_JOB_FILES):
        jobs["pyarrow-major-check"] = "its test files selected"
    osx = any(covers(k, f) for k in keys for f in A.os_sensitive_files if not f.startswith("tests/e2e/"))
    if not osx and conf:
        osx = unrestricted or bool(allow & A.os_sensitive_ids)
    if osx:
        jobs["test-cross-platform"] = "os_sensitive test selected"
    if any(overlaps(k, "tests/e2e/") for k in keys):
        jobs["e2e"] = "tests/e2e selected"
    for j in extra:
        jobs[j] = "path rule"
    if any(s in ("A", "D") and p.startswith("src/") for s, p in changes):
        jobs["package"] = "src file added or deleted"
    if any(j in jobs for j in ("test-primary", "test-primary-sftp", "e2e")):
        jobs["prepare-images"] = "needed by a selected job"
    return jobs


def main() -> None:
    import argparse

    from p0tree import git

    ap = argparse.ArgumentParser(description="RFC-0019 Phase 0 throwaway selector")
    ap.add_argument("base")
    ap.add_argument("head", help="a revision, or WORKTREE for the files on disk")
    ap.add_argument("--variant", choices=["pilot", "precision"], default="precision")
    ap.add_argument("--explain", action="store_true")
    a = ap.parse_args()
    base = Tree(a.base)
    if a.head == "WORKTREE":
        head = Tree(None)
        out = git("diff", "--name-status", "--no-renames", "-z", a.base)
        toks = [x for x in out.split("\0") if x]
        changes = [(toks[i], toks[i + 1]) for i in range(0, len(toks) - 1, 2)]
    else:
        head = Tree(a.head)
        changes = changed_paths(a.base, a.head)
    r = select(base, head, changes, a.variant)
    out_json = r.to_json()
    if not a.explain:
        out_json.pop("why")
    print(json.dumps(out_json, indent=1))


if __name__ == "__main__":
    main()
