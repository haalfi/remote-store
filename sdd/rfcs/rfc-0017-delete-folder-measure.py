"""Measure RFC-0017's kernel `delete_folder` sequence against today's classes (BK-396).

The derivation behind BK-389 dossier decision 8's sequence and RFC-0017's
`delete_folder` rows: every cell, fault, race and round-trip figure there is
printed by this script. Run from the repository root, in order:

    hatch run python sdd/rfcs/rfc-0017-delete-folder-measure.py today
    hatch run python sdd/rfcs/rfc-0017-delete-folder-measure.py inject
    hatch run python sdd/rfcs/rfc-0017-delete-folder-measure.py race [runs]
    hatch run python sdd/rfcs/rfc-0017-delete-folder-measure.py kernel
    hatch run python sdd/rfcs/rfc-0017-delete-folder-measure.py compare [section ...]

Results land in tmp/rfc-0017-delete-folder/ (gitignored). `inject`, `kernel`
and the `azure` and `extra` classes of `today` need Azurite's blob service on
127.0.0.1:10000; without Docker, `npm install --prefix tmp/azurite azurite`
and run its `dist/src/blob/main.js --silent --loose --blobHost 127.0.0.1
--blobPort 10000 --location tmp/azurite/data`.

`today` runs the shipped classes: MemoryBackend, LocalBackend, SFTPBackend
(the in-process paramiko server), S3Boto3Backend (moto), SQLBlobBackend
(sqlite file) and AsyncAzureBackend flat (Azurite). Graph and Azure HNS have
no emulator here; their cells are read from the code, and the kernel side
models their wire (a DELETE on an item removes a file item too).

`kernel` runs a model of the kernel over fake drivers, with one option switch
per BK-396 item (the `Kernel` docstring below). The fake drivers issue the
class's real wire calls where one is reachable and count them. `compare`
diffs the model against `today`: a cell matches when the answer and the
post-state both equal today's.

Bounds: a model, not the kernel. It shows what the decided sequence answers
over each wire, not that BK-389's code will; that code's fake-driver suite
does. The SFTP dead-channel fault at the removal is injected at the driver,
with the probe's reconnect succeeding; a probe that itself fails is a
separate set of cells (`compare extra`, today's by `today extra`). The race
cells inject one change deterministically, where `race` measures today
under threads.
"""

from __future__ import annotations

import argparse
import asyncio
import collections
import contextlib
import errno
import itertools
import json
import logging
import os
import shutil
import socket
import stat as stat_mod
import sys
import tempfile
import threading
import uuid
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
OUT = ROOT / "tmp" / "rfc-0017-delete-folder"
OUT.mkdir(parents=True, exist_ok=True)


from remote_store._errors import (
    BackendUnavailable,
    DirectoryNotEmpty,
    InvalidPath,
    NotFound,
    PermissionDenied,
    RemoteStoreError,
)

# ---- today ----


HIER_STATES = {
    # name: (key, files, empty_dirs)
    "empty folder": ("e", [], ["e"]),
    "folder holding files": ("d", ["d/a", "d/s/c"], []),
    "folder holding only an empty folder": ("n", [], ["n/m"]),
    "file f": ("f", ["f"], []),
    "key under a file f/x": ("f/x", ["f"], []),
    "absent": ("z", [], []),
}


def arrange_links(root: Path, key: str, target: str) -> None:
    """The link-state fixture: tf, tn/a, an empty te, d/f, and the link at *key* (d/l for the nested state)."""
    arrange_fs(root, ["tf", "tn/a", "d/f"], ["te"])
    link = root / ("d/l" if key == "d" else key)
    os.symlink(root / target, link)


LOCAL_SYMLINKS = {
    # the nested state: d holds a file and a link d/l to the non-empty tn; the key is d
    "folder holding a link to a non-empty dir": ("d", "tn"),
    # name: (key, target relative to root or None for dangling)
    "dangling symlink": ("sd", "nowhere"),
    "symlink to a file": ("sf", "tf"),
    "symlink to an empty dir": ("se", "te"),
    "symlink to a non-empty dir": ("sn", "tn"),
}
FLAT_STATES = {
    "files under the prefix": ("d", ["d/a", "d/s/c"]),
    "file f, nothing under it": ("f", ["f"]),
    "a file and a prefix both": ("b", ["b", "b/x"]),
    "absent": ("z", []),
    "key under a file f/x": ("f/x", ["f"]),
}
CALLS = [(r, m) for r in (False, True) for m in (False, True)]


def answer(exc: BaseException | None) -> str:
    if exc is None:
        return "ok"
    from remote_store._errors import RemoteStoreError

    name = type(exc).__name__
    if type(exc) is RemoteStoreError:
        return "RemoteStoreError(untyped)"
    if not isinstance(exc, RemoteStoreError):
        return f"LEAK:{name}"
    return name


class Counter:
    def __init__(self) -> None:
        self.n = 0
        self.ops: collections.Counter[str] = collections.Counter()

    def hit(self, op: str) -> None:
        self.n += 1
        self.ops[op] += 1

    def reset(self) -> None:
        self.n = 0
        self.ops = collections.Counter()


# --- hierarchical, filesystem-arranged (Local, SFTP) -------------------------


def arrange_fs(root: Path, files: list[str], dirs: list[str]) -> None:
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)
    for d in dirs:
        (root / d).mkdir(parents=True, exist_ok=True)
    for f in files:
        p = root / f
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"x")


def fs_state(root: Path) -> list[str]:
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        rel = os.path.relpath(dirpath, root)
        for d in dirnames:
            p = os.path.normpath(os.path.join(rel, d))
            out.append(p + "/")
        for f in filenames:
            out.append(os.path.normpath(os.path.join(rel, f)))
    return sorted(out)


def count_os(counter: Counter):
    names = ["stat", "lstat", "rmdir", "unlink", "scandir", "listdir", "open"]
    saved = {n: getattr(os, n) for n in names}

    def wrap(n):
        f = saved[n]

        def w(*a, **k):
            counter.hit(n)
            return f(*a, **k)

        return w

    @contextlib.contextmanager
    def cm():
        for n in names:
            setattr(os, n, wrap(n))
        try:
            yield
        finally:
            for n in names:
                setattr(os, n, saved[n])

    return cm()


def run_local() -> list[dict]:
    from remote_store.backends._local import LocalBackend

    rows = []
    base = Path(tempfile.mkdtemp(dir=OUT))
    root = base / "root"
    c = Counter()
    for state, (key, files, dirs) in HIER_STATES.items():
        for rec, mok in CALLS:
            arrange_fs(root, files, dirs)
            b = LocalBackend(root=str(root))
            c.reset()
            exc = None
            with count_os(c):
                try:
                    b.delete_folder(key, recursive=rec, missing_ok=mok)
                except Exception as e:  # noqa: BLE001
                    exc = e
            rows.append(
                dict(
                    cls="local",
                    state=state,
                    key=key,
                    recursive=rec,
                    missing_ok=mok,
                    answer=answer(exc),
                    post=fs_state(root),
                    calls=c.n,
                    ops=dict(c.ops),
                )
            )
    for state, (key, target) in LOCAL_SYMLINKS.items():
        for rec, mok in CALLS:
            arrange_links(root, key, target)
            b = LocalBackend(root=str(root))
            c.reset()
            exc = None
            with count_os(c):
                try:
                    b.delete_folder(key, recursive=rec, missing_ok=mok)
                except Exception as e:  # noqa: BLE001
                    exc = e
            rows.append(
                dict(
                    cls="local",
                    state=state,
                    key=key,
                    recursive=rec,
                    missing_ok=mok,
                    answer=answer(exc),
                    post=fs_state(root),
                    calls=c.n,
                    ops=dict(c.ops),
                )
            )
    shutil.rmtree(base)
    return rows


def run_sftp() -> list[dict]:
    import paramiko

    from remote_store.backends._sftp import HostKeyPolicy, SFTPBackend
    from tests.backends.sftp._helpers import start_sftp_server, stop_sftp_server

    base = Path(tempfile.mkdtemp(dir=OUT))
    thread, port, _hk, stop, sock = start_sftp_server(root=str(base), host="127.0.0.1")
    c = Counter()
    names = ["stat", "lstat", "listdir_attr", "listdir_iter", "rmdir", "remove", "open", "normalize"]
    saved = {n: getattr(paramiko.SFTPClient, n) for n in names}

    def wrap(n):
        f = saved[n]

        def w(self, *a, **k):
            c.hit(n)
            return f(self, *a, **k)

        return w

    for n in names:
        setattr(paramiko.SFTPClient, n, wrap(n))
    rows = []
    try:
        b = SFTPBackend(
            host="127.0.0.1",
            port=port,
            username="testuser",
            password="testpass",
            base_path="/root",
            host_key_policy=HostKeyPolicy.AUTO_ADD,
            connect_kwargs={"allow_agent": False, "look_for_keys": False},
        )
        root = base / "root"
        for state, (key, files, dirs) in HIER_STATES.items():
            for rec, mok in CALLS:
                arrange_fs(root, files, dirs)
                b.exists("")  # warm the connection outside the count
                c.reset()
                exc = None
                try:
                    b.delete_folder(key, recursive=rec, missing_ok=mok)
                except Exception as e:  # noqa: BLE001
                    exc = e
                rows.append(
                    dict(
                        cls="sftp",
                        state=state,
                        key=key,
                        recursive=rec,
                        missing_ok=mok,
                        answer=answer(exc),
                        post=fs_state(root),
                        calls=c.n,
                        ops=dict(c.ops),
                    )
                )
        b.close()
    finally:
        for n in names:
            setattr(paramiko.SFTPClient, n, saved[n])
        stop_sftp_server(thread, stop, sock)
        shutil.rmtree(base)
    return rows


# --- Memory ------------------------------------------------------------------


