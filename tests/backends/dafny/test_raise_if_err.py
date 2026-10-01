"""Direct unit tests of the oracle adapter's ``_raise_if_err`` and ``close()``.

The Dafny ``MemoryBackend`` oracle never returns ``Error.ResourceLocked``
(the in-memory filesystem has no lock condition), nor ``BackendUnavailable``
(it is non-terminal: ``closeIsTerminal`` is false, so ``Live()`` never
fails). The conformance suite that drives the oracle therefore never
exercises those dispatch arms (ADR-0024, Consequences: "Ships as a coupled
bundle"). The dispatch tests construct the Dafny ``Result_Err`` variant by
hand and pump it through ``_raise_if_err`` to prove each arm maps to its
runtime class, keeping the formal-oracle error surface complete. The
``close()`` test pins that the adapter drives the model's ``Close()``
rather than the ABC's no-op.
"""

from __future__ import annotations

import pytest

from remote_store._errors import BackendUnavailable, ResourceLocked

# _helpers owns the sys.path wiring for the compiled oracle and re-exports it
# as ``_dafny_module``; pulling the constructors from there keeps this test
# independent of import ordering (a direct ``import module_`` only resolves
# after _helpers has run).
from tests.backends.dafny._helpers import (
    _BACKEND_NAME,
    DafnyOracleBackend,
    _dafny_module,
    _raise_if_err,
    _str_to_dafny,
)


@pytest.mark.spec("ERR-013")
def test_raise_if_err_dispatches_resource_locked() -> None:
    """A Dafny ``Error.ResourceLocked`` lifts to the runtime ResourceLocked."""
    err = _dafny_module.Error_ResourceLocked(_str_to_dafny("contracts/report.docx"), _str_to_dafny("graph"))
    result = _dafny_module.Result_Err(err)
    with pytest.raises(ResourceLocked) as excinfo:
        _raise_if_err(result)
    assert excinfo.value.path == "contracts/report.docx"
    assert excinfo.value.backend == _BACKEND_NAME


@pytest.mark.spec("BE-020")
def test_raise_if_err_dispatches_backend_unavailable() -> None:
    """A Dafny ``Error.BackendUnavailable`` lifts to the runtime BackendUnavailable."""
    result = _dafny_module.Result_Err(_dafny_module.Error_BackendUnavailable(_str_to_dafny("minimal")))
    with pytest.raises(BackendUnavailable, match="is closed") as excinfo:
        _raise_if_err(result)
    assert excinfo.value.backend == _BACKEND_NAME


@pytest.mark.spec("BE-020")
def test_close_drives_the_dafny_close() -> None:
    """``close()`` reaches the model's Close(), and the non-terminal oracle stays usable."""
    oracle = DafnyOracleBackend()
    oracle.close()
    assert oracle._mb.closed is True
    assert oracle.close_is_terminal is False
    assert oracle.exists("") is True
