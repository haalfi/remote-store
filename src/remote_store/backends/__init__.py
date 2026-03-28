"""Backend implementations."""

from remote_store.backends._http import ReadOnlyHttpBackend
from remote_store.backends._local import LocalBackend
from remote_store.backends._memory import MemoryBackend

__all__ = ["LocalBackend", "MemoryBackend", "ReadOnlyHttpBackend"]

try:
    from remote_store.backends._s3 import S3Backend

    __all__ = [*__all__, "S3Backend"]
except ImportError:  # pragma: no cover
    pass

try:
    from remote_store.backends._s3_pyarrow import S3PyArrowBackend

    __all__ = [*__all__, "S3PyArrowBackend"]
except ImportError:  # pragma: no cover
    pass

try:
    from remote_store.backends._sftp import SFTPBackend, SFTPUtils

    __all__ = [*__all__, "SFTPBackend", "SFTPUtils"]
except ImportError:  # pragma: no cover
    pass

try:
    from remote_store.backends._azure import AzureBackend

    __all__ = [*__all__, "AzureBackend"]
except ImportError:  # pragma: no cover
    pass

try:
    from remote_store.backends._sqlalchemy import SQLBlobBackend

    __all__ = [*__all__, "SQLBlobBackend"]
except ImportError:  # pragma: no cover
    pass

try:
    from remote_store.backends._sqlalchemy import ArrowSerializer, ResultSerializer, SQLQueryBackend

    __all__ = [*__all__, "ArrowSerializer", "ResultSerializer", "SQLQueryBackend"]
except ImportError:  # pragma: no cover
    pass