def run_memory() -> list[dict]:
    from remote_store.backends._memory import MemoryBackend

    rows = []
    for state, (key, files, dirs) in HIER_STATES.items():
        for rec, mok in CALLS:
            b = MemoryBackend()
            for d in dirs:
                b.write(d + "/.k", b"x")
                b.delete(d + "/.k")
            for f in files:
                b.write(f, b"x")
            assert all(b.is_folder(d) for d in dirs), dirs
            exc = None
            try:
                b.delete_folder(key, recursive=rec, missing_ok=mok)
            except Exception as e:  # noqa: BLE001
                exc = e
            post = sorted(
                [str(fi.path) for fi in b.list_files("", recursive=True)]
                + [p + "/" for p in ("e", "d", "d/s", "n", "n/m") if b.is_folder(p)]
            )
            rows.append(
                dict(
                    cls="memory",
                    state=state,
                    key=key,
                    recursive=rec,
                    missing_ok=mok,
                    answer=answer(exc),
                    post=post,
                    calls=0,
                    ops={},
                )
            )
    return rows


# --- flat: S3Boto3 / SQLBlob / Azure flat ------------------------------------


def run_s3() -> list[dict]:
    import socket

    import boto3
    from moto.moto_server.threaded_moto_server import ThreadedMotoServer

    from remote_store.backends._s3_boto3 import S3Boto3Backend

    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    server = ThreadedMotoServer(port=port, verbose=False)
    server.start()
    url = f"http://127.0.0.1:{port}"
    rows = []
    c = Counter()
    try:
        for state, (key, files) in FLAT_STATES.items():
            for rec, mok in CALLS:
                bucket = f"m-{uuid.uuid4().hex[:8]}"
                cl = boto3.client(
                    "s3", endpoint_url=url, aws_access_key_id="t", aws_secret_access_key="t", region_name="us-east-1"
                )
                cl.create_bucket(Bucket=bucket)
                for f in files:
                    cl.put_object(Bucket=bucket, Key=f, Body=b"x")
                b = S3Boto3Backend(bucket=bucket, key="t", secret="t", region_name="us-east-1", endpoint_url=url)
                b._client.meta.events.register("before-call.s3.*", lambda model, **kw: c.hit(model.name))
                c.reset()
                exc = None
                try:
                    b.delete_folder(key, recursive=rec, missing_ok=mok)
                except Exception as e:  # noqa: BLE001
                    exc = e
                post = sorted(o["Key"] for o in cl.list_objects_v2(Bucket=bucket).get("Contents", []))
                rows.append(
                    dict(
                        cls="s3boto3",
                        state=state,
                        key=key,
                        recursive=rec,
                        missing_ok=mok,
                        answer=answer(exc),
                        post=post,
                        calls=c.n,
                        ops=dict(c.ops),
                    )
                )
                b.close()
    finally:
        server.stop()
    return rows


def run_sql() -> list[dict]:
    import sqlalchemy as sa

    from remote_store.backends._sqlalchemy import SQLBlobBackend

    rows = []
    c = Counter()
    d = Path(tempfile.mkdtemp(dir=OUT))
    for state, (key, files) in FLAT_STATES.items():
        for rec, mok in CALLS:
            b = SQLBlobBackend(url=f"sqlite:///{d}/{uuid.uuid4().hex}.db")
            for f in files:
                b.write(f, b"x")
            sa.event.listen(
                b._engine, "before_cursor_execute", lambda conn, cur, stmt, *a: c.hit(stmt.split()[0].upper())
            )
            c.reset()
            exc = None
            try:
                b.delete_folder(key, recursive=rec, missing_ok=mok)
            except Exception as e:  # noqa: BLE001
                exc = e
            n = c.n
            ops = dict(c.ops)
            post = sorted(str(fi.path) for fi in b.list_files("", recursive=True))
            rows.append(
                dict(
                    cls="sqlblob",
                    state=state,
                    key=key,
                    recursive=rec,
                    missing_ok=mok,
                    answer=answer(exc),
                    post=post,
                    calls=n,
                    ops=ops,
                )
            )
            b.close()
    shutil.rmtree(d)
    return rows


CONN = (
    "DefaultEndpointsProtocol=http;AccountName=devstoreaccount1;"
    "AccountKey=Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq/K1SZFPTOtr/KBHBeksoGMGw==;"
    "BlobEndpoint=http://127.0.0.1:10000/devstoreaccount1;"
)


def run_azure() -> list[dict]:
    from azure.core.pipeline.transport import AioHttpTransport
    from azure.storage.blob import BlobServiceClient

    from remote_store.aio.backends._azure import AsyncAzureBackend

    c = Counter()
    orig = AioHttpTransport.send

    async def send(self, request, **kw):
        c.hit(f"{request.method} {request.url.split('?')[1].split('&')[0] if '?' in request.url else ''}")
        return await orig(self, request, **kw)

    AioHttpTransport.send = send
    svc = BlobServiceClient.from_connection_string(CONN)
    rows = []

    async def go():
        for state, (key, files) in FLAT_STATES.items():
            for rec, mok in CALLS:
                cont = f"m-{uuid.uuid4().hex[:8]}"
                cc = svc.create_container(cont)
                for f in files:
                    cc.upload_blob(f, b"x")
                b = AsyncAzureBackend(container=cont, hns=False, connection_string=CONN)
                await b.exists("x")  # warm outside the count
                c.reset()
                exc = None
                try:
                    await b.delete_folder(key, recursive=rec, missing_ok=mok)
                except Exception as e:  # noqa: BLE001
                    exc = e
                n, ops = c.n, dict(c.ops)
                post = sorted(x.name for x in cc.list_blobs())
                rows.append(
                    dict(
                        cls="azure-flat",
                        state=state,
                        key=key,
                        recursive=rec,
                        missing_ok=mok,
                        answer=answer(exc),
                        post=post,
                        calls=n,
                        ops=ops,
                    )
                )
                await b.aclose()
                svc.delete_container(cont)

    try:
        asyncio.run(go())
    finally:
        AioHttpTransport.send = orig
    return rows


def run_extra() -> list[dict]:
    """PR #1057 round 1: today's answers for a probe that raises and a flat concurrent deleter.

    SFTP: the first paramiko ``stat`` raises EOFError (a dropped channel), on an
    absent key and on a file. Flat Azure: blob ``d/a`` is deleted by another
    client just before the backend's own ``delete_blob`` on it.
    """
    import paramiko
    from azure.storage.blob import BlobServiceClient
    from azure.storage.blob.aio import BlobClient

    from remote_store.aio.backends._azure import AsyncAzureBackend
    from remote_store.backends._sftp import HostKeyPolicy, SFTPBackend
    from tests.backends.sftp._helpers import start_sftp_server, stop_sftp_server

    rows = []
    base = Path(tempfile.mkdtemp(dir=OUT))
    thread, port, _hk, stop, sock = start_sftp_server(root=str(base), host="127.0.0.1")
    orig_stat = paramiko.SFTPClient.stat
    try:
        b = SFTPBackend(
            host="127.0.0.1",
            port=port,
            username="testuser",
            password="testpass",
            base_path="/root",
            host_key_policy=HostKeyPolicy.AUTO_ADD,
            connect_kwargs={"allow_agent": False, "look_for_keys": False},
        )
        root = base / "root"
        for state, (key, files) in {"absent, probe raises": ("z", []), "file f, probe raises": ("f", ["f"])}.items():
            for rec, mok in CALLS:
                arrange_fs(root, files, [])
                b.exists("")
                fired = []

                def stat(self, path, _f=fired):
                    if not _f:
                        _f.append(1)
                        raise EOFError("injected: channel dropped")
                    return orig_stat(self, path)

                paramiko.SFTPClient.stat = stat
                exc = None
                try:
                    b.delete_folder(key, recursive=rec, missing_ok=mok)
                except Exception as e:  # noqa: BLE001
                    exc = e
                finally:
                    paramiko.SFTPClient.stat = orig_stat
                rows.append(
                    dict(
                        cls="sftp",
                        state=state,
                        key=key,
                        recursive=rec,
                        missing_ok=mok,
                        answer=answer(exc),
                        post=fs_state(root),
                        calls=0,
                        ops={},
                    )
                )
        b.close()
    finally:
        paramiko.SFTPClient.stat = orig_stat
        stop_sftp_server(thread, stop, sock)
        shutil.rmtree(base)

    svc = BlobServiceClient.from_connection_string(CONN)
    orig_del = BlobClient.delete_blob

    async def go():
        for mok in (False, True):
            cont = f"m-{uuid.uuid4().hex[:8]}"
            cc = svc.create_container(cont)
            for f in ("d/a", "d/b"):
                cc.upload_blob(f, b"x")

            async def delete_blob(self, *a, **k):
                if self.blob_name == "d/a":
                    cc.get_blob_client("d/a").delete_blob()  # the concurrent deleter
                return await orig_del(self, *a, **k)

            BlobClient.delete_blob = delete_blob
            ab = AsyncAzureBackend(container=cont, hns=False, connection_string=CONN)
            exc = None
            try:
                await ab.delete_folder("d", recursive=True, missing_ok=mok)
            except Exception as e:  # noqa: BLE001
                exc = e
            finally:
                BlobClient.delete_blob = orig_del
            rows.append(
                dict(
                    cls="azure-flat",
                    state="d/a, d/b; d/a deleted concurrently",
                    key="d",
                    recursive=True,
                    missing_ok=mok,
                    answer=answer(exc),
                    post=sorted(x.name for x in cc.list_blobs()),
                    calls=0,
                    ops={},
                )
            )
            await ab.aclose()
            svc.delete_container(cont)

    asyncio.run(go())
    return rows


RUNNERS = dict(
    memory=run_memory, local=run_local, sftp=run_sftp, s3=run_s3, sql=run_sql, azure=run_azure, extra=run_extra
)


# ---- inject ----


INJ_STATES = {
    "files under the prefix": ("d", ["d/a"]),
    "file f, nothing under it": ("f", ["f"]),
    "absent": ("z", []),
}


