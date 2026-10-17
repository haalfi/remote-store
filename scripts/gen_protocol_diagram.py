#!/usr/bin/env python3
"""Draw the kernel's interaction protocol from its compiled model.

The diagrams under spec 003 BE-033 are enumerated, not drawn: this runs the
compiled ``sdd/formal/KernelProtocol-py/`` oracle over its whole finite input
space and writes what it computes as Mermaid ``stateDiagram-v2`` fences between
``<!-- BEGIN_GENERATED:kernel_protocol -->`` markers. So a change to
``KernelProtocol.dfy`` reaches the picture through the same rebuild that
reaches the oracle suite, and a stale picture fails ``--check``.

Two views. ``KernelStep`` over every posture, state and call: the backend's
machine, with each edge labelled call / answer. ``KernelExit`` over every exit,
every resource state its preconditions admit and an iterator with and without
``aclose``: one diagram per resource, an edge for each before-to-after change,
labelled with the exits that make it. An exit that leaves a resource as it was
draws nothing. The domain is read from the compiled datatypes
(``_constructors``), so a constructor added to the model is drawn.

The fences carry no ``%%`` comment: ``gen_python_support.py`` measured a bare
one as fatal before the diagram type, and the prose around them says what a
comment would.

**Bounds.** Mermaid is never parsed or rendered here; the refused ``;`` is the
one mis-draw measured (mermaid 11.4.1 in Chromium), and nothing else stands
between a label and the renderer. ``KernelExit``'s ``requires`` are restated in
``_resources``, since the compiled Python does not check them, so a new
precondition needs an edit there, and so does a constructor field that is not a
``bool`` (today's one field is ``Faulted``'s ``dead``). ``--check`` compares the block with the
committed oracle, so a stale oracle draws a stale "current" block: freshness is
``check_dafny_oracle_fresh.py``'s, in the ``verify-formal`` CI job. Only the
first ``kernel_protocol`` region is rewritten; a second copy is not seen.

Drift-gate::

    kind:       pair
    compares:   sdd/formal/KernelProtocol-py/ (KernelStep, KernelExit) ↔ the generated diagram block under BE-033 in
        sdd/specs/003-backend-adapter-contract.md
    domain:     intent ↔ intent-formalized
"""

from __future__ import annotations

import argparse
import itertools
import re
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_ORACLE_DIR = _REPO_ROOT / "sdd" / "formal" / "KernelProtocol-py"
SPEC = _REPO_ROOT / "sdd" / "specs" / "003-backend-adapter-contract.md"
_REGION = "kernel_protocol"
_REGION_RE = re.compile(
    rf"(<!-- BEGIN_GENERATED:{_REGION} -->\n)(?:.*?\n)?(<!-- END_GENERATED:{_REGION} -->)", re.DOTALL
)


def _oracle():
    """Import the compiled model, leaving neither its directory on ``sys.path`` nor its stub
    ``module_`` in ``sys.modules`` (it would shadow MemoryBackend-py's), as the oracle suite does."""
    prior_module_ = sys.modules.get("module_")
    sys.path.insert(0, str(_ORACLE_DIR))
    try:
        import KernelProtocol
    finally:
        sys.path.remove(str(_ORACLE_DIR))
        if prior_module_ is None:
            sys.modules.pop("module_", None)
        else:
            sys.modules["module_"] = prior_module_
    return KernelProtocol


def _name(value) -> str:
    """``KernelStreamState_SOpen()`` -> ``SOpen``: the Dafny constructor name."""
    return type(value).__name__.split("_", 1)[1]


def _exit_label(exit_path) -> str:
    return f"Faulted(dead={exit_path.dead})" if _name(exit_path) == "Faulted" else _name(exit_path)


# Joins the labels of edges merged onto one (from, to). Measured with mermaid
# 11.4.1 in Chromium: `;` ends a statement even inside a transition label, so
# `a --> b : x; y` parses without error and draws `y` as stray state nodes.
_JOIN = "<br/>"


def _fence(lines: list[str]) -> list[str]:
    for line in lines:
        if ";" in line:
            raise ValueError(f"`;` ends a Mermaid statement, so this line would draw stray states: {line!r}")
    return ["```mermaid", "stateDiagram-v2", *(f"  {line}" for line in lines), "```"]


def _constructors(datatype) -> list:
    """Every value of a compiled Dafny datatype: one per constructor, each field over ``False`` and ``True``.

    Read from the compiled classes (each constructor is a subclass), so a constructor added to
    ``KernelProtocol.dfy`` is enumerated without an edit here. Dafny types every field ``Any``,
    so a field's type cannot be read back: the bool assumption is a bound (module docstring).
    """
    values = []
    for ctor in datatype.__subclasses__():
        values += [ctor(*combo) for combo in itertools.product((False, True), repeat=len(ctor._fields))]
    return values


def _exits(kp) -> list:
    return _constructors(kp.KernelExitPath)


