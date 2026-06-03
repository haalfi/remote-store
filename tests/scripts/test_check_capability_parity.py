"""Unit tests for scripts/check_capability_parity.py.

Exercises the BK-245 Python ↔ Dafny capability-parity gate:

P — ``Capability`` enum ``.value`` extraction (AST).
D — Dafny ``CapabilityName`` arm extraction (regex).
The mismatch report and the ``main()`` exit contract, including the
live-source parity tripwire and the empty-parse guard.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "check_capability_parity.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("check_capability_parity", _SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("check_capability_parity", module)
    spec.loader.exec_module(module)
    return module


_mod = _load_module()
extract_python_capabilities = _mod.extract_python_capabilities
extract_dafny_capabilities = _mod.extract_dafny_capabilities
compute_mismatch = _mod.compute_mismatch
main = _mod.main


# ---------------------------------------------------------------------------
# Source P — Python Capability enum
# ---------------------------------------------------------------------------


class TestExtractPythonCapabilities:
    def test_collects_member_values_not_names(self, tmp_path: Path) -> None:
        src = tmp_path / "_capabilities.py"
        src.write_text(
            'import enum\n\n\nclass Capability(enum.Enum):\n    READ = "read"\n    WRITE = "write"\n',
            encoding="utf-8",
        )
        assert extract_python_capabilities(src) == {"read", "write"}

    def test_ignores_docstring_and_methods(self, tmp_path: Path) -> None:
        src = tmp_path / "_capabilities.py"
        src.write_text(
            "import enum\n\n\nclass Capability(enum.Enum):\n"
            '    """Docstring, not a member."""\n\n'
            '    READ = "read"\n\n'
            "    def helper(self) -> str:\n"
            '        return "not_a_member"\n',
            encoding="utf-8",
        )
        assert extract_python_capabilities(src) == {"read"}

    def test_ignores_other_classes(self, tmp_path: Path) -> None:
        src = tmp_path / "_capabilities.py"
        src.write_text(
            "import enum\n\n\nclass Other(enum.Enum):\n"
            '    NOPE = "nope"\n\n\n'
            "class Capability(enum.Enum):\n"
            '    READ = "read"\n',
            encoding="utf-8",
        )
        assert extract_python_capabilities(src) == {"read"}

    def test_live_source_has_lazy_read(self) -> None:
        # The member ID-188 added, which BK-245 exists to keep at parity.
        live = _mod.ROOT / "src" / "remote_store" / "_capabilities.py"
        assert "lazy_read" in extract_python_capabilities(live)


# ---------------------------------------------------------------------------
# Source D — Dafny CapabilityName arms
# ---------------------------------------------------------------------------


class TestExtractDafnyCapabilities:
    def test_collects_case_arm_strings(self, tmp_path: Path) -> None:
        dfy = tmp_path / "Contract.dfy"
        dfy.write_text(
            "function CapabilityName(c: Capability): string\n{\n"
            "  match c\n"
            '  case CapRead => "read"\n'
            '  case CapLazyRead => "lazy_read"\n'
            "}\n",
            encoding="utf-8",
        )
        assert extract_dafny_capabilities(dfy) == {"read", "lazy_read"}

    def test_ignores_non_case_lines(self, tmp_path: Path) -> None:
        dfy = tmp_path / "Contract.dfy"
        dfy.write_text(
            "datatype Error = CapabilityNotSupported(capability: string)\n"
            '// CapWriteResultNative is a quality flag returning "write_result_native"\n'
            "function CapabilityName(c: Capability): string\n{\n"
            "  match c\n"
            '  case CapWrite => "write"\n'
            "}\n",
            encoding="utf-8",
        )
        # Only genuine ``case … => "…"`` arms inside the function body count;
        # the datatype line and the prose comment must not leak names in.
        assert extract_dafny_capabilities(dfy) == {"write"}

    def test_ignores_arms_in_a_second_helper(self, tmp_path: Path) -> None:
        # A second ``match c`` helper over Capability returning strings must
        # not leak its arms into the parsed set — the brittleness PR #744
        # review flagged. Only CapabilityName's body is scanned.
        dfy = tmp_path / "Contract.dfy"
        dfy.write_text(
            "function CapabilityName(c: Capability): string\n{\n"
            "  match c\n"
            '  case CapRead => "read"\n'
            "}\n\n"
            "function CapabilityDescription(c: Capability): string\n{\n"
            "  match c\n"
            '  case CapRead => "reads bytes"\n'
            '  case CapGhost => "not a real capability"\n'
            "}\n",
            encoding="utf-8",
        )
        assert extract_dafny_capabilities(dfy) == {"read"}

    def test_absent_function_yields_empty(self, tmp_path: Path) -> None:
        dfy = tmp_path / "Contract.dfy"
        dfy.write_text("datatype Capability = CapRead | CapWrite\n", encoding="utf-8")
        assert extract_dafny_capabilities(dfy) == set()


# ---------------------------------------------------------------------------
# Mismatch + main()
# ---------------------------------------------------------------------------


class TestComputeMismatch:
    def test_partitions_each_side(self) -> None:
        py_only, dfy_only = compute_mismatch({"read", "write"}, {"read", "glob"})
        assert py_only == {"write"}
        assert dfy_only == {"glob"}

    def test_equal_sets_have_no_mismatch(self) -> None:
        assert compute_mismatch({"read"}, {"read"}) == (set(), set())


def _write_python(tmp_path: Path, values: list[str]) -> Path:
    body = "".join(f'    M{i} = "{v}"\n' for i, v in enumerate(values))
    src = tmp_path / "_capabilities.py"
    src.write_text(f"import enum\n\n\nclass Capability(enum.Enum):\n{body}", encoding="utf-8")
    return src


def _write_dafny(tmp_path: Path, values: list[str]) -> Path:
    arms = "".join(f'  case Cap{i} => "{v}"\n' for i, v in enumerate(values))
    dfy = tmp_path / "Contract.dfy"
    dfy.write_text(f"function CapabilityName(c: Capability): string\n{{\n  match c\n{arms}}}\n", encoding="utf-8")
    return dfy


class TestMain:
    def test_live_sources_are_at_parity(self) -> None:
        # Regression tripwire: the real enum and the real contract must agree.
        assert main() == 0

    def test_parity_passes(self, tmp_path: Path) -> None:
        py = _write_python(tmp_path, ["read", "write"])
        dfy = _write_dafny(tmp_path, ["read", "write"])
        assert main(capabilities_py=py, contract_dfy=dfy) == 0

    def test_python_only_member_fails(self, tmp_path: Path, capsys) -> None:
        py = _write_python(tmp_path, ["read", "write"])
        dfy = _write_dafny(tmp_path, ["read"])
        assert main(capabilities_py=py, contract_dfy=dfy) == 1
        assert "in Python only" in capsys.readouterr().out

    def test_dafny_only_member_fails(self, tmp_path: Path, capsys) -> None:
        py = _write_python(tmp_path, ["read"])
        dfy = _write_dafny(tmp_path, ["read", "write"])
        assert main(capabilities_py=py, contract_dfy=dfy) == 1
        assert "in Dafny only" in capsys.readouterr().out

    def test_empty_python_parse_fails(self, tmp_path: Path, capsys) -> None:
        py = tmp_path / "_capabilities.py"
        py.write_text("class Capability:\n    pass\n", encoding="utf-8")
        dfy = _write_dafny(tmp_path, ["read"])
        assert main(capabilities_py=py, contract_dfy=dfy) == 1
        assert "no Capability members parsed" in capsys.readouterr().out

    def test_empty_dafny_parse_fails(self, tmp_path: Path, capsys) -> None:
        py = _write_python(tmp_path, ["read"])
        dfy = tmp_path / "Contract.dfy"
        dfy.write_text("// no arms here\n", encoding="utf-8")
        assert main(capabilities_py=py, contract_dfy=dfy) == 1
        assert "no CapabilityName arms parsed" in capsys.readouterr().out
