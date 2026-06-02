"""Raw SDK targets — direct SDK calls without remote-store overhead."""

from __future__ import annotations

import pathlib
from typing import Any

from benchmarks.targets._protocol import BenchTarget


class PathLibRawTarget(BenchTarget):
    """Direct pathlib/shutil operations on a local directory."""

    def __init__(self, root: str) -> None:
        self._root = pathlib.Path(root)

    @property
    def label(self) -> str:
        return "pathlib_raw"

    def write(self, path: str, data: bytes) -> None:
        full = self._root / path
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_bytes(data)

    def read(self, path: str) -> bytes:
        return (self._root / path).read_bytes()

    def exists(self, path: str) -> bool:
        return (self._root / path).exists()

    def delete(self, path: str) -> None:
        (self._root / path).unlink()

    def list_files(self, prefix: str) -> list[str]:
        base = self._root / prefix
        return [str(p.relative_to(self._root)) for p in base.iterdir() if p.is_file()]


class Boto3RawTarget(BenchTarget):
    """Direct boto3 calls against S3 / MinIO."""

    def __init__(self, bucket: str, client: Any) -> None:
        self._bucket = bucket
        self._client = client

    @property
    def label(self) -> str:
        return "boto3_raw"

    def write(self, path: str, data: bytes) -> None:
        self._client.put_object(Bucket=self._bucket, Key=path, Body=data)

    def read(self, path: str) -> bytes:
        resp = self._client.get_object(Bucket=self._bucket, Key=path)
        body = resp["Body"]
        try:
            return body.read()
        finally:
            body.close()

    def exists(self, path: str) -> bool:
        try:
            self._client.head_object(Bucket=self._bucket, Key=path)
            return True
        except self._client.exceptions.ClientError:
            return False

    def delete(self, path: str) -> None:
        self._client.delete_object(Bucket=self._bucket, Key=path)

    def list_files(self, prefix: str) -> list[str]:
        paginator = self._client.get_paginator("list_objects_v2")
        files: list[str] = []
        # Ensure prefix ends with / for directory-like listing
        pfx = prefix.rstrip("/") + "/" if prefix else ""
        for page in paginator.paginate(Bucket=self._bucket, Prefix=pfx):
            for obj in page.get("Contents", []):
                files.append(obj["Key"])
        return files

    def iter_children(self, prefix: str) -> list[str]:
        """Immediate children (files + subfolders) via a single delimited walk."""
        pfx = prefix.rstrip("/") + "/" if prefix else ""
        paginator = self._client.get_paginator("list_objects_v2")
        names: list[str] = []
        for page in paginator.paginate(Bucket=self._bucket, Prefix=pfx, Delimiter="/"):
            names.extend(cp["Prefix"] for cp in page.get("CommonPrefixes", []))
            names.extend(obj["Key"] for obj in page.get("Contents", []))
        return names


class ParamikoRawTarget(BenchTarget):
    """Direct paramiko SFTP calls."""

    def __init__(self, host: str, port: int, username: str, password: str, base_path: str) -> None:
        import paramiko

        self._base_path = base_path
        self._transport = paramiko.Transport((host, port))
        self._transport.connect(username=username, password=password)
        self._sftp = paramiko.SFTPClient.from_transport(self._transport)
        assert self._sftp is not None

    @property
    def label(self) -> str:
        return "paramiko_raw"

    def _full(self, path: str) -> str:
        return f"{self._base_path}/{path}"

    def _mkdir_p(self, remote_dir: str) -> None:
        """Recursively create remote directories."""
        parts = remote_dir.split("/")
        current = ""
        for part in parts:
            if not part:
                current = "/"
                continue
            current = f"{current}/{part}" if current != "/" else f"/{part}"
            try:
                self._sftp.stat(current)
            except FileNotFoundError:
                self._sftp.mkdir(current)

    def write(self, path: str, data: bytes) -> None:
        full = self._full(path)
        parent = full.rsplit("/", 1)[0]
        self._mkdir_p(parent)
        with self._sftp.file(full, "wb") as f:
            f.write(data)

    def read(self, path: str) -> bytes:
        with self._sftp.file(self._full(path), "rb") as f:
            f.prefetch()
            return f.read()

    def exists(self, path: str) -> bool:
        try:
            self._sftp.stat(self._full(path))
            return True
        except FileNotFoundError:
            return False

    def delete(self, path: str) -> None:
        self._sftp.remove(self._full(path))

    def list_files(self, prefix: str) -> list[str]:
        full = self._full(prefix)
        result: list[str] = []
        self._list_recursive(full, result)
        return result

    def _list_recursive(self, path: str, result: list[str]) -> None:
        import stat

        for entry in self._sftp.listdir_attr(path):
            child = f"{path}/{entry.filename}"
            if stat.S_ISDIR(entry.st_mode):  # type: ignore[arg-type]
                self._list_recursive(child, result)
            else:
                result.append(child)

    def close(self) -> None:
        self._sftp.close()
        self._transport.close()


class AzureBlobRawTarget(BenchTarget):
    """Direct azure-storage-blob calls."""

    def __init__(self, container: str, connection_string: str) -> None:
        from azure.storage.blob import BlobServiceClient

        self._service = BlobServiceClient.from_connection_string(connection_string)
        self._container = self._service.get_container_client(container)

    @property
    def label(self) -> str:
        return "azure_blob_raw"

    def write(self, path: str, data: bytes) -> None:
        self._container.upload_blob(name=path, data=data, overwrite=True)

    def read(self, path: str) -> bytes:
        return self._container.download_blob(path).readall()

    def exists(self, path: str) -> bool:
        from azure.core.exceptions import ResourceNotFoundError

        try:
            self._container.get_blob_client(path).get_blob_properties()
            return True
        except ResourceNotFoundError:
            return False

    def delete(self, path: str) -> None:
        self._container.delete_blob(path)

    def list_files(self, prefix: str) -> list[str]:
        pfx = prefix.rstrip("/") + "/" if prefix else ""
        return [b.name for b in self._container.list_blobs(name_starts_with=pfx)]

    def close(self) -> None:
        self._service.close()
