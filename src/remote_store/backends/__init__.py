"""Backend implementations."""

from remote_store.backends._local import LocalBackend

__all__ = ["LocalBackend"]

try:
    from remote_store.backends._s3 import S3Backend

    __all__ = [*__all__, "S3Backend"]
except ImportError:
    pass
