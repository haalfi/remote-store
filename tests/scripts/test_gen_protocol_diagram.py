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
    assert "ISuspended --> IClosed : Faulted(dead=False), Faulted(dead=True), Cancelled with aclose" in lines
    # A failure leaves an unstarted iterator where it was: no edge out of IUnstarted but Success.
    assert [line for line in lines if line.startswith("IUnstarted -->")] == ["IUnstarted --> IExhausted : Success"]
    # No exit leaves a handle open or reopens a stream.
    assert not [line for line in lines if " --> HOpen :" in line or " --> SOpen :" in line]


def test_the_domain_is_every_constructor_the_preconditions_admit(gen):
    """Derived from the compiled datatypes, not hand-listed, then filtered by the model's AtAnExit:
    a closed iterator is no before-state (KernelProtocol.dfy says why), and a success meets one
    unstarted or exhausted, never suspended."""
    kp = gen._oracle()
    states = {type(value).__name__ for value in gen._constructors(kp.CallerIterState)}
    assert states == {f"CallerIterState_{s}" for s in ("IUnstarted", "ISuspended", "IExhausted", "IClosed")}
    assert len(gen._exits(kp)) == 5  # Success, GateRefused, Faulted(False), Faulted(True), Cancelled
    lines = [line.strip() for line in gen.render().splitlines()]
    assert not [line for line in lines if line.startswith("IClosed -->")]
    assert [line for line in lines if line.endswith("--> IExhausted : Success")] == [
        "IUnstarted --> IExhausted : Success"
    ]


def _reached(gen, monkeypatch) -> list[tuple]:
    """Every (exit, before, closable) the oracle suite passes the model, by running its cells."""
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
            om.test_every_sync_write_exit_leaves_the_handle_the_model_computes(*case.values)
        for case in om._open_atomic_cases():
            om.test_every_open_atomic_exit_leaves_the_handle_the_model_computes(*case.values)
        for case in om._read_cases():
            om.test_every_read_exit_leaves_the_stream_the_model_computes(*case.values)
    return calls


def test_every_drawn_edge_is_one_the_kernel_reaches(gen, monkeypatch):
    """The admitted domain, closed by enumeration: an edge the oracle suite never drives the kernel
    through (a before-state no exit meets) fails here instead of reaching the diagram."""
    kp = gen._oracle()
    reached = _reached(gen, monkeypatch)
    assert reached, "the oracle suite drove no exit"
    drawn = gen._edges(kp, gen._admitted(kp))
    by_kernel = gen._edges(kp, reached)
    assert {k: sorted(v) for k, v in drawn.items()} == {k: sorted(v) for k, v in by_kernel.items()}


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
