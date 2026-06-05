"""``driveItem`` JSON → model mapping and facet helpers for the Graph backend.

Pure functions over a parsed Graph ``driveItem`` body: facet discrimination
(file vs folder), the FileInfo field map, the file-hash extraction, and the
pre-signed download-URL accessor. Kept in one place so the read, list, and
transfer paths share a single mapping rather than each re-deriving it from the
raw JSON.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from remote_store._models import FileInfo
from remote_store._path import RemotePath
from remote_store.backends._fileinfo import _clean_etag, _name_from_path

if TYPE_CHECKING:
    from collections.abc import Mapping

# Graph annotates a file item with the pre-signed download URL under this key;
# the read/range paths stream from it directly (no Authorization header).
DOWNLOAD_URL_KEY = "@microsoft.graph.downloadUrl"


def is_folder_item(item: Mapping[str, Any]) -> bool:
    """Return ``True`` when *item* carries the Graph ``folder`` facet."""
    return "folder" in item


def is_file_item(item: Mapping[str, Any]) -> bool:
    """Return ``True`` when *item* carries the Graph ``file`` facet."""
    return "file" in item


def download_url(item: Mapping[str, Any]) -> str | None:
    """Return the pre-signed ``@microsoft.graph.downloadUrl``, or ``None``."""
    url = item.get(DOWNLOAD_URL_KEY)
    return url if isinstance(url, str) else None


def parse_graph_datetime(value: object) -> datetime:
    """Parse a Graph RFC 3339 timestamp into a timezone-aware ``datetime``.

    ``datetime.fromisoformat`` accepts the trailing ``Z`` only on Python 3.11+;
    the ``>=3.10`` floor needs it normalised to ``+00:00`` first. A missing or
    unparseable value falls back to the UTC epoch so ``modified_at`` stays a
    real ``datetime`` (Graph reliably returns the field, so this is defensive).
    """
    if not isinstance(value, str) or not value:
        return datetime.fromtimestamp(0, tz=timezone.utc)
    normalized = f"{value[:-1]}+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return datetime.fromtimestamp(0, tz=timezone.utc)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def item_to_fileinfo(item: Mapping[str, Any], key: str) -> FileInfo:
    """Map a file ``driveItem`` to a ``FileInfo`` for store key *key*.

    ``file.hashes`` rides ``extra["graph.file.hashes"]`` when present; ``digest``
    is left unset (no canonical-hash selection in v1) and ``metadata`` is
    ``None`` (the backend does not declare user metadata).
    """
    file_facet = item.get("file") or {}
    extra: dict[str, object] = {}
    hashes = file_facet.get("hashes")
    if isinstance(hashes, dict) and hashes:
        extra["graph.file.hashes"] = dict(hashes)
    return FileInfo(
        path=RemotePath(key),
        name=item.get("name") or _name_from_path(key),
        size=int(item.get("size") or 0),
        modified_at=parse_graph_datetime(item.get("lastModifiedDateTime")),
        etag=_clean_etag(item.get("eTag")),
        content_type=file_facet.get("mimeType"),
        metadata=None,
        extra=extra,
    )
