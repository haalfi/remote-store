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

from remote_store._models import FileInfo, WriteResult
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


def item_to_write_result(
    item: Mapping[str, Any],
    key: str,
    size: int,
    metadata: Mapping[str, str] | None,
) -> WriteResult:
    """Map a write-response ``driveItem`` to a native ``WriteResult`` for *key*.

    Both ``PUT /content`` and the final upload-session chunk return a full
    ``driveItem`` body; this populates ``source="native"`` with ``size``,
    ``etag`` (cleaned to match ``get_file_info``), and ``last_modified``.
    ``version_id`` rides the SharePoint ``listItem`` version where Graph
    surfaces one, ``None`` otherwise. ``digest`` is left ``None`` — no
    canonical hash is selected from ``file.hashes`` in v1. ``metadata`` echoes
    the caller's input mapping (``None`` when none was supplied).

    *size* is the byte count the backend wrote (authoritative even when the
    response omits or under-reports ``size``), not re-derived from the body.
    """
    return WriteResult(
        path=RemotePath(key),
        size=size,
        source="native",
        etag=_clean_etag(item.get("eTag")),
        version_id=_version_id(item),
        last_modified=parse_graph_datetime(item.get("lastModifiedDateTime")),
        metadata=metadata,
    )


def _version_id(item: Mapping[str, Any]) -> str | None:
    """Return a SharePoint version identifier from *item*, or ``None``.

    SharePoint-backed drives expose the published version under
    ``publication.versionId``; personal OneDrive omits it. The value is opaque
    and surfaced verbatim when a non-empty string is present.
    """
    publication = item.get("publication")
    if isinstance(publication, dict):
        version = publication.get("versionId")
        if isinstance(version, str) and version:
            return version
    return None
