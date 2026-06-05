"""Microsoft Graph backend sub-package (OneDrive / SharePoint / Teams files).

Re-exports the three public symbols. Importing this package requires the
``graph`` extra (``httpx`` / ``msal`` / ``platformdirs``); the parent
``remote_store.aio.backends`` package guards the import so ``import
remote_store`` works without the extra installed.
"""

from __future__ import annotations

from remote_store.aio.backends._graph.auth import GraphAuth
from remote_store.aio.backends._graph.backend import GraphBackend
from remote_store.aio.backends._graph.utils import GraphUtils

__all__ = ["GraphAuth", "GraphBackend", "GraphUtils"]
