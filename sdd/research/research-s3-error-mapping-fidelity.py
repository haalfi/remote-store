"""ID-200 audit driver: s3fs -> _S3Base error-mapping fidelity against moto.

Re-runnable evidence for research-s3-error-mapping-fidelity.md. Drives the
five ID-200 scenarios against a fresh in-process moto-backed S3Backend and
prints, per scenario: the target typed error, the observed typed error (or
outcome), and the underlying s3fs/botocore exception.

This is a throwaway audit driver, not a test (ID-200 adds no tests; the
failing test for the divergence it found lives with BUG-214). It is committed
alongside the note so the findings can be reproduced.

    hatch run python sdd/research/research-s3-error-mapping-fidelity.py
"""

from __future__ import annotations

import io
import socket
from typing import Any

import boto3
from botocore.exceptions import ClientError
from moto.moto_server.threaded_moto_server import ThreadedMotoServer

from remote_store._errors import RemoteStoreError
from remote_store.backends._s3 import S3Backend

MB = 1024 * 1024


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = int(s.getsockname()[1])
    s.close()
    return port


def _line(label: str, value: Any) -> None:
    print(f"    {label:<30}: {value}")


def _observe(fn: Any) -> str:
    """Run fn(); summarise as 'TypedError: msg', 'LEAK:...', or 'NO-RAISE ...'."""
    try:
        result = fn()
    except RemoteStoreError as exc:
        return f"{type(exc).__name__}: {exc.args[0] if exc.args else exc}"
    except Exception as exc:  # noqa: BLE001
        return f"LEAK {type(exc).__name__}: {exc}"
    return f"NO-RAISE (returned {result!r})"


def _translate(err: ClientError) -> str:
    from s3fs.errors import translate_boto_error

    translated = translate_boto_error(err)
    return f"{type(translated).__name__}: {translated}"


class _Boom(io.RawIOBase):
    """Deliver `fail_after` bytes, then raise a connection reset."""

    def __init__(self, fail_after: int) -> None:
        self.remaining = fail_after

    def readable(self) -> bool:
        return True

    def read(self, size: int = -1) -> bytes:
        if self.remaining <= 0:
            raise ConnectionResetError("Connection reset by peer")
        n = size if size and size > 0 else 65536
        chunk = b"x" * min(n, self.remaining)
        self.remaining -= len(chunk)
        return chunk


