"""Live cloud env-var validation for Stage 3 fixtures.

Each helper returns the validated connection record or fails loud via
``pytest.fail``. Silent skips defeat the point of opting into live tests,
so the helpers fail rather than skip when the opt-in flag is set but
credentials are missing or point at a local emulator.

The opt-in flags themselves (``RS_TEST_LIVE_HNS=1``, ``RS_TEST_LIVE_S3=1``)
are checked at the fixture-factory level, not here. A helper is only
called once the corresponding factory has decided the user has asked for
the live tier.

A ``load_dotenv(override=False)`` runs at module level for callers that
import this from a shell where ``-m live`` was not in the mark expression
(``tests.conftest._maybe_load_dotenv_for_live`` only loads under that
selector). ``override=False`` keeps shell/CI values authoritative.
"""

from __future__ import annotations

import os

import pytest
from dotenv import load_dotenv

# Backstop load. The primary path is ``tests.conftest._maybe_load_dotenv_for_live``,
# which loads ``.env`` before collection when ``-m live`` is in the mark
# expression. This module-level call covers the niche where a user runs
# with the opt-in env var exported but without ``-m live`` (so the
# conftest heuristic skips the load).
load_dotenv(override=False)


# Connection-string fragments that unambiguously identify Azurite.
# ``UseDevelopmentStorage=true`` is the shorthand; ``AccountName=devstoreaccount1``
# is Azurite's well-known emulator account, globally reserved on real
# Azure. Tunnelled real accounts may legitimately contain ``127.0.0.1``
# or ``localhost`` in BlobEndpoint, so those tokens are not Azurite signatures.
_AZURITE_FRAGMENTS = ("UseDevelopmentStorage=true", "AccountName=devstoreaccount1")


def require_azure_live_connection_string() -> str:
    """Return ``AZURE_STORAGE_CONNECTION_STRING`` for a real ADLS Gen2 account.

    Fails loud when the env var is empty or carries an Azurite signature.
    Azurite does not emulate Hierarchical Namespace, so live HNS coverage
    is impossible against it.

    The legacy live-HNS suite under ``tests/backends/azure/test_live_hns.py``
    keeps its own inline copy of this validator pending BK-182's deletion of
    that suite. The new conformance fixture ``azure_live`` is the first
    consumer of this shared helper.
    """
    conn = os.environ.get("AZURE_STORAGE_CONNECTION_STRING")
    if not conn:
        pytest.fail("RS_TEST_LIVE_HNS=1 set but AZURE_STORAGE_CONNECTION_STRING is empty")
    if any(frag in conn for frag in _AZURITE_FRAGMENTS):
        pytest.fail(
            "RS_TEST_LIVE_HNS=1 set but AZURE_STORAGE_CONNECTION_STRING points at Azurite; "
            "the live HNS suite needs a real ADLS Gen2 account"
        )
    return conn


__all__ = [
    "require_azure_live_connection_string",
]
