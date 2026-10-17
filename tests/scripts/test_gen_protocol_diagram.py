"""Tests for scripts/gen_protocol_diagram.py.

`--check` is the drift gate. These add what it cannot see: a block that agrees
with itself but draws the wrong machine, or will not draw. Mermaid itself is
not run here (no browser in the unit lane); the `;` guard is the floor under
the one mis-draw measured, which parsed without error.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent.parent / "scripts"


@pytest.fixture(scope="module")
def gen():
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    import gen_protocol_diagram

    return gen_protocol_diagram


def test_the_committed_block_is_current(gen):
    assert gen.main(["--check"]) == 0


def test_a_stale_block_fails_the_check_naming_the_line(gen, tmp_path, monkeypatch, capsys):
    spec = tmp_path / "spec.md"
    fresh = gen._splice(gen.SPEC.read_text(encoding="utf-8"), gen.render())
    spec.write_text(fresh.replace("LiveCall / Unavailable", "LiveCall / Done"), encoding="utf-8")
    monkeypatch.setattr(gen, "SPEC", spec)
    monkeypatch.setattr(gen, "_REPO_ROOT", tmp_path)
    assert gen.main(["--check"]) == 1
    err = capsys.readouterr().err
    assert "STALE" in err
    assert "Unavailable" in err
    assert "gen-protocol-diagram" in err


def test_a_spec_without_the_markers_is_refused(gen, tmp_path, monkeypatch, capsys):
    spec = tmp_path / "spec.md"
    spec.write_text("# no block\n", encoding="utf-8")
    monkeypatch.setattr(gen, "SPEC", spec)
    monkeypatch.setattr(gen, "_REPO_ROOT", tmp_path)
    assert gen.main(["--check"]) == 1
    assert "BEGIN_GENERATED:kernel_protocol" in capsys.readouterr().err


def test_only_a_terminal_closed_backend_answers_unavailable(gen):
    """I1 as drawn: the one Unavailable edge is Terminal_BClosed's self-loop."""
    lines = [line.strip() for line in gen.render().splitlines()]
    unavailable = [line for line in lines if "Unavailable" in line]
    assert unavailable == ["Terminal_BClosed --> Terminal_BClosed : CloseCall / Done<br/>LiveCall / Unavailable"]
    assert "Reusable_BClosed --> Reusable_BClosed : CloseCall / Done<br/>LiveCall / Done" in lines


def test_the_resource_edges_are_the_models_cleanup(gen):
    lines = {line.strip() for line in gen.render().splitlines()}
    assert "SOpen --> SReleased : Faulted(dead=True)" in lines
    assert "HOpen --> HCommitted : Success" in lines
    # The kernel moves an iterator only by closing one it left suspended, on any exit past the gates.
    assert [line for line in lines if line.startswith("I") and " --> I" in line] == [
        "ISuspended --> IClosed : Success, Faulted(dead=False), Faulted(dead=True), Cancelled with aclose"
    ]
    # No exit leaves a handle open or reopens a stream.
    assert not [line for line in lines if " --> HOpen :" in line or " --> SOpen :" in line]


def test_the_domain_is_every_constructor_the_preconditions_admit(gen):
    """Derived from the compiled datatypes, not hand-listed, then filtered by the model's AtAnExit:
    a closed iterator is no before-state (KernelProtocol.dfy says why), and a gate refusal, which
    meets an iterator unstarted, moves none."""
    kp = gen._oracle()
    states = {type(value).__name__ for value in gen._constructors(kp.CallerIterState)}
    assert states == {f"CallerIterState_{s}" for s in ("IUnstarted", "ISuspended", "IExhausted", "IClosed")}
    assert len(gen._exits(kp)) == 5  # Success, GateRefused, Faulted(False), Faulted(True), Cancelled
    admitted = gen._admitted(kp)
    assert not [b for _, b, _ in admitted if type(b.iter_).__name__ == "CallerIterState_IClosed"]
    edges = gen._edges(kp, admitted)
    assert not [k for k, by_exit in edges.items() if k[0] == "iterator" and "GateRefused" in by_exit]
    assert [k for k, by_exit in edges.items() if k[0] == "iterator" and "Success" in by_exit] == [
        ("iterator", "ISuspended", "IClosed")
    ]


