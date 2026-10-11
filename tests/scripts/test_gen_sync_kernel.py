"""``scripts/gen_sync_kernel.py``: the generated sync kernel stays in step with its source."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import gen_sync_kernel  # noqa: E402

KERNEL = ROOT / "src" / "remote_store" / "_kernel"


@pytest.fixture
def kernel_copy(tmp_path: Path) -> Path:
    """The kernel's source and generated halves, copied so a test may edit them."""
    copy = tmp_path / "_kernel"
    for half in ("_async", "_sync"):
        shutil.copytree(KERNEL / half, copy / half)
    return copy


def test_the_committed_sync_kernel_is_up_to_date(capsys: pytest.CaptureFixture[str]) -> None:
    assert gen_sync_kernel.main(["--check"]) == 0
    assert "up to date" in capsys.readouterr().out


def test_a_hand_edit_to_a_generated_file_fails_the_check(kernel_copy: Path, capsys: pytest.CaptureFixture[str]) -> None:
    generated = kernel_copy / "_sync" / "kernel.py"
    generated.write_text(generated.read_text(encoding="utf-8") + "\n# a hand edit\n", encoding="utf-8")
    assert gen_sync_kernel.main(["--check"], kernel=kernel_copy) == 1
    assert "_sync/kernel.py" in capsys.readouterr().err


def test_an_edit_to_the_async_source_is_stale_until_regenerated(kernel_copy: Path) -> None:
    source = kernel_copy / "_async" / "kernel.py"
    text = source.read_text(encoding="utf-8")
    source.write_text(text.replace("Cannot write to the store root", "Cannot write to the root"), encoding="utf-8")
    assert gen_sync_kernel.main(["--check"], kernel=kernel_copy) == 1
    assert gen_sync_kernel.main([], kernel=kernel_copy) == 0
    assert gen_sync_kernel.main(["--check"], kernel=kernel_copy) == 0
    assert "Cannot write to the root" in (kernel_copy / "_sync" / "kernel.py").read_text(encoding="utf-8")


def test_the_generated_kernel_holds_no_async_syntax() -> None:
    text = (KERNEL / "_sync" / "kernel.py").read_text(encoding="utf-8")
    for token in ("async def", "await ", "async for", "async with", "AsyncDriver", "__anext__"):
        assert token not in text, token
