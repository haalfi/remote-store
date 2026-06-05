"""Direct unit test of the ``_raise_if_err`` ResourceLocked dispatch arm (ERR-013).

The Dafny ``MemoryBackend`` oracle never returns ``Error.ResourceLocked`` —
the in-memory filesystem has no lock condition — so the conformance suite
that drives the oracle never exercises that dispatch arm (ADR-0024 §
Bundled implementation). This test constructs the Dafny ``Result_Err``
variant by hand and pumps it through ``_raise_if_err`` to prove the arm
maps it to the runtime ``remote_store.ResourceLocked``, keeping the
formal-oracle error surface complete as the variant lands.
"""

from __future__ import annotations

import pytest

from remote_store._errors import ResourceLocked

# _helpers owns the sys.path wiring for the compiled oracle and re-exports it
# as ``_dafny_module``; pulling the constructors from there keeps this test
# independent of import ordering (a direct ``import module_`` only resolves
# after _helpers has run).
from tests.backends.dafny._helpers import _BACKEND_NAME, _dafny_module, _raise_if_err, _str_to_dafny


@pytest.mark.spec("ERR-013")
def test_raise_if_err_dispatches_resource_locked() -> None:
    """A Dafny ``Error.ResourceLocked`` lifts to the runtime ResourceLocked."""
    err = _dafny_module.Error_ResourceLocked(_str_to_dafny("contracts/report.docx"), _str_to_dafny("graph"))
    result = _dafny_module.Result_Err(err)
    with pytest.raises(ResourceLocked) as excinfo:
        _raise_if_err(result)
    assert excinfo.value.path == "contracts/report.docx"
    assert excinfo.value.backend == _BACKEND_NAME
