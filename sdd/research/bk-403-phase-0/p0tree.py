"""Repository snapshots and static facts for the RFC-0019 Phase 0 selector.

Throwaway research, not a gate. Stdlib only (D7: the selector never imports
project modules). A ``Tree`` is the set of tracked files at one commit (or the
working tree) with their bytes; ``Facts`` are the per-file AST facts the
selector needs, cached by blob content so a replay over many commits parses
each distinct file once.
"""

from __future__ import annotations

import ast
import hashlib
import subprocess
from dataclasses import dataclass, field
from functools import cached_property
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def git(*args: str, cwd: Path = ROOT) -> str:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True).stdout


class _CatFile:
    """One persistent ``git cat-file --batch`` process."""

    def __init__(self) -> None:
        self.p = subprocess.Popen(
            ["git", "cat-file", "--batch"], cwd=ROOT, stdin=subprocess.PIPE, stdout=subprocess.PIPE
        )

    def read(self, spec: str) -> bytes | None:
        assert self.p.stdin
        assert self.p.stdout
        self.p.stdin.write(spec.encode() + b"\n")
        self.p.stdin.flush()
        header = self.p.stdout.readline().split()
        if len(header) < 3 or header[1] == b"missing":
            return None
        size = int(header[2])
        data = self.p.stdout.read(size)
        self.p.stdout.read(1)
        return data


_CAT: _CatFile | None = None


def cat() -> _CatFile:
    global _CAT
    if _CAT is None:
        _CAT = _CatFile()
    return _CAT


class Tree:
    """Tracked files and contents at a git revision, or on disk (``rev=None``)."""

    def __init__(self, rev: str | None, disk_root: Path = ROOT) -> None:
        self.rev = rev
        self.disk_root = disk_root
        if rev is None:
            out = git("ls-files", "-z", cwd=disk_root)
            self.files = frozenset(p for p in out.split("\0") if p and (disk_root / p).exists())
        else:
            out = git("ls-tree", "-r", "-z", "--name-only", rev)
            self.files = frozenset(p for p in out.split("\0") if p)
        self._cache: dict[str, bytes | None] = {}

    def read(self, path: str) -> bytes | None:
        if path not in self._cache:
            if path not in self.files:
                self._cache[path] = None
            elif self.rev is None:
                self._cache[path] = (self.disk_root / path).read_bytes()
            else:
                self._cache[path] = cat().read(f"{self.rev}:{path}")
        return self._cache[path]

    def text(self, path: str) -> str | None:
        b = self.read(path)
        return None if b is None else b.decode("utf-8", errors="replace")

    @cached_property
    def dirs(self) -> frozenset[str]:
        out: set[str] = set()
        for f in self.files:
            parts = f.split("/")[:-1]
            for i in range(1, len(parts) + 1):
                out.add("/".join(parts[:i]))
        return frozenset(out)

    @cached_property
    def py_files(self) -> list[str]:
        return sorted(f for f in self.files if f.endswith(".py"))


class OverlayTree(Tree):
    """A tree with some files replaced, added (bytes) or deleted (None)."""

    def __init__(self, base: Tree, overrides: dict[str, bytes | None]) -> None:
        self.rev = f"{base.rev}+overlay{hash(frozenset(overrides.items()))}"
        self.disk_root = base.disk_root
        self._base = base
        self._over = overrides
        self.files = frozenset(
            {f for f in base.files if overrides.get(f, b"") is not None}
            | {f for f, v in overrides.items() if v is not None}
        )
        self._cache = {}

    def read(self, path: str) -> bytes | None:
        if path in self._over:
            return self._over[path]
        return self._base.read(path)


# --------------------------------------------------------------------------- module names


def module_of(path: str) -> str | None:
    """Dotted module name a tracked ``.py`` file is importable as."""
    if not path.endswith(".py"):
        return None
    p = path[:-3]
    if p.startswith("src/"):
        p = p[4:]
    elif not p.startswith(("tests/", "examples/", "scripts/")):
        return None
    if p.endswith("/__init__"):
        p = p[: -len("/__init__")]
    return p.replace("/", ".")


def bare_script_name(path: str) -> str | None:
    """Name a ``scripts/`` module is imported by after ``sys.path`` gets ``scripts``."""
    if path.startswith("scripts/") and path.endswith(".py"):
        p = path[len("scripts/") : -3]
        if p.endswith("/__init__"):
            p = p[: -len("/__init__")]
        return p.replace("/", ".")
    return None


# --------------------------------------------------------------------------- per-file facts

