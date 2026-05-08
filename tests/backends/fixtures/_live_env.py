"""Live cloud env-var validation for Stage 3 fixtures.

Each helper returns the validated connection record or fails loud via
``pytest.fail``. Silent skips defeat the point of opting into live tests,
so the helpers fail rather than skip when the opt-in flag is set but
credentials are missing or point at a local emulator.

The opt-in flags themselves (``RS_TEST_LIVE_HNS=1``) are checked at the
fixture-factory level, not here. A helper is only called once the
corresponding factory has decided the user has asked for the live tier.

The ``load_dotenv(override=False)`` backstop runs *inside* each helper
rather than at module import time. Module-level loading would pull
``.env`` secrets into ``os.environ`` on every ``hatch run test`` session
(because ``_load_all`` imports the live-fixture modules unconditionally),
defeating the conditional load in
``tests.conftest._maybe_load_dotenv_for_live`` whose contract is "a
regular ``hatch run test`` does not pull credentials into its
environment". Lazy load preserves that contract while still covering the
niche where the user runs with ``RS_TEST_LIVE_HNS=1`` exported but
without ``-m live``.

Generalisation
==============

The validator core is descriptor-driven: the per-fixture
``live_opt_in_env`` and ``live_creds_env`` fields parsed by
``_loader.py`` carry the env-var names, and ``require_live_credentials``
walks them. ``require_azure_live_connection_string`` is a thin
backend-specific wrapper that adds the Azurite signature check and
extracts the single connection-string value. ``require_s3_live_credentials``
is the S3 sibling: it validates the three AWS credential env vars through
the descriptor-driven path (no per-value emulator check there, because
``AWS_ACCESS_KEY_ID`` values don't embed endpoint URLs), then separately
checks ``AWS_ENDPOINT_URL`` / ``AWS_S3_ENDPOINT_URL`` against
``_S3_EMULATOR_FRAGMENTS`` — those vars are optional and absent from
``live_creds_env``, so the guard lives outside the core walker.
"""

from __future__ import annotations

import os

import pytest

from tests.backends.fixtures._loader import FixtureDescriptor, load_fixture

# Connection-string fragments that unambiguously identify Azurite.
# ``UseDevelopmentStorage=true`` is the shorthand; ``AccountName=devstoreaccount1``
# is Azurite's well-known emulator account, globally reserved on real
# Azure. Tunnelled real accounts may legitimately contain ``127.0.0.1``
# or ``localhost`` in BlobEndpoint, so those tokens are not Azurite signatures.
_AZURITE_FRAGMENTS = ("UseDevelopmentStorage=true", "AccountName=devstoreaccount1")


def _load_dotenv_backstop() -> None:
    """Lazy ``.env`` load — see module docstring for the rationale."""
    from dotenv import load_dotenv  # noqa: PLC0415 -- intentional lazy import

    load_dotenv(override=False)


def require_live_credentials(
    descriptor: FixtureDescriptor,
    *,
    emulator_signatures: tuple[str, ...] = (),
    emulator_label: str | None = None,
) -> dict[str, str]:
    """Return every env var listed in ``descriptor.live_creds_env``.

    Fails loud when:

    * the descriptor has no ``live_creds_env`` (mis-configured TOML);
    * any required env var is missing, empty, or whitespace-only;
    * any value contains a fragment from ``emulator_signatures``
      (caller signals "this looks like an emulator, not a real account").

    The opt-in flag itself (``descriptor.live_opt_in_env``) is checked
    at the fixture-factory level, not here. A descriptor lacking that
    flag is unusual but not an error from the validator's perspective —
    callers that wrap this helper assert on it before calling.
    """
    _load_dotenv_backstop()

    if not descriptor.live_creds_env:
        pytest.fail(f"fixture {descriptor.name!r} has no live_creds_env; check fixtures.toml")

    opt_in = descriptor.live_opt_in_env
    gate = f"{opt_in}=1 set but " if opt_in else ""

    out: dict[str, str] = {}
    for env_var in descriptor.live_creds_env:
        value = os.environ.get(env_var)
        if not value or not value.strip():
            pytest.fail(f"{gate}{env_var} is empty")
        if emulator_signatures and any(frag in value for frag in emulator_signatures):
            label = emulator_label or "an emulator"
            pytest.fail(f"{gate}{env_var} points at {label}; the live suite needs a real account")
        out[env_var] = value
    return out


# Endpoint-URL fragments that identify local S3 emulators (moto server,
# MinIO, LocalStack). Applied only to AWS_ENDPOINT_URL / AWS_S3_ENDPOINT_URL
# — the eu-central-1 region string is not checked here.
_S3_EMULATOR_FRAGMENTS = ("127.0.0.1", "localhost", ":9000", ":5000", ":4566")


def require_s3_live_credentials() -> dict[str, str]:
    """Return AWS credentials for a real S3 account.

    Wraps ``require_live_credentials`` for the three required creds, then
    additionally fails loud if ``AWS_ENDPOINT_URL`` or
    ``AWS_S3_ENDPOINT_URL`` contains an emulator fragment. Those vars are
    optional and therefore absent from ``live_creds_env``, but if set they
    must not redirect traffic to a local emulator.
    """
    creds = require_live_credentials(
        load_fixture("s3_live"),
        emulator_signatures=(),
        emulator_label=None,
    )
    for endpoint_var in ("AWS_ENDPOINT_URL", "AWS_S3_ENDPOINT_URL"):
        value = os.environ.get(endpoint_var, "")
        if value and any(frag in value for frag in _S3_EMULATOR_FRAGMENTS):
            pytest.fail(
                f"RS_TEST_LIVE_S3=1 set but {endpoint_var} points at an S3 emulator;"
                " the live suite needs a real AWS account"
            )
    return creds


def require_azure_live_connection_string() -> str:
    """Return ``AZURE_STORAGE_CONNECTION_STRING`` for a real ADLS Gen2 account.

    Fails loud when the env var is empty, whitespace-only, or carries an
    Azurite signature. Azurite does not emulate Hierarchical Namespace,
    so live HNS coverage is impossible against it.

    The legacy live-HNS suite under ``tests/backends/azure/test_live_hns.py``
    keeps its own inline copy of this validator pending BK-182's deletion
    of that suite. The conformance fixtures ``azure_live`` /
    ``azure_live_async`` are the first consumers of this shared helper.
    """
    creds = require_live_credentials(
        load_fixture("azure_live"),
        emulator_signatures=_AZURITE_FRAGMENTS,
        emulator_label="Azurite",
    )
    return creds["AZURE_STORAGE_CONNECTION_STRING"]


__all__ = [
    "require_azure_live_connection_string",
    "require_live_credentials",
    "require_s3_live_credentials",
]
