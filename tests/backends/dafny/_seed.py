"""Build a fresh ``DafnyOracleBackend`` seeded from a literal tree (ID-187).

The seed is the source of truth. Never enumerate a live backend to derive
it: re-deriving the seed through the operation under test would let a
buggy backend seed a matching-buggy oracle and hide the divergence
(Safe/Unsafe-pair discipline, ``sdd/formal/README.md`` § Design decisions).
"""

from __future__ import annotations

from tests.backends.dafny._helpers import DafnyOracleBackend


def build_oracle(tree: dict[str, bytes]) -> DafnyOracleBackend:
    oracle = DafnyOracleBackend()
    for path, data in tree.items():
        oracle.write(path, data)
    return oracle
