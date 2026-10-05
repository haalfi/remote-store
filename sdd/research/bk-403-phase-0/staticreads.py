"""Static half of the D5 layer-4 reader inventory; throwaway research.

Scans every ``.py`` under ``tests/`` and ``scripts/`` for calls that read repo
files other than by import, and resolves their targets with a small constant
folder:

- read calls: ``.read_text``, ``.read_bytes``, ``open``, ``.open``,
  ``tomllib.load``, ``json.load`` on an ``open``;
- scan calls: ``.glob``, ``.rglob``, ``.iterdir``, ``os.listdir``,
  ``os.scandir``, ``os.walk``, ``glob.glob``;
- ``subprocess.run/check_output/call/Popen`` whose argv names a repo path.

Resolvable expressions: ``Path(__file__)`` and ``os.path.dirname(__file__)``,
``.parent``, ``.parents[n]``, ``.resolve()``, ``/`` and ``os.path.join`` with
string constants, ``Path("...")``, and names bound to such values at module
level or earlier in the same function. Anything else is unresolved and
counted, never guessed.

A read in ``scripts/x.py`` is attributed to every test that imports ``x``
(layer-2 edge, transitively through scripts) or runs it by subprocess. A read
in a conftest is attributed to the conftest's directory scope.

Usage: python sdd/research/bk-403-phase-0/staticreads.py <rev> <out.json>
"""

from __future__ import annotations

import ast
import json
import sys
from collections import defaultdict

from p0tree import Tree
from selector import analysis, is_test_file

READ_ATTRS = {"read_text", "read_bytes", "open"}
SCAN_ATTRS = {"glob", "rglob", "iterdir"}
SCAN_FUNCS = {"os.listdir", "os.scandir", "os.walk", "glob.glob", "glob.iglob"}
SUBPROC = {"subprocess.run", "subprocess.check_output", "subprocess.call", "subprocess.Popen", "subprocess.check_call"}


def _norm(parts: list[str]) -> str | None:
    out: list[str] = []
    for p in parts:
        for q in p.replace("\\", "/").split("/"):
            if q in ("", "."):
                continue
            if q == "..":
                if not out:
                    return None
                out.pop()
            else:
                out.append(q)
    return "/".join(out)


