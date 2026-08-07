"""What ``LocalBackend`` does when its root directory is deleted underneath it.

BE-021's absent-container rule says a tolerant delete treats an absent container
as an absent path. On ``LocalBackend`` the container is the root directory, so
the rule applies here as it does everywhere — and this module exists because
that is *not* what happens today.

**Measured:** with the root deleted, every path operation raises
``InvalidPath("Path escapes root directory")``. Not ``NotFound``, and not a
silent return under ``missing_ok``. The cause is in ``_within_root``: it walks
up from the target to the deepest lexically-existing ancestor for its
symlink-escape check, and once the root is gone that walk climbs *past* the
root, so ``anchor.resolve().relative_to(self._root)`` raises ``ValueError`` and
containment is reported as an escape. Nothing is escaping — the store is absent
— and ``InvalidPath`` is the worst of the three plausible answers, since it tells
the caller their path is malformed when the path is fine.

**Why this module is worth its weight.** The claim that Local already treated an
absent root as an absent path was written into BE-021's rationale, into
``_flat_ns._children_or_absent_container``'s docstring, and into the item's
trace, as the argument that tolerating "makes flat-namespace agree with the
hierarchical backends". It was false, and it was false in a way reading could
not catch: ``delete`` and ``delete_folder`` both look correct in isolation
(``full.exists()`` → ``missing_ok`` → return), because ``_resolve`` raises two
lines earlier. Two readers checked the code and both missed it; running it took
seconds. `sdd/TESTING.md`'s rule that behaviour must be executed rather than
inspected is the whole of the lesson.

The contract cells below are ``xfail(strict=True)``: they state what BE-021
requires, they fail today, and the moment the divergence is fixed they XPASS and
break the suite, which is the prompt to delete the markers. The companion cell
pins the actual error so a change to some *third* behaviour is caught too.
"""

from __future__ import annotations

import shutil
from typing import TYPE_CHECKING

import pytest

from remote_store._errors import InvalidPath, NotFound
from remote_store.backends._local import LocalBackend

if TYPE_CHECKING:
    from pathlib import Path

_DIVERGENCE = "absent root raises InvalidPath instead of the contract's NotFound / missing_ok tolerance"


@pytest.fixture
def backend(tmp_path: Path) -> LocalBackend:
    """A ``LocalBackend`` holding one file, whose root is then deleted."""
    root = tmp_path / "store"
    root.mkdir()
    instance = LocalBackend(str(root))
    instance.write("folder/object.txt", b"payload")
    shutil.rmtree(root)
    return instance


@pytest.mark.spec("BE-012", "BE-013", "BE-021")
class TestAbsentRootReadsAsAbsentPath:
    """What BE-021 requires of an absent container, applied to Local's root."""

    @pytest.mark.xfail(strict=True, reason=_DIVERGENCE)
    @pytest.mark.parametrize(
        ("op_name", "call"),
        [
            ("delete", lambda b: b.delete("folder/object.txt", missing_ok=True)),
            ("delete_folder", lambda b: b.delete_folder("folder", recursive=True, missing_ok=True)),
        ],
        ids=["delete", "delete_folder"],
    )
    def test_tolerant_delete_returns_cleanly(
        self,
        backend: LocalBackend,
        op_name: str,
        call,  # noqa: ANN001 -- parametrized callable
    ) -> None:
        assert call(backend) is None, f"{op_name} must tolerate an absent root under missing_ok"

    @pytest.mark.xfail(strict=True, reason=_DIVERGENCE)
    @pytest.mark.parametrize(
        ("op_name", "call"),
        [
            ("delete", lambda b: b.delete("folder/object.txt")),
            ("delete_folder", lambda b: b.delete_folder("folder", recursive=True)),
        ],
        ids=["delete", "delete_folder"],
    )
    def test_strict_delete_raises_not_found(
        self,
        backend: LocalBackend,
        op_name: str,
        call,  # noqa: ANN001 -- parametrized callable
    ) -> None:
        with pytest.raises(NotFound) as exc_info:
            call(backend)
        assert exc_info.value.backend == "local"


@pytest.mark.spec("BE-012", "BE-013", "BE-021")
class TestTheDivergenceAsItActuallyIs:
    """Pins today's answer, so a drift to some third behaviour is not silent.

    The ``xfail`` cells above catch the divergence being *fixed*. This catches it
    changing into something else — a bare ``OSError`` leaking, say — which
    ``xfail`` would happily absorb.
    """

    @pytest.mark.parametrize(
        ("op_name", "call"),
        [
            ("delete", lambda b: b.delete("folder/object.txt", missing_ok=True)),
            ("delete_folder", lambda b: b.delete_folder("folder", recursive=True, missing_ok=True)),
        ],
        ids=["delete", "delete_folder"],
    )
    def test_absent_root_currently_reports_an_escape(
        self,
        backend: LocalBackend,
        op_name: str,
        call,  # noqa: ANN001 -- parametrized callable
    ) -> None:
        with pytest.raises(InvalidPath, match="escapes root"):
            call(backend)
