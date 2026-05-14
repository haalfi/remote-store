"""BK-181 PoC -- sync ``AzureBackend`` over a recorded HTTP cassette.

Each test runs the *real* Azure SDK code path. The only thing that changes
between recording and replay is the transport:

* ``--record-mode=rewrite`` -> real ADLS Gen2 account, traffic captured.
* no flag (``record_mode=none``) -> vcrpy serves the committed cassette,
  the backend is built from a fake connection string, zero network.

Run instructions are in ``README.md``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from collections.abc import Callable

pytestmark = pytest.mark.vcr


def test_write_read_roundtrip(azure_backend: object) -> None:
    """Happy-path baseline: ``write`` then ``read_bytes`` round-trips.

    Proves the cassette captures a full multi-request SDK exchange (HNS
    detection probe + create/append/flush + read) and replays it green.
    """
    payload = b"hello from the bk-181 cassette/replay PoC"
    # overwrite=True keeps re-recording idempotent: the fixed-name file
    # persists on the account between record runs.
    azure_backend.write("poc-happy.txt", payload, overwrite=True)  # type: ignore[attr-defined]

    assert azure_backend.read_bytes("poc-happy.txt") == payload  # type: ignore[attr-defined]


def test_bug197_read_bytes_on_hns_directory_returns_empty(
    azure_backend: object,
    hns_directory: Callable[[str], str],
) -> None:
    """The BUG-197 unhappy case, replayed from a cassette.

    BUG-197: ``read_bytes`` on an HNS *directory* path silently returns
    ``b""`` instead of raising ``InvalidPath``. The assertion below freezes
    the *current buggy* behaviour -- exactly how the backlog says the live
    HNS tests "freeze the actual behaviour ... must be flipped back to
    assert ``InvalidPath`` once the fix lands".

    The directory is a real HNS directory blob (``hdi_isfolder=true``), the
    marker Azurite cannot emulate. Recording this proves the cassette
    captures the HNS-only traffic the whole BUG-195..203 family depends on;
    once committed it is a zero-cost Stage 1 regression guard.
    """
    dirpath = hns_directory("poc-dir197")

    # Frozen buggy behaviour (BUG-197). Flip to pytest.raises(InvalidPath)
    # and re-record once the backend fix lands.
    assert azure_backend.read_bytes(dirpath) == b""  # type: ignore[attr-defined]