def _reached(gen, monkeypatch) -> tuple[list[tuple], list[tuple]]:
    """Every (exit, before, closable) the oracle suite passes the model, by running its cells: those
    whose iterator is a real caller iterator (the async writes), and those whose iterator component
    is a placeholder the cell never compares (sync writes, ``open_atomic``, reads)."""
    from tests._kernel import test_protocol_oracle as om

    calls: list[tuple] = []
    exit_fn = om._MODEL.KernelExit

    def record(exit_path, before, closable):
        calls.append((exit_path, before, closable))
        return exit_fn(exit_path, before, closable)

    with monkeypatch.context() as patched:  # undone before the caller asks the model itself
        patched.setattr(om._MODEL, "KernelExit", staticmethod(record))
        for case in om._write_cases():
            for closable in (True, False):
                om.test_every_async_write_exit_leaves_the_state_the_model_computes(*case.values, closable)
        for route in om._UNDRAINED_ROUTES:
            for closable in (True, False):
                with pytest.MonkeyPatch.context() as undrained:  # its driver patch ends with the cell
                    om.test_a_success_whose_driver_left_the_iterator_suspended_leaves_the_state_the_model_computes(
                        route, closable, undrained
                    )
        with_iterator = list(calls)
        calls.clear()
        for case in om._write_cases():
            om.test_every_sync_write_exit_leaves_the_handle_the_model_computes(*case.values)
        for case in om._open_atomic_cases():
            om.test_every_open_atomic_exit_leaves_the_handle_the_model_computes(*case.values)
        for case in om._read_cases():
            om.test_every_read_exit_leaves_the_stream_the_model_computes(*case.values)
    return with_iterator, list(calls)


def _shape(edges: dict) -> dict:
    """An edge's drawn label: its exits, and for the iterator, which take it with or without aclose."""
    return {
        key: {label: sorted(c) for label, c in by_exit.items()} if key[0] == "iterator" else sorted(by_exit)
        for key, by_exit in edges.items()
    }


def test_every_drawn_edge_is_one_the_kernel_reaches(gen, monkeypatch):
    """Every edge the diagram draws, label included, is one an oracle cell drives the kernel through,
    and the reverse: a drawn edge no exit takes fails here. The bound is edge-level: a state the model
    admits but no exit meets, whose edges other states draw too, passes (KernelProtocol.dfy says so)."""
    kp = gen._oracle()
    with_iterator, placeholder = _reached(gen, monkeypatch)
    assert with_iterator, "the oracle suite drove no async write exit"
    assert placeholder, "the oracle suite drove no other exit"
    by_kernel = gen._edges(kp, with_iterator)
    # A placeholder iterator is no observation: those cells count for stream and handle edges only.
    for key, by_exit in gen._edges(kp, placeholder).items():
        if key[0] != "iterator":
            for label, closables in by_exit.items():
                by_kernel.setdefault(key, {}).setdefault(label, set()).update(closables)
    drawn = gen._edges(kp, gen._admitted(kp))
    assert _shape(drawn) == _shape(by_kernel)


def test_a_semicolon_in_a_line_is_refused(gen):
    """Measured: `a --> b : x; y` parses and draws `y` as stray states."""
    with pytest.raises(ValueError, match="stray states"):
        gen._fence(["A --> B : x; y"])


def test_rendering_leaves_no_oracle_stub_behind(gen, monkeypatch):
    """The compiled model's stub `module_` would shadow MemoryBackend-py's in the same process."""
    # A fresh import each time, or a cached KernelProtocol never reaches the stub.
    monkeypatch.delitem(sys.modules, "KernelProtocol", raising=False)
    sentinel = object()
    monkeypatch.setitem(sys.modules, "module_", sentinel)
    gen.render()
    assert sys.modules["module_"] is sentinel
    monkeypatch.delitem(sys.modules, "KernelProtocol")
    monkeypatch.delitem(sys.modules, "module_")
    gen.render()
    assert "module_" not in sys.modules
    assert str(gen._ORACLE_DIR) not in sys.path