SESSION_HOOKS = {
    "pytest_configure",
    "pytest_unconfigure",
    "pytest_sessionstart",
    "pytest_sessionfinish",
    "pytest_collection_modifyitems",
}
DYN_IMPORT_FUNCS = {"import_module", "__import__", "importorskip"}
REGISTRY_FUNCS = {"all_fixtures", "fixture_params", "fixtures", "fixture_params_concurrent"}


@dataclass
class ImportRef:
    module: str  # absolute dotted module as written (relative resolved)
    names: tuple[str, ...]  # for ``from module import a, b``; () for ``import module``
    star: bool = False
    asname: str | None = None  # ``import module as asname``


@dataclass
class FileFacts:
    parse_ok: bool
    imports: list[ImportRef] = field(default_factory=list)
    strings: set[str] = field(default_factory=set)
    attr_chains: set[str] = field(default_factory=set)  # e.g. "remote_store.Store"
    dyn_nonliteral: bool = False
    session_hooks: set[str] = field(default_factory=set)
    os_sensitive: bool = False
    registry_calls: bool = False
    top_effects: list[str] = field(default_factory=list)
    defined_names: set[str] = field(default_factory=set)
    top_imports: list[ImportRef] = field(default_factory=list)  # run at import time
    sync_backend_cells: bool = False  # a test takes ``backend`` or calls ``fixture_params(``


def _resolve_rel(mod: str | None, level: int, this_module: str, is_pkg: bool) -> str:
    if level == 0:
        return mod or ""
    parts = this_module.split(".")
    base = parts if is_pkg else parts[:-1]
    if level > 1:
        base = base[: len(base) - (level - 1)]
    return ".".join([*base, mod] if mod else base)


def _chain(node: ast.AST) -> str | None:
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return ".".join(reversed(parts))
    return None


def _is_type_checking(test: ast.AST) -> bool:
    return (isinstance(test, ast.Name) and test.id == "TYPE_CHECKING") or (
        isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING"
    )


