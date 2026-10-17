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