def inject_s3() -> list[dict]:
    import socket

    import boto3
    from botocore.exceptions import ClientError
    from moto.moto_server.threaded_moto_server import ThreadedMotoServer

    from remote_store.backends._s3_boto3 import S3Boto3Backend

    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    server = ThreadedMotoServer(port=port, verbose=False)
    server.start()
    url = f"http://127.0.0.1:{port}"
    rows = []
    try:
        for state, (key, files) in INJ_STATES.items():
            for site, opname in (("list", "ListObjectsV2"), ("stat", "HeadObject")):
                for status, code in ((403, "AccessDenied"), (503, "ServiceUnavailable")):
                    for rec, mok in CALLS:
                        bucket = f"m-{uuid.uuid4().hex[:8]}"
                        cl = boto3.client(
                            "s3",
                            endpoint_url=url,
                            aws_access_key_id="t",
                            aws_secret_access_key="t",
                            region_name="us-east-1",
                        )
                        cl.create_bucket(Bucket=bucket)
                        for f in files:
                            cl.put_object(Bucket=bucket, Key=f, Body=b"x")
                        b = S3Boto3Backend(
                            bucket=bucket, key="t", secret="t", region_name="us-east-1", endpoint_url=url
                        )
                        fired = []

                        def boom(model, _op=opname, _st=status, _c=code, **kw):
                            if model.name == _op and not fired:
                                fired.append(1)
                                raise ClientError(
                                    {
                                        "Error": {"Code": _c, "Message": "inj"},
                                        "ResponseMetadata": {"HTTPStatusCode": _st},
                                    },
                                    _op,
                                )

                        b._client.meta.events.register("before-call.s3.*", boom)
                        exc = None
                        try:
                            b.delete_folder(key, recursive=rec, missing_ok=mok)
                        except Exception as e:  # noqa: BLE001
                            exc = e
                        post = sorted(o["Key"] for o in cl.list_objects_v2(Bucket=bucket).get("Contents", []))
                        rows.append(
                            dict(
                                cls="s3boto3",
                                state=state,
                                site=site,
                                fault=status,
                                fired=bool(fired),
                                recursive=rec,
                                missing_ok=mok,
                                answer=answer(exc),
                                post=post,
                            )
                        )
                        b.close()
    finally:
        server.stop()
    return rows


def inject_sql() -> list[dict]:
    import sqlalchemy as sa

    from remote_store.backends._sqlalchemy import SQLBlobBackend

    rows = []
    d = Path(tempfile.mkdtemp(dir=OUT))
    for state, (key, files) in INJ_STATES.items():
        for site in ("list", "stat"):
            for rec, mok in CALLS:
                b = SQLBlobBackend(url=f"sqlite:///{d}/{uuid.uuid4().hex}.db")
                for f in files:
                    b.write(f, b"x")
                fired = []

                def boom(conn, cur, stmt, params, ctx, many, _site=site):
                    s = stmt.upper()
                    is_list = s.startswith("SELECT") and " LIKE " in s
                    is_stat = s.startswith("SELECT") and " LIKE " not in s
                    if not fired and ((_site == "list" and is_list) or (_site == "stat" and is_stat)):
                        fired.append(1)
                        raise sa.exc.OperationalError(stmt, params, Exception("injected"))

                sa.event.listen(b._engine, "before_cursor_execute", boom)
                exc = None
                try:
                    b.delete_folder(key, recursive=rec, missing_ok=mok)
                except Exception as e:  # noqa: BLE001
                    exc = e
                sa.event.remove(b._engine, "before_cursor_execute", boom)
                post = sorted(str(fi.path) for fi in b.list_files("", recursive=True))
                rows.append(
                    dict(
                        cls="sqlblob",
                        state=state,
                        site=site,
                        fault="OperationalError",
                        fired=bool(fired),
                        recursive=rec,
                        missing_ok=mok,
                        answer=answer(exc),
                        post=post,
                    )
                )
                b.close()
    shutil.rmtree(d)
    return rows


def inject_azure() -> list[dict]:
    from azure.core.exceptions import HttpResponseError
    from azure.storage.blob import BlobServiceClient
    from azure.storage.blob.aio import BlobClient, ContainerClient

    from remote_store.aio.backends._azure import AsyncAzureBackend

    svc = BlobServiceClient.from_connection_string(CONN)
    rows = []
    orig_list = ContainerClient.list_blobs
    orig_props = BlobClient.get_blob_properties

    def err(status):
        e = HttpResponseError(message=f"injected {status}")
        e.status_code = status
        return e

    async def go():
        for state, (key, files) in INJ_STATES.items():
            for site in ("list", "stat"):
                for status in (403, 503):
                    for rec, mok in CALLS:
                        cont = f"m-{uuid.uuid4().hex[:8]}"
                        cc = svc.create_container(cont)
                        for f in files:
                            cc.upload_blob(f, b"x")
                        b = AsyncAzureBackend(container=cont, hns=False, connection_string=CONN)
                        fired = []

                        def lb(self, *a, _st=status, _site=site, **k):
                            if _site == "list" and not fired:
                                fired.append(1)
                                raise err(_st)
                            return orig_list(self, *a, **k)

                        async def gp(self, *a, _st=status, _site=site, **k):
                            if _site == "stat" and not fired:
                                fired.append(1)
                                raise err(_st)
                            return await orig_props(self, *a, **k)

                        ContainerClient.list_blobs = lb
                        BlobClient.get_blob_properties = gp
                        exc = None
                        try:
                            await b.delete_folder(key, recursive=rec, missing_ok=mok)
                        except Exception as e:  # noqa: BLE001
                            exc = e
                        finally:
                            ContainerClient.list_blobs = orig_list
                            BlobClient.get_blob_properties = orig_props
                        post = sorted(x.name for x in cc.list_blobs())
                        rows.append(
                            dict(
                                cls="azure-flat",
                                state=state,
                                site=site,
                                fault=status,
                                fired=bool(fired),
                                recursive=rec,
                                missing_ok=mok,
                                answer=answer(exc),
                                post=post,
                            )
                        )
                        await b.aclose()
                        svc.delete_container(cont)

    asyncio.run(go())
    return rows


# ---- race ----


RACE_FILES = ["d/a", "d/e0/b", "d/e1/c"]


def race_writer(root: Path, stop: threading.Event) -> None:
    i = 0
    while not stop.is_set():
        try:
            (root / "d" / "e0").mkdir(parents=True, exist_ok=True)
            (root / "d" / "e0" / f"w{i}").write_bytes(b"x")
        except OSError:
            pass
        i += 1


def race_run(make, root: Path, runs: int) -> collections.Counter:
    """Today's recursive delete under a writer that keeps adding files to d/e0.

    The writer runs for the whole call, so an answer of DirectoryNotEmpty shows a
    write landed mid-walk. There is no deleter race here: an unsynchronised deleter
    removes its files before the walk lists them as often as during it, so its tally
    would not show tolerance mid-walk. The deleter case is the kernel's injected
    `races` cell instead.
    """
    tally: collections.Counter[str] = collections.Counter()
    for _ in range(runs):
        arrange_fs(root, RACE_FILES, [])
        b = make()
        stop = threading.Event()
        t = threading.Thread(target=race_writer, args=(root, stop))
        t.start()
        exc = None
        try:
            b.delete_folder("d", recursive=True)
        except Exception as e:  # noqa: BLE001
            exc = e
        stop.set()
        t.join()
        tally[answer(exc)] += 1
    return tally


# ---- kernel ----


# --- drivers -----------------------------------------------------------------


class Driver:
    parents = "explicit"
    has_delete_tree = False

    def __init__(self) -> None:
        self.calls = 0
        self.hooks: dict[tuple[str, str], object] = {}  # (primitive, key) -> callable(before) once
        self.faults: dict[str, tuple[str, RemoteStoreError]] = {}  # primitive -> (when, exc), once
        self.list_faults: dict[str, RemoteStoreError] = {}  # prefix -> exc raised by its next listing, once

    def wire(self, n: int = 1) -> None:
        self.calls += n

    def _hook(self, prim: str, key: str) -> None:
        h = self.hooks.pop((prim, key), None)
        if h:
            h()

    def _fault(self, prim: str, run):
        f = self.faults.pop(prim, None)
        if f is None:
            return run()
        when, exc = f
        if when == "before":
            self.wire()
            raise exc
        run()
        raise exc


class MemoryDriver(Driver):
    """In-process tree: files and folders as two sets; one lock per primitive (no wire)."""

    has_delete_tree = True

    def __init__(self, files, dirs, delete_tree_mode="D1") -> None:
        super().__init__()
        self.files = set(files)
        self.dirs = {p for f in files for p in _ancestors(f)} | {p for d in dirs for p in _ancestors(d + "/x")}
        self.mode = delete_tree_mode

    def kind(self, key):
        return "file" if key in self.files else "folder" if key in self.dirs else None

    def stat(self, key):
        self.wire(0)
        return self.kind(key)

    def list_page(self, prefix, delimiter="/", limit=None):
        p = prefix + "/"
        if delimiter is None:
            ents = sorted(f for f in self.files if f.startswith(p))
            return ents[:limit] if limit else ents, []
        files = sorted(f for f in self.files if f.startswith(p) and "/" not in f[len(p) :])
        dirs = sorted(d for d in self.dirs if d.startswith(p) and "/" not in d[len(p) :])
        if limit:
            return (files + dirs)[:limit], []
        return files, dirs

    def delete(self, key):
        self._hook("delete", key)
        if key not in self.files:
            raise NotFound(key, path=key)
        self.files.discard(key)

    def remove_folder(self, key):
        self._hook("remove_folder", key)

        def run():
            k = self.kind(key)
            if k is None:
                raise NotFound(key, path=key)
            if k == "file":
                raise InvalidPath(key, path=key)
            if any(x.startswith(key + "/") for x in self.files | self.dirs):
                raise DirectoryNotEmpty(key, path=key)
            self.dirs.discard(key)

        self._fault("remove_folder", run)

    def delete_tree(self, key):
        def run():
            k = self.kind(key)
            if k is None:
                raise NotFound(key, path=key)
            if k == "file":
                if self.mode == "D0":  # a naive detach of whatever node sits at key
                    self.files.discard(key)
                    return
                raise InvalidPath(key, path=key)
            self.files = {f for f in self.files if not f.startswith(key + "/")}
            self.dirs = {d for d in self.dirs if d != key and not d.startswith(key + "/")}

        self._fault("delete_tree", run)

    def post(self):
        return sorted(self.files | {d + "/" for d in self.dirs})