def _backend(kp) -> list[str]:
    lines: list[str] = []
    for posture in _constructors(kp.ClosePosture):
        p = _name(posture)
        lines += [f"state {p} {{", f"  [*] --> {p}_BOpen"]
        # One edge per (from, to): Mermaid draws two self-loops on a state with one label between them.
        edges: dict[tuple[str, str], list[str]] = {}
        for state in _constructors(kp.KernelBackendState):
            for call in _constructors(kp.KernelCall):
                after, answer = kp.default__.KernelStep(kp.KernelBackend_KernelBackend(posture, state, 0), call)
                key = (f"{p}_{_name(state)}", f"{p}_{_name(after.state)}")
                edges.setdefault(key, []).append(f"{_name(call)} / {_name(answer)}")
        lines += [f"  {b} --> {a} : {_JOIN.join(labels)}" for (b, a), labels in edges.items()]
        lines.append("}")
    return _fence(lines)


def _resources(kp) -> dict[str, list[str]]:
    # KernelExit's `requires`, restated: the compiled Python does not check them.
    streams = [s for s in _constructors(kp.KernelStreamState) if _name(s) in ("SOpen", "SClosed")]
    handles = _constructors(kp.WriteHandleState)
    iters = [i for i in _constructors(kp.CallerIterState) if _name(i) != "IClosed"]
    # (resource, before, after) -> exit label -> the `closable` values that take the edge
    edges: dict[tuple[str, str, str], dict[str, set[bool]]] = {}
    for exit_path in _exits(kp):
        for stream in streams:
            for handle in handles:
                for it in iters:
                    gate = _name(exit_path) == "GateRefused"
                    if gate and (_name(handle) != "HNone" or _name(it) != "IUnstarted"):
                        continue
                    for closable in (True, False):
                        before = kp.KernelResources_KernelResources(stream, handle, it)
                        after = kp.default__.KernelExit(exit_path, before, closable)
                        for resource, b, a in (
                            ("stream", stream, after.stream),
                            ("handle", handle, after.handle),
                            ("iterator", it, after.iter_),
                        ):
                            if b != a:
                                key = (resource, _name(b), _name(a))
                                edges.setdefault(key, {}).setdefault(_exit_label(exit_path), set()).add(closable)
    out: dict[str, list[str]] = {"stream": [], "handle": [], "iterator": []}
    for (resource, b, a), by_exit in sorted(edges.items()):
        # Only the iterator's edges depend on `aclose`; group the exits by the condition, stated once.
        groups: dict[str, list[str]] = {}
        for label, closables in by_exit.items():
            condition = "" if len(closables) == 2 else (" with aclose" if True in closables else " without aclose")
            groups.setdefault(condition, []).append(label)
        label = _JOIN.join(", ".join(exits) + condition for condition, exits in groups.items())
        out[resource].append(f"{b} --> {a} : {label}")
    return {resource: _fence(lines) for resource, lines in out.items()}


def render() -> str:
    """The region's body, between its markers."""
    kp = _oracle()
    resources = _resources(kp)
    parts = [
        "Generated from the compiled model by `scripts/gen_protocol_diagram.py`; do not edit by hand.",
        "",
        "The backend under `KernelStep`, each edge a call / its answer:",
        "",
        *_backend(kp),
        "",
        "Each resource under `KernelExit`, each edge labelled with the exits that make it; an exit not drawn",
        "leaves the resource as it was:",
    ]
    for resource in ("stream", "handle", "iterator"):
        parts += ["", f"{resource.capitalize()}:", "", *resources[resource]]
    return "\n".join(parts)


def _splice(text: str, body: str) -> str:
    if not _REGION_RE.search(text):
        raise ValueError(f"{SPEC.relative_to(_REPO_ROOT)} has no BEGIN_GENERATED:{_REGION} / END_GENERATED pair")
    return _REGION_RE.sub(lambda m: m.group(1) + body + "\n" + m.group(2), text, count=1)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="Read-only: exit 1 if the committed block is stale.")
    args = parser.parse_args(argv)
    text = SPEC.read_text(encoding="utf-8")
    try:
        expected = _splice(text, render())
    except ValueError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    if not args.check:
        SPEC.write_text(expected, encoding="utf-8", newline="\n")
        print(f"Wrote the {_REGION} block in {SPEC.relative_to(_REPO_ROOT)}")
        return 0
    if expected == text:
        return 0
    print(f"STALE: the {_REGION} block in {SPEC.relative_to(_REPO_ROOT)} disagrees with the oracle.", file=sys.stderr)
    for number, (want, got) in enumerate(zip(expected.splitlines(), text.splitlines(), strict=False), start=1):
        if want != got:
            print(
                f"  line {number}: expected {want!r}, found {got!r}",
                file=sys.stderr,
            )
            break
    print("Run: hatch run gen-protocol-diagram", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
