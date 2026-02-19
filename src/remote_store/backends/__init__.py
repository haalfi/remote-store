"""Backend implementations."""

from remote_store.backends._local import LocalBackend

__all__ = ["LocalBackend"]

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
    from remote_store.backends._sftp import SFTPBackend

    __all__ = [*__all__, "SFTPBackend"]
except ImportError:  # pragma: no cover
    pass