class ImplicitTreeDriver(MemoryDriver):
    """Graph / Azure HNS, modelled. remove_folder is check-then-remove (2 wire calls);
    delete_tree is one DELETE on the item, which removes a file item too (D0), or,
    under the D1 contract, a type check first (2 wire calls)."""

    parents = "implicit"

    def stat(self, key):
        self.wire()
        return self.kind(key)

    def list_page(self, prefix, delimiter="/", limit=None):
        self.wire()
        return super().list_page(prefix, delimiter, limit)

    def remove_folder(self, key):
        self.wire(2)
        super().remove_folder(key)

    def delete_tree(self, key):
        self.wire(1 if self.mode == "D0" else 2)
        super().delete_tree(key)


class LocalDriver(Driver):
    def __init__(self, root: Path, classifier: str) -> None:
        super().__init__()
        self.root = root
        self.cls = classifier

    def p(self, key):
        return str(self.root / key)

    def classify(self, exc: OSError, key: str) -> RemoteStoreError:
        code = exc.errno
        if self.cls == "Lt":
            if code in (errno.ENOTEMPTY, 145):
                return DirectoryNotEmpty(key, path=key)
            return PermissionDenied(key, path=key)
        if code in (errno.ENOENT, errno.ENOTDIR):
            return NotFound(key, path=key)
        if code in (errno.ENOTEMPTY, 145):
            return DirectoryNotEmpty(key, path=key)
        if code in (errno.EACCES, errno.EPERM):
            return PermissionDenied(key, path=key)
        return RemoteStoreError(str(exc), path=key)

    def stat(self, key):
        # Ll: lstat, so a symlink is never a folder (it is an entry delete() unlinks).
        self.wire()
        try:
            st = (os.lstat if self.cls == "Ll" else os.stat)(self.p(key))
        except (FileNotFoundError, NotADirectoryError):
            return None
        return "folder" if stat_mod.S_ISDIR(st.st_mode) else "file"

    def list_page(self, prefix, delimiter="/", limit=None):
        # An absent or non-folder prefix lists empty (BE-014's listing answer); any
        # other refusal is raised, classified, so the walk's listing rule is exercised.
        self._hook("list_page", prefix)
        self.wire()
        follow = self.cls != "Ll"
        try:
            fault = self.list_faults.pop(prefix, None)
            if fault is not None:
                raise fault
            if not follow and os.path.islink(self.p(prefix)):
                return [], []
            ents = list(os.scandir(self.p(prefix)))
        except (FileNotFoundError, NotADirectoryError):
            return [], []
        except OSError as e:
            raise self.classify(e, prefix) from e
        files = sorted(f"{prefix}/{e.name}" for e in ents if not e.is_dir(follow_symlinks=follow))
        dirs = sorted(f"{prefix}/{e.name}" for e in ents if e.is_dir(follow_symlinks=follow))
        if limit:
            return (files + dirs)[:limit], []
        return files, dirs

    def delete(self, key):
        self._hook("delete", key)
        self.wire()
        try:
            os.unlink(self.p(key))
        except OSError as e:
            raise self.classify(e, key) from e

    def remove_folder(self, key):
        self._hook("remove_folder", key)

        def run():
            self.wire()
            try:
                os.rmdir(self.p(key))
            except OSError as e:
                raise self.classify(e, key) from e

        self._fault("remove_folder", run)

    def post(self):
        return fs_state(self.root)


class SFTPDriver(Driver):
    def __init__(self, backend, root: Path) -> None:
        super().__init__()
        self.b = backend
        self.root = root

    def c(self):
        return self.b._sftp

    def sp(self, key):
        return self.b._sftp_path(key)

    def stat(self, key):
        self.wire()
        try:
            a = self.c().stat(self.sp(key))
        except FileNotFoundError:
            return None
        except OSError as e:
            raise self.b._map_exception(e, key) from e
        return "folder" if stat_mod.S_ISDIR(a.st_mode) else "file"

    def list_page(self, prefix, delimiter="/", limit=None):
        # As LocalDriver: an absent prefix lists empty (SFTPBackend.list_files does
        # today); any other refusal is raised through SFTP's classifier.
        self._hook("list_page", prefix)
        self.wire()
        try:
            fault = self.list_faults.pop(prefix, None)
            if fault is not None:
                raise fault
            ents = self.c().listdir_attr(self.sp(prefix))
        except FileNotFoundError:
            return [], []
        except RemoteStoreError:
            raise
        except Exception as e:  # noqa: BLE001
            raise self.b._map_exception(e, prefix) from e
        files = sorted(f"{prefix}/{e.filename}" for e in ents if not stat_mod.S_ISDIR(e.st_mode))
        dirs = sorted(f"{prefix}/{e.filename}" for e in ents if stat_mod.S_ISDIR(e.st_mode))
        if limit:
            return (files + dirs)[:limit], []
        return files, dirs

    def delete(self, key):
        self._hook("delete", key)
        self.wire()
        try:
            self.c().remove(self.sp(key))
        except Exception as e:  # noqa: BLE001
            raise self.b._map_exception(e, key) from e

    def remove_folder(self, key):
        self._hook("remove_folder", key)

        def run():
            self.wire()
            try:
                self.c().rmdir(self.sp(key))
            except Exception as e:  # noqa: BLE001
                raise self.b._map_exception(e, key) from e

        self._fault("remove_folder", run)

    def post(self):
        return fs_state(self.root)


class FlatDriver(Driver):
    parents = "none"

    def __init__(self) -> None:
        super().__init__()
        self.inject: dict[str, RemoteStoreError] = {}  # "list" / "stat" -> exc, once

    def _inj(self, site):
        e = self.inject.pop(site, None)
        if e is not None:
            self.wire()
            raise e


class S3Driver(FlatDriver):
    has_delete_tree = True

    def __init__(self, client, bucket) -> None:
        super().__init__()
        self.cl, self.bucket = client, bucket

    def stat(self, key):
        self._inj("stat")
        self.wire()
        try:
            self.cl.head_object(Bucket=self.bucket, Key=key)
            return "file"
        except self.cl.exceptions.ClientError:
            return None

    def list_page(self, prefix, delimiter="/", limit=None):
        self._inj("list")
        self.wire()
        kw = dict(Bucket=self.bucket, Prefix=prefix + "/")
        if delimiter:
            kw["Delimiter"] = delimiter
        if limit:
            kw["MaxKeys"] = limit
        r = self.cl.list_objects_v2(**kw)
        return [o["Key"] for o in r.get("Contents", [])], [p["Prefix"] for p in r.get("CommonPrefixes", [])]

    def delete_tree(self, key):
        self.wire()
        keys = [o["Key"] for o in self.cl.list_objects_v2(Bucket=self.bucket, Prefix=key + "/").get("Contents", [])]
        if keys:
            self.wire()
            self.cl.delete_objects(Bucket=self.bucket, Delete={"Objects": [{"Key": k} for k in keys]})

    def post(self):
        return sorted(o["Key"] for o in self.cl.list_objects_v2(Bucket=self.bucket).get("Contents", []))


class SQLDriver(FlatDriver):
    has_delete_tree = True

    def __init__(self, backend) -> None:
        super().__init__()
        self.b = backend

    def stat(self, key):
        import sqlalchemy as sa

        self._inj("stat")
        self.wire()
        with self.b._engine.connect() as c:
            t = self.b._table
            return "file" if c.execute(sa.select(sa.literal(1)).where(t.c.key == key)).first() else None

    def list_page(self, prefix, delimiter="/", limit=None):
        import sqlalchemy as sa

        self._inj("list")
        self.wire()
        with self.b._engine.connect() as c:
            q = sa.select(self.b._table.c.key).where(self.b._under(prefix + "/"))
            if limit:
                q = q.limit(limit)
            return [r[0] for r in c.execute(q)], []

    def delete_tree(self, key):
        self.wire()
        with self.b._engine.begin() as c:
            c.execute(self.b._table.delete().where(self.b._under(key + "/")))

    def post(self):
        return sorted(str(fi.path) for fi in self.b.list_files("", recursive=True))


class AzureFlatDriver(FlatDriver):
    def __init__(self, cc) -> None:
        super().__init__()
        self.cc = cc

    def stat(self, key):
        from azure.core.exceptions import ResourceNotFoundError

        self._inj("stat")
        self.wire()
        try:
            self.cc.get_blob_client(key).get_blob_properties()
            return "file"
        except ResourceNotFoundError:
            return None

    page_size = None  # results_per_page for an unlimited listing; set small to force several pages

    def list_page(self, prefix, delimiter="/", limit=None):
        # limit: one bounded request. No limit: every page, one wire call each (the
        # kernel would follow the cursor; collapsing the pages here keeps the model small).
        self._inj("list")
        names = []
        for page in self.cc.list_blobs(
            name_starts_with=prefix + "/", results_per_page=limit or self.page_size
        ).by_page():
            self.wire()
            names += [b.name for b in page]
            if limit:
                break
        return names, []

    def delete(self, key):
        from azure.core.exceptions import ResourceNotFoundError

        self._hook("delete", key)
        self.wire()
        try:
            self.cc.get_blob_client(key).delete_blob()
        except ResourceNotFoundError as e:
            raise NotFound(key, path=key) from e

    def post(self):
        return sorted(b.name for b in self.cc.list_blobs())


def _ancestors(path: str) -> list[str]:
    parts = path.split("/")
    return ["/".join(parts[:i]) for i in range(1, len(parts))]


# --- kernel ------------------------------------------------------------------


class _Counting:
    """Counts driver primitive calls (Memory's lock acquisitions; a wire driver's requests are drv.calls)."""

    def __init__(self, drv) -> None:
        self._drv = drv
        drv.prims = 0

    def __getattr__(self, name):
        attr = getattr(self._drv, name)
        if name in ("stat", "list_page", "delete", "remove_folder", "delete_tree"):

            def f(*a, **k):
                self._drv.prims += 1
                fail = getattr(self._drv, "fail_stat", None)
                if name == "stat" and fail is not None:  # a probe that raises, once
                    self._drv.fail_stat = None
                    raise fail
                return attr(*a, **k)

            return f
        return attr