class Folder(ast.NodeVisitor):
    """Resolve path expressions in one file to repo-relative strings."""

    def __init__(self, path: str, files: frozenset[str], dirs: frozenset[str]) -> None:
        self.path = path
        self.files = files
        self.dirs = dirs
        self.env: dict[str, str | None] = {}
        self.reads: list[tuple[str, str, int]] = []  # (kind, target, line)
        self.unresolved: list[tuple[str, int]] = []

    def val(self, n: ast.AST) -> str | None:
        """Repo-relative path (``""`` = repo root) or None."""
        if isinstance(n, ast.Name):
            if n.id == "__file__":
                return self.path
            return self.env.get(n.id)
        if isinstance(n, ast.Constant) and isinstance(n.value, str):
            return None
        if isinstance(n, ast.Call):
            fn = ast.unparse(n.func)
            if fn in ("Path", "pathlib.Path", "PurePath") and n.args:
                if isinstance(n.args[0], ast.Constant) and isinstance(n.args[0].value, str):
                    # A relative literal resolves against cwd; pytest runs from the
                    # repo root, so accept it when it names a tracked path.
                    rel = _norm([n.args[0].value])
                    return rel if rel is not None and (rel in self.files or rel in self.dirs) else None
                return self.val(n.args[0])
            if isinstance(n.func, ast.Attribute) and n.func.attr in ("resolve", "absolute"):
                return self.val(n.func.value)
            if fn in ("os.path.dirname",) and n.args:
                v = self.val(n.args[0])
                return None if v is None else (v.rsplit("/", 1)[0] if "/" in v else "")
            if fn in ("os.path.abspath", "os.path.realpath", "str", "os.fspath") and n.args:
                return self.val(n.args[0])
            if fn == "os.path.join" and n.args:
                base = self.val(n.args[0])
                rest = [a.value for a in n.args[1:] if isinstance(a, ast.Constant) and isinstance(a.value, str)]
                if base is None or len(rest) != len(n.args) - 1:
                    return None
                return _norm([base, *rest])
            return None
        if isinstance(n, ast.Attribute):
            if n.attr == "parent":
                v = self.val(n.value)
                return None if v is None else (v.rsplit("/", 1)[0] if "/" in v else "")
            return None
        if isinstance(n, ast.Subscript) and isinstance(n.value, ast.Attribute) and n.value.attr == "parents":
            v = self.val(n.value.value)
            if v is None or not isinstance(n.slice, ast.Constant):
                return None
            parts = v.split("/")
            k = int(n.slice.value) + 1
            return "/".join(parts[:-k]) if k <= len(parts) else None
        if isinstance(n, ast.BinOp) and isinstance(n.op, ast.Div):
            left = self.val(n.left)
            if left is None:
                return None
            if isinstance(n.right, ast.Constant) and isinstance(n.right.value, str):
                return _norm([left, n.right.value])
            return None
        return None

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        saved = dict(self.env)
        self.generic_visit(node)
        self.env = saved

    visit_AsyncFunctionDef = visit_FunctionDef  # type: ignore[assignment]

    def visit_Assign(self, node: ast.Assign) -> None:
        self.generic_visit(node)
        v = self.val(node.value)
        for t in node.targets:
            if isinstance(t, ast.Name):
                self.env[t.id] = v

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        self.generic_visit(node)
        if isinstance(node.target, ast.Name) and node.value is not None:
            self.env[node.target.id] = self.val(node.value)

    def visit_Call(self, node: ast.Call) -> None:
        self.generic_visit(node)
        fn = ast.unparse(node.func)
        if isinstance(node.func, ast.Attribute) and node.func.attr in READ_ATTRS | SCAN_ATTRS:
            v = self.val(node.func.value)
            kind = "scan" if node.func.attr in SCAN_ATTRS else "read"
            if v is None:
                self.unresolved.append((f"{kind}:{node.func.attr}", node.lineno))
                return
            if kind == "scan":
                pat = node.args[0].value if node.args and isinstance(node.args[0], ast.Constant) else "*"
                if node.func.attr == "rglob" or "**" in str(pat):
                    self.reads.append(("scan-tree", v or ".", node.lineno))
                else:
                    self.reads.append(("scan", v or ".", node.lineno))
            elif v in self.files:
                self.reads.append(("read", v, node.lineno))
            return
        if fn == "open" and node.args:
            v = self.val(node.args[0])
            if v is None:
                self.unresolved.append(("read:open", node.lineno))
            elif v in self.files:
                self.reads.append(("read", v, node.lineno))
            return
        if fn in SCAN_FUNCS and node.args:
            v = self.val(node.args[0])
            if v is None:
                self.unresolved.append((f"scan:{fn}", node.lineno))
            else:
                self.reads.append(("scan-tree" if fn == "os.walk" else "scan", v or ".", node.lineno))
            return
        if fn in SUBPROC and node.args:
            argv = node.args[0]
            elems = argv.elts if isinstance(argv, (ast.List, ast.Tuple)) else [argv]
            hit = False
            for e in elems:
                v = self.val(e)
                if v is not None and v in self.files:
                    self.reads.append(("subprocess", v, node.lineno))
                    hit = True
                elif isinstance(e, ast.Constant) and isinstance(e.value, str) and _norm([e.value]) in self.files:
                    self.reads.append(("subprocess", _norm([e.value]), node.lineno))
                    hit = True
            if not hit:
                self.unresolved.append(("subprocess", node.lineno))


def scan(tree: Tree) -> dict:
    A = analysis(tree)
    per_file: dict[str, list] = {}
    unresolved: dict[str, list] = {}
    for p in A.py:
        if not p.startswith(("tests/", "scripts/")):
            continue
        data = tree.text(p) or ""
        try:
            mod = ast.parse(data)
        except SyntaxError:
            continue
        f = Folder(p, tree.files, tree.dirs)
        f.visit(mod)
        if f.reads:
            per_file[p] = f.reads
        if f.unresolved:
            unresolved[p] = f.unresolved

    # Attribute script reads (and subprocess-run scripts) to the tests that reach them.
    readers: dict[str, set[str]] = defaultdict(set)  # reader -> targets (kind:target)

    def attribute(src: str, reader: str, seen: set[str]) -> None:
        if src in seen:
            return
        seen.add(src)
        for kind, tgt, _ in per_file.get(src, ()):
            readers[reader].add(f"{kind}:{tgt}")
            if kind == "subprocess" and tgt.endswith(".py"):
                attribute(tgt, reader, seen)
        for dep in A.edges.get(src, ()):
            if dep.startswith("scripts/") or (dep.startswith("tests/") and not is_test_file(dep)):
                attribute(dep, reader, seen)

    for p in A.py:
        if is_test_file(p):
            attribute(p, p, set())
        elif p.endswith("conftest.py"):
            attribute(p, "dir:" + p[: -len("conftest.py")], set())
    return {
        "rev": tree.rev,
        "readers": {k: sorted(v) for k, v in sorted(readers.items()) if v},
        "unresolved": {k: [f"{a}@{b}" for a, b in v] for k, v in sorted(unresolved.items())},
    }


def main() -> None:
    out = scan(Tree(sys.argv[1]))
    with open(sys.argv[2], "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1)
    n_unres = sum(len(v) for v in out["unresolved"].values())
    print(f"readers {len(out['readers'])}, unresolved call sites {n_unres} in {len(out['unresolved'])} files")


if __name__ == "__main__":
    main()
