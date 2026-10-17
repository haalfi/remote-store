#!/usr/bin/env python3
"""Draw the kernel's interaction protocol from its compiled model.

The diagrams under spec 003 BE-033 are enumerated, not drawn: this runs the
compiled ``sdd/formal/KernelProtocol-py/`` oracle over its whole finite input
space and writes what it computes as Mermaid ``stateDiagram-v2`` fences between
``<!-- BEGIN_GENERATED:kernel_protocol -->`` markers. So a change to
``KernelProtocol.dfy`` reaches the picture through the same rebuild that
reaches the oracle suite, and a stale picture fails ``--check``.

Two views. ``KernelStep`` over (posture, state) and both calls: the backend's
machine, with each edge labelled call / answer. ``KernelExit`` over every exit,
every resource state its preconditions admit and an iterator with and without
``aclose``: one diagram per resource, an edge for each before-to-after change,
labelled with the exits that make it. An exit that leaves a resource as it was
draws nothing.

The fences carry no ``%%`` comment: ``gen_python_support.py`` measured a bare
one as fatal before the diagram type, and the prose around them says what a
comment would.

Drift-gate::

    kind:       pair
    compares:   sdd/formal/KernelProtocol-py/ (KernelStep, KernelExit) ↔ the generated diagram block under BE-033 in
        sdd/specs/003-backend-adapter-contract.md
    domain:     intent ↔ intent-formalized
"""

from __future__ import annotations

import argparse
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


def _backend(kp) -> list[str]:
    lines: list[str] = []
    for posture in (kp.ClosePosture_Reusable(), kp.ClosePosture_Terminal()):
        p = _name(posture)
        lines += [f"state {p} {{", f"  [*] --> {p}_BOpen"]
        # One edge per (from, to): Mermaid draws two self-loops on a state with one label between them.
        edges: dict[tuple[str, str], list[str]] = {}
        for state in (kp.KernelBackendState_BOpen(), kp.KernelBackendState_BClosed()):
            for call in (kp.KernelCall_CloseCall(), kp.KernelCall_LiveCall()):
                after, answer = kp.default__.KernelStep(kp.KernelBackend_KernelBackend(posture, state, 0), call)
                key = (f"{p}_{_name(state)}", f"{p}_{_name(after.state)}")
                edges.setdefault(key, []).append(f"{_name(call)} / {_name(answer)}")
        lines += [f"  {b} --> {a} : {_JOIN.join(labels)}" for (b, a), labels in edges.items()]
        lines.append("}")
    return _fence(lines)


def _resources(kp) -> dict[str, list[str]]:
    exits = (
        kp.KernelExitPath_Success(),
        kp.KernelExitPath_GateRefused(),
        kp.KernelExitPath_Faulted(False),
        kp.KernelExitPath_Faulted(True),
        kp.KernelExitPath_Cancelled(),
    )
    streams = (kp.KernelStreamState_SOpen(), kp.KernelStreamState_SClosed())
    handles = (kp.WriteHandleState_HNone(), kp.WriteHandleState_HOpen())
    iters = (kp.CallerIterState_IUnstarted(), kp.CallerIterState_ISuspended())
    # (resource, before, after) -> exit label -> the `closable` values that take the edge
    edges: dict[tuple[str, str, str], dict[str, set[bool]]] = {}
    for exit_path in exits:
        for stream in streams:
            for handle in handles:
                for it in iters:
                    gate = _name(exit_path) == "GateRefused"
                    if gate and (_name(handle) != "HNone" or _name(it) != "IUnstarted"):
                        continue  # KernelExit's precondition
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