class Kernel:
    """The kernel's delete_folder sequence, one option switch per BK-396 item.

    P  which refusals are probed:   P0 any but a typed DirectoryNotEmpty (BK-396's candidate)
                                    P1 a typed NotFound or an untyped refusal only (decided)
    D  delete_tree on a non-folder: D0 no contract (the driver does what its wire does)
                                    D1 contract: refuse a file or an absent key, removing nothing (decided)
                                    D2 the kernel stats before delete_tree (fails closed)
    W  walk refusals on the way:    W0 every refusal through the full error-path table (candidate)
                                    W1 NotFound on the way tolerated, other refusals probed (decided)
    R  recursive DirectoryNotEmpty: R1 passes through (decided)
                                    R0 forbidden: re-walk up to 3 passes, then BackendUnavailable
    Local's driver (``LocalDriver.cls``), run under each P and W:
                                    Lt today's delete_folder handler (ENOTEMPTY -> DNE, else
                                       PermissionDenied), stat follows links
                                    Le errno-typed (ENOENT/ENOTDIR -> NotFound, ENOTEMPTY -> DNE,
                                       EACCES/EPERM -> PermissionDenied, else untyped), stat follows links
                                    Ll Le's classifier with stat and list_page as follow_links=False:
                                       the view delete_folder requests, where a link is never a
                                       folder (decided)
    Added after PR #1057's round 1:
    M  a probe that raises:         M0 the refusal is raised, the probe's error chained
                                    M1 as M0, but missing_ok applies to a NotFound refusal (decided)
                                    M2 the probe's error is raised, the refusal chained
    F  parents none, no delete_tree, F0 a NotFound from delete(f) propagates
       recursive:                   F1 tolerated, as on the walk (decided)
    Added after round 2, from `compare enum`, which enumerates the condition both rounds refuted:
    Q  probes that do not replace   Q0 as written after round 1: missing_ok only after a raising stat;
       the refusal (one raised, or     an absent outcome on the walk fails the delete
       a folder they cannot type)   Q1 the refusal stands, missing_ok applying to a NotFound; on the
                                       walk an absent outcome is tolerated, and a delete whose probe
                                       finds a file keeps its own refusal (decided)
                                    Q1 applies only together with P1, M1 and W1: a row for a rejected
                                    P, M or W runs Q0, the semantics it was weighed with.
    Ll models delete_folder's link-aware view only: the decided rule leaves stat and list_page
    following links for every other operation, so no other operation's cells are modelled here.
    """

    def __init__(self, drv: Driver, P="P1", D="D1", W="W1", R="R1", M="M1", F="F1", Q="Q1") -> None:
        self.d, self.P, self.D, self.W, self.R = _Counting(drv), P, D, W, R
        self.M, self.F = M, F
        # Q1 refines the decided P1, M1 and W1; a rejected P, M or W keeps the semantics it was weighed with.
        self.Q = Q if (P == "P1" and M == "M1" and W == "W1") else "Q0"

    def probe_raised(self, e, pe, mok):
        if self.M == "M1" and type(e) is NotFound and mok:
            return
        if self.M == "M2":
            raise pe from e
        raise e from pe

    def probe_wanted(self, e: RemoteStoreError) -> bool:
        if self.P == "P0":
            return not isinstance(e, DirectoryNotEmpty)
        return type(e) is NotFound or type(e) is RemoteStoreError

    def error_path(self, e, key, mok, listing_arm, on_way=False, file_op=False):
        """``on_way``: a delete or remove_folder inside a walk, on an entry under ``key``.

        ``file_op``: the refused call was the walk's ``delete(f)``, for which a file is the right type.
        """
        if not self.probe_wanted(e):
            raise e
        try:
            k = self.d.stat(key)
        except RemoteStoreError as pe:
            return self._stands(e, mok, on_way, pe, listing=False)
        if k is None:
            if mok or (on_way and self.Q == "Q1"):
                return
            raise NotFound(key, path=key) from e
        if k == "file":
            if file_op and self.Q == "Q1":
                return self._stands(e, mok, on_way, None, listing=False)
            raise InvalidPath(key, path=key) from e
        if listing_arm:
            try:
                ents, dirs = self.d.list_page(key, "/", 1)
            except RemoteStoreError as pe:
                return self._stands(e, mok, on_way, pe, listing=True)
            if ents or dirs:
                raise DirectoryNotEmpty(key, path=key) from e
        return self._stands(e, mok, on_way, None, listing=False)

    def _stands(self, e, mok, on_way, pe, listing):
        """The probes did not replace the refusal: it raised, or found a folder they cannot type further."""
        if self.Q == "Q0":  # as first written: missing_ok only after a raising stat
            if pe is None:
                raise e
            return self.probe_raised(e, pe, False if listing else mok)
        if type(e) is NotFound and (mok or on_way):
            return
        if pe is not None and self.M == "M2":
            raise pe from e
        if pe is not None:
            raise e from pe
        raise e

    def delete_folder(self, key, recursive=False, missing_ok=False):
        d = self.d
        if d.parents == "none":
            return self._none(key, recursive, missing_ok)
        if not recursive:
            try:
                d.remove_folder(key)
            except RemoteStoreError as e:
                return self.error_path(e, key, missing_ok, listing_arm=True)
            return
        if d.has_delete_tree:
            if self.D == "D2":
                k = d.stat(key)  # determinant, fails closed
                if k is None:
                    if missing_ok:
                        return
                    raise NotFound(key, path=key)
                if k == "file":
                    raise InvalidPath(key, path=key)
            try:
                d.delete_tree(key)
            except RemoteStoreError as e:
                return self.error_path(e, key, missing_ok, listing_arm=False)
            return
        passes = 3 if self.R == "R0" else 1
        for i in range(passes):
            try:
                return self._walk(key, missing_ok)
            except DirectoryNotEmpty:
                if self.R == "R1":
                    raise
                if i == passes - 1:
                    raise BackendUnavailable(f"tree kept changing: {key}", path=key) from None

    def _walk(self, key, mok):
        d = self.d
        files, folders = [], []
        stack = [key]
        while stack:
            cur = stack.pop()
            try:
                fs, ds = d.list_page(cur, "/")
            except RemoteStoreError as e:
                # The walk's own listing refused: the key's goes through the probe rule
                # with missing_ok; a subfolder's follows the on-the-way rule.
                if cur == key:
                    return self.error_path(e, key, mok, listing_arm=True)
                if self.W == "W1" and type(e) is NotFound:
                    continue
                self.error_path(e, cur, False, listing_arm=True, on_way=True)
                continue
            files += fs
            folders += ds
            stack += ds
        for f in files:
            try:
                d.delete(f)
            except RemoteStoreError as e:
                if self.W == "W1" and type(e) is NotFound:
                    continue
                self.error_path(e, f, False, listing_arm=True, on_way=True, file_op=True)
        for sub in sorted(folders, key=lambda s: -s.count("/")):
            try:
                d.remove_folder(sub)
            except RemoteStoreError as e:
                if self.W == "W1" and type(e) is NotFound:
                    continue
                self.error_path(e, sub, False, listing_arm=True, on_way=True)
        try:
            d.remove_folder(key)
        except RemoteStoreError as e:
            return self.error_path(e, key, mok, listing_arm=True)

    def _none(self, key, recursive, mok):
        d = self.d
        if not recursive:
            ents, dirs = d.list_page(key, "/", 1)  # determinant: a raise propagates
            if ents or dirs:
                raise DirectoryNotEmpty(key, path=key)
            return self._empty(key, mok)
        if d.has_delete_tree:
            ents, _ = d.list_page(key, None, 1)
            if not ents:
                return self._empty(key, mok)
            d.delete_tree(key)
            return
        ents, _ = d.list_page(key, None)
        if not ents:
            return self._empty(key, mok)
        for f in ents:
            try:
                d.delete(f)
            except NotFound:
                if self.F == "F0":
                    raise

    def _empty(self, key, mok):
        try:
            k = self.d.stat(key)  # after an empty listing: fails open
        except RemoteStoreError:
            k = None
        if k == "file":
            raise InvalidPath(key, path=key)
        if mok:
            return
        raise NotFound(key, path=key)


# --- runners -----------------------------------------------------------------

OPTS = dict(
    P=("P0", "P1"),
    D=("D0", "D1", "D2"),
    W=("W0", "W1"),
    R=("R1", "R0"),
    M=("M0", "M1", "M2"),
    F=("F0", "F1"),
    Q=("Q0", "Q1"),
)
DEFAULT = dict(P="P1", D="D1", W="W1", R="R1", M="M1", F="F1", Q="Q1")


def run_cell(drv: Driver, opts, key, rec, mok) -> dict:
    k = Kernel(drv, **opts)
    exc = None
    try:
        k.delete_folder(key, recursive=rec, missing_ok=mok)
    except Exception as e:  # noqa: BLE001
        exc = e
    return dict(answer=answer(exc), post=drv.post(), calls=drv.calls, prims=drv.prims)


def variants(axes):
    keys = list(axes)
    for combo in itertools.product(*(OPTS[a] for a in keys)):
        o = dict(DEFAULT)
        o.update(zip(keys, combo))
        yield o


def memory_rows():
    rows = []
    for opts in variants(["P", "D"]):
        for state, (key, files, dirs) in HIER_STATES.items():
            for rec, mok in CALLS:
                drv = MemoryDriver(files, dirs, opts["D"])
                rows.append(
                    dict(
                        cls="memory",
                        opts=opts,
                        state=state,
                        key=key,
                        recursive=rec,
                        missing_ok=mok,
                        **run_cell(drv, opts, key, rec, mok),
                    )
                )
    return rows


def implicit_rows():
    rows = []
    for name in ("graph", "azure-hns"):
        for opts in variants(["P", "D"]):
            for state, (key, files, dirs) in HIER_STATES.items():
                for rec, mok in CALLS:
                    drv = ImplicitTreeDriver(files, dirs, opts["D"])
                    rows.append(
                        dict(
                            cls=name,
                            modelled=True,
                            opts=opts,
                            state=state,
                            key=key,
                            recursive=rec,
                            missing_ok=mok,
                            **run_cell(drv, opts, key, rec, mok),
                        )
                    )
    return rows


