"""The oracle adapter routes write keys and move/copy destinations through ``RootPath.dfy`` §5.

Conformance cannot tell the routing from a direct call: the class methods
also refuse ``"./"`` (their ``AddressesRoot`` check fires on the raw string),
and the conformance cells accept any root spelling in the raised path. The
difference is certification. A direct call hands the class a key outside its
``requires WellFormedPath``, so the refusal is observed, not proved; through
``WriteKey`` / ``MoveKey`` / ``CopyKey`` the key reaches the class folded
onto Root and the refusal is the verified one. The observable trace of the
fold is the raised path: ``"."`` for every spelling, never the raw key.
"""

from __future__ import annotations

import pytest

from remote_store._errors import InvalidPath
from tests.backends.dafny._helpers import DafnyOracleBackend

_NON_CANONICAL = ["./", ".//", "./.", "/"]


@pytest.mark.spec("BE-029")
@pytest.mark.parametrize("root", _NON_CANONICAL)
@pytest.mark.parametrize(
    "call",
    [
        pytest.param(lambda b, p: b.write(p, b"x"), id="write"),
        pytest.param(lambda b, p: b.write_atomic(p, b"x", overwrite=True), id="write_atomic"),
        pytest.param(lambda b, p: b.move("src.txt", p), id="move_dst"),
        pytest.param(lambda b, p: b.copy("src.txt", p), id="copy_dst"),
    ],
)
def test_root_spelling_is_folded_before_the_model(call: object, root: str) -> None:
    """Every non-canonical root spelling is refused naming Root, and nothing moves."""
    backend = DafnyOracleBackend()
    backend.write("src.txt", b"seed")
    with pytest.raises(InvalidPath) as exc:
        call(backend, root)  # type: ignore[operator]
    assert exc.value.path == "."
    assert backend.read_bytes("src.txt") == b"seed"
