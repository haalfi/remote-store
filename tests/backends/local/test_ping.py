"""LocalBackend check_health() error-mapping tests -- PING-003.

The healthy-path assertion (``check_health() is None`` on a fresh local
fixture) lives in tests/backends/conformance/test_check_health.py. This
file covers the LocalBackend-specific failure-injection branches: a
missing root directory (``NotFound``) and an unreadable root
(``PermissionDenied``). Both require filesystem-level manipulation
(``rmdir``, ``patch("os.access")``) that has no conformance analogue.

Migrated from tests/test_ping.py (BK-217 / BK-191 slice 2/6).
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

from remote_store._errors import NotFound, PermissionDenied
from remote_store.backends._local import LocalBackend

if TYPE_CHECKING:
    from pathlib import Path


class TestLocalCheckHealth:
    @pytest.mark.spec("PING-003")
    def test_local_missing_root(self, tmp_path: Path) -> None:
        missing = tmp_path / "nonexistent"
        backend = LocalBackend(root=str(missing))
        missing.rmdir()
        with pytest.raises(NotFound, match="Root directory not found"):
            backend.check_health()

    @pytest.mark.spec("PING-003")
    def test_local_unreadable_root(self, tmp_path: Path) -> None:
        backend = LocalBackend(root=str(tmp_path))
        with patch("os.access", return_value=False), pytest.raises(PermissionDenied, match="not readable"):
            backend.check_health()