def local_rows(base: Path):
    rows = []
    root = base / "lroot"
    for L in ("Lt", "Le", "Ll"):
        for opts in variants(["P", "W"]):
            for state, (key, files, dirs) in HIER_STATES.items():
                for rec, mok in CALLS:
                    arrange_fs(root, files, dirs)
                    drv = LocalDriver(root, L)
                    rows.append(
                        dict(
                            cls="local",
                            L=L,
                            opts=opts,
                            state=state,
                            key=key,
                            recursive=rec,
                            missing_ok=mok,
                            **run_cell(drv, opts, key, rec, mok),
                        )
                    )
            for state, (key, target) in LOCAL_SYMLINKS.items():
                for rec, mok in CALLS:
                    arrange_links(root, key, target)
                    drv = LocalDriver(root, L)
                    rows.append(
                        dict(
                            cls="local",
                            L=L,
                            opts=opts,
                            state=state,
                            key=key,
                            recursive=rec,
                            missing_ok=mok,
                            **run_cell(drv, opts, key, rec, mok),
                        )
                    )
    return rows


def sftp_session(base: Path):
    from remote_store.backends._sftp import HostKeyPolicy, SFTPBackend
    from tests.backends.sftp._helpers import start_sftp_server

    srv = start_sftp_server(root=str(base), host="127.0.0.1")
    b = SFTPBackend(
        host="127.0.0.1",
        port=srv[1],
        username="testuser",
        password="testpass",
        base_path="/sroot",
        host_key_policy=HostKeyPolicy.AUTO_ADD,
        connect_kwargs={"allow_agent": False, "look_for_keys": False},
    )
    return srv, b


def sftp_rows(b, base: Path):
    rows = []
    root = base / "sroot"
    for opts in variants(["P", "W"]):
        for state, (key, files, dirs) in HIER_STATES.items():
            for rec, mok in CALLS:
                arrange_fs(root, files, dirs)
                b.exists("")
                drv = SFTPDriver(b, root)
                rows.append(
                    dict(
                        cls="sftp",
                        opts=opts,
                        state=state,
                        key=key,
                        recursive=rec,
                        missing_ok=mok,
                        **run_cell(drv, opts, key, rec, mok),
                    )
                )
    return rows


def faults(b, base: Path):
    """Item 1: a refusal that says nothing about the key's state, at the removal call."""
    rows = []
    cases = [
        ("local", "PermissionDenied before", "before", PermissionDenied),
        ("sftp", "BackendUnavailable before (dead channel, nothing removed)", "before", BackendUnavailable),
        ("sftp", "BackendUnavailable after (removed, then the channel died)", "after", BackendUnavailable),
        ("sftp", "PermissionDenied before", "before", PermissionDenied),
    ]
    states = {k: v for k, v in HIER_STATES.items() if k in ("empty folder", "folder holding files")}
    for cls, fault, when, etype in cases:
        for P in ("P0", "P1"):
            for state, (key, files, dirs) in states.items():
                for rec, mok in CALLS:
                    if when == "after" and files and not rec:
                        continue  # rmdir on a non-empty folder refuses for real: the fault cannot fire
                    root = base / ("lroot" if cls == "local" else "sroot")
                    arrange_fs(root, files, dirs)
                    if cls == "local":
                        drv = LocalDriver(root, "Le")
                    else:
                        b.exists("")
                        drv = SFTPDriver(b, root)
                    drv.faults["remove_folder"] = (when, etype("injected", path=key))
                    opts = dict(DEFAULT, P=P)
                    r = run_cell(drv, opts, key, rec, mok)
                    rows.append(
                        dict(
                            cls=cls,
                            fault=fault,
                            today=etype.__name__,
                            opts=opts,
                            state=state,
                            key=key,
                            recursive=rec,
                            missing_ok=mok,
                            **r,
                        )
                    )
    return rows


def races(b, base: Path):
    """Items 3 and 4: one concurrent change injected deterministically at a walk step.

    Tree d/a, d/e0/b, d/e1/c. writer: a file appears in d/e0 just before
    remove_folder(d/e0). deleter: d/a vanishes just before delete(d/a), and d/e1
    just before remove_folder(d/e1).
    """
    rows = []
    files = ["d/a", "d/e0/b", "d/e1/c"]
    for cls in ("local", "sftp"):
        root = base / ("lroot" if cls == "local" else "sroot")
        for kind in ("writer", "writer, persistent", "deleter"):
            for opts in variants(["W", "R"]):
                arrange_fs(root, files, [])
                if cls == "local":
                    drv = LocalDriver(root, "Le")
                else:
                    b.exists("")
                    drv = SFTPDriver(b, root)

                def write(n=[0]):  # noqa: B006
                    n[0] += 1
                    (root / "d" / "e0").mkdir(parents=True, exist_ok=True)
                    (root / "d" / "e0" / f"w{n[0]}").write_bytes(b"x")

                if kind == "writer":
                    drv.hooks[("remove_folder", "d/e0")] = write
                elif kind == "writer, persistent":

                    class Always(dict):
                        def pop(self, k, default=None):
                            return write if k == ("remove_folder", "d/e0") else default

                    drv.hooks = Always()
                else:
                    drv.hooks[("delete", "d/a")] = lambda: (root / "d" / "a").unlink()
                    drv.hooks[("remove_folder", "d/e1")] = lambda: shutil.rmtree(root / "d" / "e1")
                r = run_cell(drv, opts, "d", True, False)
                rows.append(
                    dict(
                        cls=cls,
                        race=kind,
                        opts=opts,
                        state="d/a, d/e0/b, d/e1/c",
                        key="d",
                        recursive=True,
                        missing_ok=False,
                        **r,
                    )
                )
    return rows


def s3_rows():
    import boto3
    from moto.moto_server.threaded_moto_server import ThreadedMotoServer

    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    server = ThreadedMotoServer(port=port, verbose=False)
    server.start()
    url = f"http://127.0.0.1:{port}"
    cl = boto3.client("s3", endpoint_url=url, aws_access_key_id="t", aws_secret_access_key="t", region_name="us-east-1")
    rows = []

    def fresh(files):
        bucket = f"k-{uuid.uuid4().hex[:8]}"
        cl.create_bucket(Bucket=bucket)
        for f in files:
            cl.put_object(Bucket=bucket, Key=f, Body=b"x")
        return S3Driver(cl, bucket)

    try:
        rows += flat_cells("s3boto3", fresh)
    finally:
        server.stop()
    return rows


def sql_rows(base: Path):
    from remote_store.backends._sqlalchemy import SQLBlobBackend

    def fresh(files):
        b = SQLBlobBackend(url=f"sqlite:///{base}/{uuid.uuid4().hex}.db")
        for f in files:
            b.write(f, b"x")
        return SQLDriver(b)

    return flat_cells("sqlblob", fresh)


def azure_rows():
    from azure.storage.blob import BlobServiceClient

    svc = BlobServiceClient.from_connection_string(CONN)

    def fresh(files):
        cc = svc.create_container(f"k-{uuid.uuid4().hex[:8]}")
        for f in files:
            cc.upload_blob(f, b"x")
        return AzureFlatDriver(cc)

    return flat_cells("azure-flat", fresh)


def flat_cells(cls, fresh):
    rows = []
    for state, (key, files) in FLAT_STATES.items():
        for rec, mok in CALLS:
            drv = fresh(files)
            rows.append(
                dict(
                    cls=cls,
                    opts=DEFAULT,
                    state=state,
                    key=key,
                    recursive=rec,
                    missing_ok=mok,
                    **run_cell(drv, DEFAULT, key, rec, mok),
                )
            )
    inj_states = INJ_STATES

    faults_ = (
        [(403, PermissionDenied), (503, BackendUnavailable)]
        if cls != "sqlblob"
        else [("OperationalError", BackendUnavailable)]
    )
    for state, (key, files) in inj_states.items():
        for site in ("list", "stat"):
            for fault, etype in faults_:
                for rec, mok in CALLS:
                    drv = fresh(files)
                    drv.inject[site] = etype("injected", path=key)
                    r = run_cell(drv, DEFAULT, key, rec, mok)
                    fired = site not in drv.inject
                    rows.append(
                        dict(
                            cls=cls,
                            opts=DEFAULT,
                            state=state,
                            site=site,
                            fault=fault,
                            fired=fired,
                            key=key,
                            recursive=rec,
                            missing_ok=mok,
                            **r,
                        )
                    )
    return rows


# ---- compare ----


def o(opts, keys):
    return " ".join(opts[k] for k in keys)


def cellname(r):
    return f"{r['state']} rec={int(r['recursive'])} mok={int(r['missing_ok'])}"


def diff_section(rows, keys, extra=""):
    groups = defaultdict(list)
    for r in rows:
        groups[(r["cls"], r.get("L", ""), o(r["opts"], keys))].append(r)
    for (cls, L, opt), rs in sorted(groups.items()):
        changed = []
        for r in rs:
            t = TODAY.get((r["cls"], r["state"], r["recursive"], r["missing_ok"]))
            if t is None:
                changed.append((r, None))
                continue
            if t["answer"] != r["answer"] or t["post"] != r["post"]:
                changed.append((r, t))
        tag = " (modelled; today read)" if rs[0].get("modelled") else ""
        print(f"\n## {cls}{tag} {L} {opt}: {len(rs)} cells, {len(changed)} changed")
        for r, t in changed:
            if t is None:
                print(f"   {cellname(r)}: kernel {r['answer']} post={r['post']} (no measured today)")
            else:
                ta = t["answer"] + ("" if t["post"] == r["post"] else f" post={t['post']}")
                ka = r["answer"] + ("" if t["post"] == r["post"] else f" post={r['post']}")
                print(f"   {cellname(r)}: today {ta} -> kernel {ka}")