def _top_effects(tree: ast.Module) -> list[str]:
    """Top-level statements that do more than define names (layer 2, core list).

    Allowed without effect: imports, def/class, docstrings, ``__all__``,
    assignments whose value is a literal, a name, an attribute, a subscript of
    those, a lambda, or a call that only constructs a value (no call to
    ``register*``, ``patch*``, ``setattr``, ``os.environ``/``getenv``,
    ``sys.*`` mutation); ``if TYPE_CHECKING`` and ``try: import`` blocks.
    """
    out: list[str] = []

    def call_names(n: ast.AST) -> list[str]:
        return [c for c in (_chain(x.func) for x in ast.walk(n) if isinstance(x, ast.Call)) if c]

    def effectful_calls(n: ast.AST) -> list[str]:
        bad = []
        for c in call_names(n):
            last = c.rsplit(".", 1)[-1]
            if (
                last.startswith(("register", "patch", "install", "setdefault", "add_audit"))
                or last in {"setattr", "getenv", "putenv", "filterwarnings", "simplefilter", "basicConfig", "seed"}
                or c.startswith(("os.environ", "sys.", "warnings.", "atexit.", "logging.basicConfig"))
            ):
                bad.append(c)
        for x in ast.walk(n):
            if isinstance(x, ast.Subscript) and _chain(x.value) == "os.environ":
                bad.append("os.environ[]")
        return bad

    def visit(stmts: list[ast.stmt]) -> None:
        for s in stmts:
            if isinstance(s, (ast.Import, ast.ImportFrom, ast.FunctionDef, ast.AsyncFunctionDef, ast.Pass)):
                continue
            if isinstance(s, ast.ClassDef):
                bad = [c for d in s.decorator_list for c in call_names(d) if "register" in c]
                if bad:
                    out.append(f"line {s.lineno}: class decorator {bad[0]}")
                continue
            if isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant):
                continue
            if isinstance(s, ast.If):
                if _is_type_checking(s.test):
                    continue
                visit(s.body)
                visit(s.orelse)
                continue
            if isinstance(s, ast.Try):
                visit(s.body)
                for h in s.handlers:
                    visit(h.body)
                visit(s.orelse)
                visit(s.finalbody)
                continue
            if isinstance(s, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
                targets = s.targets if isinstance(s, ast.Assign) else [s.target]
                if any(isinstance(t, (ast.Attribute, ast.Subscript)) for t in targets):
                    out.append(f"line {s.lineno}: assigns to {ast.unparse(targets[0])[:60]}")
                    continue
                if s.value is not None:
                    bad = effectful_calls(s.value)
                    if bad:
                        out.append(f"line {s.lineno}: calls {bad[0]}")
                continue
            if isinstance(s, ast.Expr) and isinstance(s.value, ast.Call):
                out.append(f"line {s.lineno}: top-level call {_chain(s.value.func) or ast.unparse(s.value.func)[:40]}")
                continue
            if isinstance(s, (ast.For, ast.While, ast.With, ast.AsyncFor, ast.AsyncWith, ast.Delete)):
                out.append(f"line {s.lineno}: top-level {type(s).__name__}")
                continue
            if isinstance(s, (ast.Expr, ast.Assert, ast.Raise, ast.Global, ast.Nonlocal)):
                continue
            out.append(f"line {s.lineno}: top-level {type(s).__name__}")

    visit(tree.body)
    return out


_FACTS: dict[str, FileFacts] = {}


def facts(tree: Tree, path: str) -> FileFacts:
    data = tree.read(path)
    if data is None:
        return FileFacts(parse_ok=False)
    key = hashlib.sha1(path.encode() + b"\0" + data).hexdigest()
    if key in _FACTS:
        return _FACTS[key]
    try:
        mod = ast.parse(data, filename=path)
    except (SyntaxError, ValueError):
        f = FileFacts(parse_ok=False)
        _FACTS[key] = f
        return f
    this = module_of(path) or ""
    is_pkg = path.endswith("/__init__.py")
    f = FileFacts(parse_ok=True)
    for node in ast.walk(mod):
        if isinstance(node, ast.Import):
            for a in node.names:
                f.imports.append(ImportRef(a.name, (), asname=a.asname))
        elif isinstance(node, ast.ImportFrom):
            m = _resolve_rel(node.module, node.level, this, is_pkg)
            names = tuple(a.name for a in node.names if a.name != "*")
            f.imports.append(ImportRef(m, names, star=any(a.name == "*" for a in node.names)))
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) and len(node.value) < 200:
            f.strings.add(node.value)
        elif isinstance(node, ast.Attribute):
            c = _chain(node)
            if c:
                f.attr_chains.add(c)
        elif isinstance(node, ast.Call):
            fn = _chain(node.func) or ""
            last = fn.rsplit(".", 1)[-1]
            if last in DYN_IMPORT_FUNCS and node.args and not isinstance(node.args[0], ast.Constant):
                f.dyn_nonliteral = True
            if last in REGISTRY_FUNCS:
                f.registry_calls = True
            if last == "fixture_params":
                f.sync_backend_cells = True
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name.startswith("test") and any(a.arg == "backend" for a in node.args.args):
                f.sync_backend_cells = True
            if node.name in SESSION_HOOKS:
                f.session_hooks.add(node.name)
            for d in node.decorator_list:
                if isinstance(d, ast.Call) and (_chain(d.func) or "").endswith("fixture"):
                    kw = {k.arg: k.value for k in d.keywords}
                    scope = kw.get("scope")
                    auto = kw.get("autouse")
                    if (
                        isinstance(scope, ast.Constant)
                        and scope.value == "session"
                        and isinstance(auto, ast.Constant)
                        and auto.value is True
                    ):
                        f.session_hooks.add(f"session autouse fixture {node.name}")
        if (
            isinstance(node, (ast.Attribute, ast.Name))
            and getattr(node, "attr", getattr(node, "id", "")) == "os_sensitive"
        ):
            f.os_sensitive = True
    for s in mod.body:
        if isinstance(s, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            f.defined_names.add(s.name)
        elif isinstance(s, ast.Assign):
            for t in s.targets:
                if isinstance(t, ast.Name):
                    f.defined_names.add(t.id)
        elif isinstance(s, ast.AnnAssign) and isinstance(s.target, ast.Name):
            f.defined_names.add(s.target.id)
    f.top_effects = _top_effects(mod)

    def top(stmts: list[ast.stmt]) -> None:
        for s in stmts:
            if isinstance(s, ast.Import):
                f.top_imports.extend(ImportRef(a.name, (), asname=a.asname) for a in s.names)
            elif isinstance(s, ast.ImportFrom):
                m = _resolve_rel(s.module, s.level, this, is_pkg)
                f.top_imports.append(
                    ImportRef(m, tuple(a.name for a in s.names if a.name != "*"), any(a.name == "*" for a in s.names))
                )
            elif isinstance(s, ast.If) and not _is_type_checking(s.test):
                top(s.body)
                top(s.orelse)
            elif isinstance(s, ast.Try):
                top(s.body)
                for h in s.handlers:
                    top(h.body)
                top(s.orelse)
                top(s.finalbody)

    top(mod.body)
    _FACTS[key] = f
    return f