def main() -> None:
    port = _free_port()
    server = ThreadedMotoServer(port=port, verbose=False)
    server.start()
    endpoint = f"http://127.0.0.1:{port}"
    bucket = "id200"
    client = boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id="testing",
        aws_secret_access_key="testing",
        region_name="us-east-1",
    )
    client.create_bucket(Bucket=bucket)

    def backend() -> S3Backend:
        return S3Backend(
            bucket=bucket,
            endpoint_url=endpoint,
            key="testing",
            secret="testing",
            region_name="us-east-1",
        )

    def left_behind(key: str) -> str:
        objs = client.list_objects_v2(Bucket=bucket, Prefix=key).get("Contents", [])
        present = [(o["Key"], o["Size"]) for o in objs if o["Key"] == key]
        mpu = client.list_multipart_uploads(Bucket=bucket).get("Uploads", [])
        return f"object={present or 'ABSENT'}  orphan_mpu={len(mpu)}"

    print("=" * 72)
    print("ID-200 s3fs error-mapping fidelity (moto)")
    print("=" * 72)

    # (a) GetObject missing key -> NotFound
    print("\n(a) GetObject missing key  [target: NotFound]")
    b = backend()
    _line("observed", _observe(lambda: b.read_bytes("never/written.txt")))
    b.close()

    # (b) GetObject forbidden 403 -> PermissionDenied
    print("\n(b) GetObject forbidden 403  [target: PermissionDenied]")
    print("    moto does not enforce ACL/IAM -> mapping verified via real translator")
    err403 = ClientError(
        {"Error": {"Code": "AccessDenied", "Message": "Access Denied"}, "ResponseMetadata": {"HTTPStatusCode": 403}},
        "GetObject",
    )
    _line("s3fs translate(403)", _translate(err403))
    b = backend()

    def _b() -> Any:
        from s3fs.errors import translate_boto_error

        with b._s3fs_errors("forbidden.txt"):
            raise translate_boto_error(err403)

    _line("mapped via _s3fs_errors", _observe(_b))
    b.close()

    # (c) PutObject expired/invalid token -> BackendUnavailable | PermissionDenied
    print("\n(c) PutObject expired/invalid token  [target: BackendUnavailable | PermissionDenied]")
    print("    moto accepts any credentials -> mapping verified via real translator")
    cred_cases = {
        "ExpiredToken (400)": ("ExpiredToken", 400, "The provided token has expired."),
        "InvalidAccessKeyId (403)": ("InvalidAccessKeyId", 403, "The AWS Access Key Id does not exist."),
        "SignatureDoesNotMatch (403)": ("SignatureDoesNotMatch", 403, "The request signature does not match."),
    }
    b = backend()
    for label, (code, http, msg) in cred_cases.items():
        err = ClientError(
            {"Error": {"Code": code, "Message": msg}, "ResponseMetadata": {"HTTPStatusCode": http}},
            "PutObject",
        )
        _line(f"translate {label}", _translate(err))

        def _c(err: ClientError = err) -> Any:
            from s3fs.errors import translate_boto_error

            with b._s3fs_errors("upload.txt"):
                raise translate_boto_error(err)

        _line(f"  -> mapped {label}", _observe(_c))
    b.close()

    # (d) Mid-stream failure -> typed error AND no partial object
    print("\n(d) Mid-stream failure during write  [target: typed error, no partial object]")
    print("    s3fs write block size = 50 MB (multipart only above it)")
    for label, deliver, key, op in [
        ("write() 6 MB (single PUT)", 6 * MB, "d/write_6mb.bin", "write"),
        ("write() 55 MB (multipart)", 55 * MB, "d/write_55mb.bin", "write"),
        ("write_atomic() 6 MB", 6 * MB, "d/atomic_6mb.bin", "write_atomic"),
        ("write_atomic() 55 MB", 55 * MB, "d/atomic_55mb.bin", "write_atomic"),
    ]:
        b = backend()
        observed = _observe(
            lambda b=b, op=op, key=key, deliver=deliver: getattr(b, op)(key, _Boom(deliver), overwrite=True)
        )
        print(f"    {label}")
        _line("  raised", observed)
        _line("  left", left_behind(key))
        b.close()

    # open_atomic: caller raises inside the with-block (distinct, safe path)
    b = backend()
    key = "d/open_atomic_caller_raises.bin"

    def _oa() -> Any:
        with b.open_atomic(key, overwrite=True) as buf:
            buf.write(b"x" * (6 * MB))
            raise ConnectionResetError("Connection reset by peer")

    # The caller's own exception propagates unmapped here (correct -- it is not
    # a backend error); the safety signal is object=ABSENT below.
    print("    open_atomic() caller raises inside the with-block (caller exc propagates)")
    try:
        _oa()
        raised = "NO-RAISE"
    except ConnectionResetError as exc:
        raised = f"propagated {type(exc).__name__}: {exc}"
    _line("  raised", raised)
    _line("  left", left_behind(key))
    b.close()

    # (e) Directory-marker ambiguity
    print("\n(e) Directory-marker ambiguity  [target: InvalidPath | NotFound, not confused]")
    b = backend()
    b.write("conf", b"i am a file", overwrite=True)
    b.write("conf/app.txt", b"under the prefix", overwrite=True)
    _line("is_file('conf')", _observe(lambda: b.is_file("conf")))
    _line("is_folder('conf')", _observe(lambda: b.is_folder("conf")))
    _line("get_file_info('conf')", _observe(lambda: b.get_file_info("conf").name))
    _line("read('conf')", _observe(lambda: b.read_bytes("conf")))
    b.close()

    server.stop()
    print("\n" + "=" * 72)
    print("done")


if __name__ == "__main__":
    main()