def main() -> None:
    sect = sys.argv[1:] or ["memory", "implicit", "local", "sftp", "flat", "faults", "races", "trips", "summary"]
    if "summary" in sect:
        summary()
    if "extra" in sect:
        extra()
    if "enum" in sect:
        enum()
    if "memory" in sect:
        diff_section(K["memory"], ["P", "D"])
    if "implicit" in sect:
        print("\n# Graph / HNS: modelled driver; today's answers are read from the code, not run")
        for r in K["implicit"]:
            if r["recursive"] and r["state"] in ("file f",):
                print(
                    f"   {r['cls']} {o(r['opts'], ['P', 'D'])} {cellname(r)}: kernel {r['answer']} post={r['post']} calls={r['calls']}"
                )
    if "local" in sect:
        diff_section(K["local"], ["P", "W"])
    if "sftp" in sect:
        diff_section(K["sftp"], ["P", "W"])
    if "flat" in sect:
        for name in ("s3", "sql", "azure"):
            base = [r for r in K[name] if "site" not in r]
            diff_section(base, ["P"])
            inj = [r for r in K[name] if "site" in r and r["fired"]]
            ch = []
            for r in inj:
                t = INJ[(r["cls"], r["state"], r["site"], str(r["fault"]), r["recursive"], r["missing_ok"])]
                if t["answer"] != r["answer"] or t["post"] != r["post"]:
                    ch.append((r, t))
            print(f"## {name} injected: {len(inj)} fired cells, {len(ch)} changed")
            for r, t in ch:
                print(
                    f"   {r['state']} {r['site']} {r['fault']} rec={int(r['recursive'])} mok={int(r['missing_ok'])}: "
                    f"today {t['answer']} -> kernel {r['answer']}"
                )
    if "faults" in sect:
        print("\n# Item 1: a non-state refusal injected at remove_folder")
        for r in K["faults"]:
            mark = "" if r["answer"] == r["today"] else "  <- changed"
            print(
                f"   {r['cls']:5} {r['opts']['P']} {r['fault']:58} {cellname(r):38} today {r['today']:18} kernel "
                f"{r['answer']:18} calls={r['calls']}{mark}"
            )
    if "races" in sect:
        print("\n# Items 3, 4: one concurrent change injected in the walk (today: the `race` tallies)")
        print("   today:", json.loads((OUT / "race.json").read_text()))
        for r in K["races"]:
            print(f"   {r['cls']:5} {r['race']:20} {o(r['opts'], ['W', 'R'])}: {r['answer']:22} post={r['post']}")
    if "trips" in sect:
        trips()


def trips() -> None:
    print("\n# Round trips: today's wire calls vs the kernel's (P1 D1 W1 R1), per class and cell")
    keyset = {"P": "P1", "D": "D1", "W": "W1", "R": "R1"}
    for name in ("memory", "local", "sftp", "s3", "sql", "azure"):
        for r in K[name]:
            if "site" in r or r.get("L", "Ll") != "Ll" or any(r["opts"][k] != v for k, v in keyset.items()):
                continue
            t = TODAY.get((r["cls"], r["state"], r["recursive"], r["missing_ok"]))
            if t is None or r["missing_ok"]:
                continue
            tc = t["calls"]
            kc = r["prims"] if name in ("memory", "local") else r["calls"]
            unit = "primitives" if name in ("memory", "local") else "wire"
            print(f"   {r['cls']:10} {r['state']:38} rec={int(r['recursive'])}: today {tc:>3} kernel {kc:>3} ({unit})")
    print("   Local's 'today' is os-level calls through pathlib, not comparable to its primitives; Graph and HNS: read")


class ScriptedDriver(Driver):
    """Every outcome set per cell: the refusal, what the stat probe answers, what the listing probe answers.

    Contexts: "remove_folder" (recursive=False, both probes), "delete_tree"
    (recursive, stat only), "walk delete" (a file on the way under d) and
    "walk rmdir" (a subfolder d/s on the way); in both walk contexts the
    final remove_folder(d) succeeds.
    """

    WALK = {"walk delete": (["d/a"], []), "walk rmdir": ([], ["d/s"])}

    parents = "explicit"

    def __init__(self, context, refusal, stat_out, list_out) -> None:
        super().__init__()
        self.ctx, self.refusal, self.stat_out, self.list_out = context, refusal, stat_out, list_out
        self.has_delete_tree = context == "delete_tree"

    def _out(self, v, key):
        if v == "raises":
            raise BackendUnavailable("injected: probe failed", path=key)
        return v

    def stat(self, key):
        return self._out(self.stat_out, key)

    def list_page(self, prefix, delimiter="/", limit=None):
        if self.ctx in self.WALK and limit is None:
            return self.WALK[self.ctx] if prefix == "d" else ([], [])  # the walk's own listings
        v = self._out(self.list_out, prefix)
        return (["x"], []) if v == "non-empty" else ([], [])

    def _refuse(self, key):
        raise self.refusal(f"refused: {key}", path=key)

    def remove_folder(self, key):
        if self.ctx in self.WALK and key == "d":
            return
        self._refuse(key)

    def delete_tree(self, key):
        self._refuse(key)

    def delete(self, key):
        self._refuse(key)

    def post(self):
        return []


def enum_rows(Q):
    """Every combination of refusal x stat x listing x missing_ok, per context, under the decided options and Q."""
    rows = []
    for ctx in ("remove_folder", "delete_tree", "walk delete", "walk rmdir"):
        for refusal in (NotFound, RemoteStoreError):
            for stat_out in ("raises", None, "file", "folder"):
                lists = ("raises", "empty", "non-empty") if stat_out == "folder" and ctx != "delete_tree" else ("-",)
                for list_out in lists:
                    for mok in (False, True):
                        drv = ScriptedDriver(ctx, refusal, stat_out, list_out)
                        r = run_cell(drv, dict(DEFAULT, Q=Q), "d", ctx != "remove_folder", mok)
                        rows.append(
                            dict(
                                ctx=ctx,
                                refusal=refusal.__name__ if refusal is NotFound else "untyped",
                                stat=stat_out or "absent",
                                listing=list_out,
                                mok=mok,
                                answer=r["answer"],
                            )
                        )
    return rows


def enum() -> None:
    """The condition rounds 1 and 2 of PR #1057 each refuted, enumerated: what a refusal the probes did not replace answers."""
    a, b = enum_rows("Q0"), enum_rows("Q1")
    print(f"\n# Probe outcomes, enumerated: {len(a)} cells per rule; Q0 = as written after round 1, Q1 = uniform")
    for x, y in zip(a, b):
        mark = "" if x["answer"] == y["answer"] else "   <- differs"
        print(
            f"   {x['ctx']:13} {x['refusal']:8} stat={x['stat']:6} list={x['listing']:9} mok={int(x['mok'])}: "
            f"Q0 {x['answer']:18} Q1 {y['answer']:18}{mark}"
        )
    print(f"   cells that differ: {sum(x['answer'] != y['answer'] for x, y in zip(a, b))}")


def extra() -> None:
    """PR #1057 round 1's cells: a probe that raises, the walk's delete refusal, flat Azure's deleter and paging."""
    print("\n# Round-1 cells (today where a wire exists; '-' where none)")
    for r in K["extra"]:
        t = TODAY.get((r["cls"], r["state"], r["recursive"], r["missing_ok"]))
        today = "-" if t is None else f"{t['answer']} post={t['post']}"
        o_ = " ".join(f"{k}={v}" for k, v in r["opts"].items() if v != DEFAULT[k]) or "default"
        print(
            f"   {r['cls']:10} {o_:6} {cellname(r):52} today {today:40} kernel {r['answer']} post={r['post']}"
            f" calls={r['calls']}"
        )


DECIDED = {"P": "P1", "D": "D1", "W": "W1", "R": "R1", "M": "M1", "F": "F1", "Q": "Q1"}


def summary() -> None:
    """Changed-cell counts under the decided options (BK-396): P1 D1 W1 R1 M1 F1 Q1, Local's lstat driver (Ll)."""
    print("\n# Decided options P1 D1 W1 R1 M1 F1 Q1, Local driver Ll: changed cells against today")

    def decided(r):
        return all(r["opts"][k] == v for k, v in DECIDED.items()) and r.get("L", "Ll") == "Ll"

    for name in ("memory", "local", "sftp", "s3", "sql", "azure"):
        base = [r for r in K[name] if "site" not in r and decided(r)]
        ch = [
            r
            for r in base
            if (t := TODAY[(r["cls"], r["state"], r["recursive"], r["missing_ok"])])["answer"] != r["answer"]
            or t["post"] != r["post"]
        ]
        print(f"   {name:7} base: {len(base)} cells, {len(ch)} changed")
        for r in ch:
            t = TODAY[(r["cls"], r["state"], r["recursive"], r["missing_ok"])]
            print(f"      {cellname(r)}: today {t['answer']} -> kernel {r['answer']}")
        inj = [r for r in K[name] if "site" in r and r["fired"]]
        if inj:
            ch = [
                r
                for r in inj
                if (t := INJ[(r["cls"], r["state"], r["site"], str(r["fault"]), r["recursive"], r["missing_ok"])])[
                    "answer"
                ]
                != r["answer"]
                or t["post"] != r["post"]
            ]
            print(f"   {name:7} injected: {len(inj)} fired cells, {len(ch)} changed")
    f = [r for r in K["faults"] if r["opts"]["P"] == "P1"]
    print(f"   faults (P1): {len(f)} cells, {sum(r['answer'] != r['today'] for r in f)} differ from the injected type")
    for r in f:
        if r["answer"] != r["today"]:
            print(f"      {r['cls']} {r['fault']} {cellname(r)}: {r['answer']}")
    for r in K["races"]:
        if r["opts"]["W"] == "W1" and r["opts"]["R"] == "R1":
            print(f"   race {r['cls']:5} {r['race']:20}: {r['answer']:18} post={r['post']}")
    ex = [r for r in K["extra"] if decided(r)]
    measured = [r for r in ex if (r["cls"], r["state"], r["recursive"], r["missing_ok"]) in TODAY]
    ch = [
        r
        for r in measured
        if (t := TODAY[(r["cls"], r["state"], r["recursive"], r["missing_ok"])])["answer"] != r["answer"]
        or t["post"] != r["post"]
    ]
    print(f"   round-1 cells: {len(ex)} decided, {len(measured)} with a today, {len(ch)} changed")
    for r in ch:
        t = TODAY[(r["cls"], r["state"], r["recursive"], r["missing_ok"])]
        print(
            f"      {r['cls']} {cellname(r)}: today {t['answer']} post={t['post']} -> kernel {r['answer']} post={r['post']}"
        )
    for r in ex:
        if (r["cls"], r["state"], r["recursive"], r["missing_ok"]) not in TODAY:
            print(f"      no today: {r['cls']} {cellname(r)}: kernel {r['answer']} post={r['post']}")
    for r in K["implicit"]:
        if decided(r) and r["recursive"] and r["state"] == "file f" and not r["missing_ok"]:
            print(f"   {r['cls']} (modelled) delete_folder('f', recursive=True): {r['answer']} post={r['post']}")


def _load_compare_inputs() -> None:
    global K, TODAY, INJ
    K = json.loads((OUT / "kernel.json").read_text())
    TODAY = {}
    for f in OUT.glob("today-*.json"):
        for r in json.loads(f.read_text()):
            TODAY[(r["cls"], r["state"], r["recursive"], r["missing_ok"])] = r
    INJ = {
        (r["cls"], r["state"], r["site"], str(r["fault"]), r["recursive"], r["missing_ok"]): r
        for r in json.loads((OUT / "inject-flat.json").read_text())
    }


def cmd_today(args) -> None:
    for name in args.rest or list(RUNNERS):
        rows = RUNNERS[name]()
        (OUT / f"today-{name}.json").write_text(json.dumps(rows, indent=1))
        for r in rows:
            print(
                f"{r['cls']:10} {r['state']:38} rec={int(r['recursive'])} mok={int(r['missing_ok'])} "
                f"{r['answer']:26} calls={r['calls']:<3} post={r['post']}"
            )
        print(f"{name}: {len(rows)} cells")


def cmd_inject(args) -> None:
    rows = inject_s3() + inject_sql() + inject_azure()
    (OUT / "inject-flat.json").write_text(json.dumps(rows, indent=1))
    for r in rows:
        if r["fired"]:
            print(
                f"{r['cls']:10} {r['state']:26} {r['site']:4} {r['fault']!s:16} rec={int(r['recursive'])} "
                f"mok={int(r['missing_ok'])} {r['answer']:18} post={r['post']}"
            )
    print(f"{len(rows)} cells, {sum(r['fired'] for r in rows)} with the fault fired")


def cmd_race(args) -> None:
    from remote_store.backends._local import LocalBackend
    from remote_store.backends._sftp import HostKeyPolicy, SFTPBackend
    from tests.backends.sftp._helpers import start_sftp_server, stop_sftp_server

    runs = int(args.rest[0]) if args.rest else 200
    out = {}
    base = Path(tempfile.mkdtemp(dir=OUT))
    root = base / "root"
    out["local/writer"] = race_run(lambda: LocalBackend(root=str(root)), root, runs)
    thread, port, _hk, stop, sock = start_sftp_server(root=str(base), host="127.0.0.1")
    sb = SFTPBackend(
        host="127.0.0.1",
        port=port,
        username="testuser",
        password="testpass",
        base_path="/root",
        host_key_policy=HostKeyPolicy.AUTO_ADD,
        connect_kwargs={"allow_agent": False, "look_for_keys": False},
    )
    try:
        out["sftp/writer"] = race_run(lambda: sb, root, runs)
    finally:
        sb.close()
        stop_sftp_server(thread, stop, sock)
        shutil.rmtree(base)
    (OUT / "race.json").write_text(json.dumps({k: dict(v) for k, v in out.items()}, indent=1))
    for k, v in out.items():
        print(f"{k:14} runs={runs} {dict(v)}")


def extra_rows(b, base: Path) -> list[dict]:
    """PR #1057 round 1: the cells run_extra measures today, plus two with no today.

    - probe raises: the refusal is NotFound (absent key; on SFTP and Local also a
      file, which their rmdir types NotFound) and the stat probe raises
      BackendUnavailable, under M0/M1/M2. Memory and Local have no wire to drop,
      so they have no today; SFTP's today is run_extra's.
    - walk delete refusal (Local, no today): d/a becomes a non-empty directory
      just before delete(d/a), so unlink answers EISDIR (untyped).
    - flat Azure: d/a deleted just before delete(d/a), under F0/F1; and a
      three-file tree listed one blob per page, to check the paging.
    """
    from azure.storage.blob import BlobServiceClient

    rows = []
    states = {"absent, probe raises": ("z", []), "file f, probe raises": ("f", ["f"])}
    for M in OPTS["M"]:
        opts = dict(DEFAULT, M=M)
        for state, (key, files) in states.items():
            for rec, mok in CALLS:
                for cls in ("memory", "local", "sftp"):
                    if cls == "memory":
                        drv = MemoryDriver(files, [], "D1")
                    elif cls == "local":
                        root = base / "lroot"
                        arrange_fs(root, files, [])
                        drv = LocalDriver(root, "Ll")
                    else:
                        root = base / "sroot"
                        arrange_fs(root, files, [])
                        b.exists("")
                        drv = SFTPDriver(b, root)
                    drv.fail_stat = BackendUnavailable("injected: probe failed", path=key)
                    rows.append(
                        dict(
                            cls=cls,
                            opts=opts,
                            state=state,
                            key=key,
                            recursive=rec,
                            missing_ok=mok,
                            **run_cell(drv, opts, key, rec, mok),
                        )
                    )
    root = base / "lroot"
    for W in OPTS["W"]:
        opts = dict(DEFAULT, W=W)
        arrange_fs(root, ["d/a", "d/e/b"], [])

        def swap():
            (root / "d" / "a").unlink()
            (root / "d" / "a").mkdir()
            (root / "d" / "a" / "z").write_bytes(b"x")

        drv = LocalDriver(root, "Ll")
        drv.hooks[("delete", "d/a")] = swap
        rows.append(
            dict(
                cls="local",
                opts=opts,
                state="d/a becomes a non-empty directory mid-walk",
                key="d",
                recursive=True,
                missing_ok=False,
                **run_cell(drv, opts, "d", True, False),
            )
        )

    # The walk's own listing refusing on a subfolder (no today: no hook reaches today's
    # classes between listings). Tree d/a, d/e0/b, d/e1/c; the subfolder is d/e0.
    def gone():  # a concurrent deleter removes d/e0 between its parent's listing and its own
        shutil.rmtree(root / "d" / "e0")

    listing_cases = [
        ("d/e0 deleted before its listing", lambda drv: drv.hooks.__setitem__(("list_page", "d/e0"), gone)),
        (
            "d/e0 listing answers NotFound",
            lambda drv: (
                drv.hooks.__setitem__(("list_page", "d/e0"), gone),
                drv.list_faults.__setitem__("d/e0", NotFound("injected", path="d/e0")),
            ),
        ),
        (
            "d/e0 listing PermissionDenied",
            lambda drv: drv.list_faults.__setitem__("d/e0", PermissionDenied("injected", path="d/e0")),
        ),
        (
            "d/e0 listing untyped",
            lambda drv: drv.list_faults.__setitem__("d/e0", RemoteStoreError("injected", path="d/e0")),
        ),
    ]
    for cls in ("local", "sftp"):
        for state, arm in listing_cases:
            root = base / ("lroot" if cls == "local" else "sroot")
            arrange_fs(root, ["d/a", "d/e0/b", "d/e1/c"], [])
            if cls == "local":
                drv = LocalDriver(root, "Ll")
            else:
                b.exists("")
                drv = SFTPDriver(b, root)
            arm(drv)
            rows.append(
                dict(
                    cls=cls,
                    opts=DEFAULT,
                    state=state,
                    key="d",
                    recursive=True,
                    missing_ok=False,
                    **run_cell(drv, DEFAULT, "d", True, False),
                )
            )

    svc = BlobServiceClient.from_connection_string(CONN)
    for F in OPTS["F"]:
        opts = dict(DEFAULT, F=F)
        for mok in (False, True):
            cc = svc.create_container(f"k-{uuid.uuid4().hex[:8]}")
            for f in ("d/a", "d/b"):
                cc.upload_blob(f, b"x")
            drv = AzureFlatDriver(cc)
            drv.hooks[("delete", "d/a")] = lambda cc=cc: cc.get_blob_client("d/a").delete_blob()
            rows.append(
                dict(
                    cls="azure-flat",
                    opts=opts,
                    state="d/a, d/b; d/a deleted concurrently",
                    key="d",
                    recursive=True,
                    missing_ok=mok,
                    **run_cell(drv, opts, "d", True, mok),
                )
            )
    cc = svc.create_container(f"k-{uuid.uuid4().hex[:8]}")
    for f in ("d/a", "d/b", "d/c"):
        cc.upload_blob(f, b"x")
    drv = AzureFlatDriver(cc)
    drv.page_size = 1
    rows.append(
        dict(
            cls="azure-flat",
            opts=DEFAULT,
            state="d/a, d/b, d/c, one blob per page",
            key="d",
            recursive=True,
            missing_ok=False,
            **run_cell(drv, DEFAULT, "d", True, False),
        )
    )
    return rows


def cmd_kernel(args) -> None:
    from tests.backends.sftp._helpers import stop_sftp_server

    base = Path(tempfile.mkdtemp(dir=OUT))
    out = dict(memory=memory_rows(), implicit=implicit_rows(), local=local_rows(base))
    srv, b = sftp_session(base)
    try:
        out["sftp"] = sftp_rows(b, base)
        out["faults"] = faults(b, base)
        out["races"] = races(b, base)
        out["extra"] = extra_rows(b, base)
    finally:
        b.close()
        stop_sftp_server(srv[0], srv[3], srv[4])
    out["s3"] = s3_rows()
    out["sql"] = sql_rows(base)
    out["azure"] = azure_rows()
    shutil.rmtree(base)
    (OUT / "kernel.json").write_text(json.dumps(out, indent=1, default=str))
    print({k: len(v) for k, v in out.items()})


def cmd_compare(args) -> None:
    _load_compare_inputs()
    sys.argv = [sys.argv[0], *args.rest]
    main()


if __name__ == "__main__":
    logging.disable(logging.CRITICAL)
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("cmd", choices=["today", "inject", "race", "kernel", "compare"])
    p.add_argument("rest", nargs="*")
    a = p.parse_args()
    globals()[f"cmd_{a.cmd}"](a)
