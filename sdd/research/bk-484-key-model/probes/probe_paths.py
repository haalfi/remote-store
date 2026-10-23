"""Live probe: what a storage service does with a raw path or key.

Settles the open points of ``research-backend-path-authorities.md`` § 4 by
measurement. Each probe key is sent as a raw request: the path goes on the
wire byte for byte through ``http.client``, so no SDK or urllib3 step removes
dot segments or collapses slashes first (§ 3.7 of that document records that
urllib3 does). Per key the probe records the PUT status, the names a listing
shows afterwards, and the status of a GET on the same raw path.

Targets, chosen with ``--target`` (comma-separated):

- ``s3``: a temporary ``rs-conformance-<hex>`` general-purpose bucket on the
  AWS account in ``.env``, deleted at the end.
- ``s3express``: a temporary directory bucket in the same region, deleted at
  the end.
- ``azure``: a temporary container on the account in
  ``AZURE_STORAGE_CONNECTION_STRING``, deleted at the end.
- ``minio``, ``azurite``, ``sftp``: the local Docker stack
  (``infra/docker-compose.yml``). These are implementations, not authorities.

Run from the repo root, for example::

    hatch run python sdd/research/bk-484-key-model/probes/probe_paths.py --target minio,azurite,sftp

Credentials load inside the process (``.env`` for the cloud, ``infra/.env``
through ``infra._settings`` for the local stack) and are never printed.
Results are written as JSON to ``--out``: exceptions are recorded through
``describe`` (class and error code, no message text), and the whole result
passes through ``redact`` (no account, bucket, container, region or zone name).
"""

from __future__ import annotations

import argparse
import datetime as dt
import errno
import http.client
import json
import os
import re
import sys
import urllib.parse
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

BODY = b"probe"
# Prefix of every container and SFTP folder a run creates; `redact` replaces it.
PROBE_PREFIX = "bk484-probe"

# Probe keys relative to the run's base prefix B. "{B}" is replaced per run.
KEYS: list[tuple[str, str]] = [
    ("control", "{B}/plain"),
    ("name with dots", "{B}/..."),
    ("empty segment", "{B}/a//b"),
    ("empty segment after base", "{B}//c"),
    ("dot segment", "{B}/./d"),
    ("dot-dot inside", "{B}/e/../f"),
    ("trailing slash", "{B}/g/"),
    ("leading slash", "/{B}/h"),
    ("backslash", "{B}/i\\j"),
    ("trailing dot", "{B}/k."),
    ("dot-dot above root", "{B}/{UP}/x"),
]


def above_root(base: str) -> str:
    """The `..` run that climbs one level above the root from inside `base`."""
    return "/".join([".."] * (base.count("/") + 2))


def describe(exc: BaseException) -> str:
    """An exception as its class and, where one exists, a fixed error code.

    Message text is never kept: an SDK puts the request host, which names the
    account or bucket, into the message of a connection or authentication error.
    """
    code = None
    response = getattr(exc, "response", None)
    if isinstance(response, dict):  # botocore ClientError
        code = response.get("Error", {}).get("Code")
    elif getattr(exc, "error_code", None):  # azure-core HttpResponseError
        code = str(exc.error_code)  # type: ignore[attr-defined]
    elif isinstance(exc, OSError) and exc.errno is not None:
        code = errno.errorcode.get(exc.errno)
    elif isinstance(exc, OSError) and str(exc) in _SFTP_STATUS:
        code = str(exc)
    return f"{type(exc).__name__}: {code}" if code else type(exc).__name__


# paramiko raises a bare OSError carrying one of these fixed SFTP status texts.
_SFTP_STATUS = {
    "End of file",
    "No such file",
    "Permission denied",
    "Failure",
    "Bad message",
    "No connection",
    "Connection lost",
    "Operation unsupported",
}


def quote(key: str) -> str:
    """Percent-encode a key for the URL path, keeping `/` and `.` literal."""
    return urllib.parse.quote(key, safe="/~")


def raw_request(
    scheme: str, host: str, method: str, path: str, headers: dict[str, str], body: bytes = b""
) -> tuple[int, str]:
    """Send one request with the path exactly as given."""
    conn_cls = http.client.HTTPSConnection if scheme == "https" else http.client.HTTPConnection
    conn = conn_cls(host, timeout=30)
    try:
        conn.putrequest(method, path, skip_host=True, skip_accept_encoding=True)
        conn.putheader("Host", host)
        for k, v in headers.items():
            if k.lower() != "host":
                conn.putheader(k, v)
        conn.putheader("Content-Length", str(len(body)))
        conn.endheaders(body if body else None)
        resp = conn.getresponse()
        text = resp.read().decode("utf-8", "replace")
        code = ""
        if "<Code>" in text:
            code = text.split("<Code>", 1)[1].split("</Code>", 1)[0]
        return resp.status, code
    finally:
        conn.close()


def run_keys(
    base: str,
    put: Callable[[str], tuple[int, str]],
    get: Callable[[str], tuple[int, str]],
    list_names: Callable[[], set[str]],
) -> list[dict[str, Any]]:
    """Probe every key: PUT, the names it added to a listing, GET."""
    out = []
    for label, template in KEYS:
        key = template.replace("{B}", base).replace("{UP}", above_root(base))
        before = list_names()
        try:
            put_status, put_code = put(key)
        except Exception as exc:  # noqa: BLE001 -- a refusal is a result
            put_status, put_code = -1, describe(exc)
        added = sorted(list_names() - before)
        try:
            get_status, get_code = get(key)
        except Exception as exc:  # noqa: BLE001
            get_status, get_code = -1, describe(exc)
        out.append(
            {
                "label": label,
                "key": key,
                "put": put_status,
                "put_code": put_code,
                "listed_new": added,
                "get_raw": get_status,
                "get_code": get_code,
            }
        )
    return out


# S3 ------------------------------------------------------------------------


def _s3_signed(creds: Any, region: str, service: str, method: str, url: str, auth_cls: Any) -> dict[str, str]:
    from botocore.awsrequest import AWSRequest

    req = AWSRequest(method=method, url=url, data=BODY if method == "PUT" else b"")
    req.headers["x-amz-content-sha256"] = "UNSIGNED-PAYLOAD"
    auth_cls(creds, service, region).add_auth(req)
    return dict(req.headers.items())


def _s3_target(endpoint: str | None, express: bool) -> dict[str, Any]:
    import boto3
    from botocore.auth import S3ExpressAuth, S3SigV4Auth
    from botocore.config import Config

    if endpoint is None:
        from dotenv import load_dotenv

        load_dotenv(override=False)
        region = os.environ["AWS_DEFAULT_REGION"]
        session = boto3.Session(region_name=region)
    else:
        sys.path.insert(0, str(Path.cwd()))
        from infra import _settings

        region = "us-east-1"
        session = boto3.Session(
            aws_access_key_id=_settings.MINIO_ACCESS_KEY,
            aws_secret_access_key=_settings.MINIO_SECRET_KEY,
            region_name=region,
        )
    cfg = Config(s3={"addressing_style": "path"}) if endpoint else None
    client = session.client("s3", endpoint_url=endpoint, config=cfg)
    hexid = uuid.uuid4().hex[:12]
    info: dict[str, Any] = {"region": region}

    if express:
        prefix = {"eu-central-1": "euc1", "eu-north-1": "eun1", "us-east-1": "use1", "us-west-2": "usw2"}
        zone_prefix = prefix.get(region)
        if zone_prefix is None:
            return {**info, "error": f"no AZ-id prefix known for {region}"}
        bucket = None
        codes = []
        for n in range(1, 7):
            az = f"{zone_prefix}-az{n}"
            name = f"rs-conformance-{hexid}--{az}--x-s3"
            try:
                client.create_bucket(
                    Bucket=name,
                    CreateBucketConfiguration={
                        "Location": {"Type": "AvailabilityZone", "Name": az},
                        "Bucket": {"Type": "Directory", "DataRedundancy": "SingleAvailabilityZone"},
                    },
                )
                bucket, info["az"] = name, az
                break
            except Exception as exc:  # noqa: BLE001
                codes.append(describe(exc))
        if bucket is None:
            # One code per zone tried, in zone order; the zone IDs name the region.
            return {**info, "error": "could not create a directory bucket", "attempt_codes": codes}
        host = f"{bucket}.s3express-{info['az']}.{region}.amazonaws.com"
        sess = client.create_session(Bucket=bucket)["Credentials"]
        from botocore.credentials import Credentials

        signing = Credentials(sess["AccessKeyId"], sess["SecretAccessKey"], sess["SessionToken"])
        service, auth_cls, scheme = "s3express", S3ExpressAuth, "https"
    else:
        bucket = f"rs-conformance-{hexid}"
        kwargs: dict[str, Any] = {"Bucket": bucket}
        if region != "us-east-1":
            kwargs["CreateBucketConfiguration"] = {"LocationConstraint": region}
        client.create_bucket(**kwargs)
        signing = session.get_credentials().get_frozen_credentials()
        service, auth_cls = "s3", S3SigV4Auth
        if endpoint:
            parsed = urllib.parse.urlsplit(endpoint)
            scheme, host = parsed.scheme, parsed.netloc
        else:
            scheme, host = "https", f"{bucket}.s3.{region}.amazonaws.com"

    path_prefix = f"/{bucket}" if endpoint else ""

    def path_for(key: str) -> str:
        return f"{path_prefix}/{quote(key)}"

    def put(key: str) -> tuple[int, str]:
        path = path_for(key)
        headers = _s3_signed(signing, region, service, "PUT", f"{scheme}://{host}{path}", auth_cls)
        return raw_request(scheme, host, "PUT", path, headers, BODY)

    def get(key: str) -> tuple[int, str]:
        path = path_for(key)
        headers = _s3_signed(signing, region, service, "GET", f"{scheme}://{host}{path}", auth_cls)
        return raw_request(scheme, host, "GET", path, headers)

    def list_names() -> set[str]:
        names: set[str] = set()
        for page in client.get_paginator("list_objects_v2").paginate(Bucket=bucket):
            names.update(o["Key"] for o in page.get("Contents", []))
        return names

    try:
        results = run_keys("p", put, get, list_names)
    finally:
        leftover = sorted(list_names())
        for name in leftover:
            client.delete_object(Bucket=bucket, Key=name)
        remaining = sorted(list_names())
        client.delete_bucket(Bucket=bucket)
    return {**info, "bucket": bucket, "results": results, "cleanup_remaining": remaining}


# Azure ---------------------------------------------------------------------


def _azure_target(conn_str: str) -> dict[str, Any]:
    from azure.storage.blob import BlobServiceClient, ContainerSasPermissions, generate_container_sas

    service = BlobServiceClient.from_connection_string(conn_str)
    container = f"{PROBE_PREFIX}-{uuid.uuid4().hex[:12]}"
    cc = service.create_container(container)
    parts = dict(p.split("=", 1) for p in conn_str.strip(";").split(";") if "=" in p)
    sas = generate_container_sas(
        account_name=str(service.account_name),
        container_name=container,
        account_key=parts["AccountKey"],
        permission=ContainerSasPermissions(read=True, write=True, create=True, delete=True, list=True),
        expiry=dt.datetime.now(dt.UTC) + dt.timedelta(hours=1),
    )
    url = urllib.parse.urlsplit(service.url)
    scheme, host = url.scheme, url.netloc
    account_path = url.path.rstrip("/")  # "/devstoreaccount1" on Azurite, "" on Azure
    hns = None
    try:
        hns = bool(service.get_account_information().get("is_hns_enabled"))
    except Exception:  # noqa: BLE001
        hns = None

    def path_for(key: str) -> str:
        return f"{account_path}/{container}/{quote(key)}?{sas}"

    common = {"x-ms-version": "2023-11-03"}

    def put(key: str) -> tuple[int, str]:
        headers = {**common, "x-ms-blob-type": "BlockBlob"}
        return raw_request(scheme, host, "PUT", path_for(key), headers, BODY)

    def get(key: str) -> tuple[int, str]:
        return raw_request(scheme, host, "GET", path_for(key), common)

    def list_names() -> set[str]:
        return {b.name for b in cc.list_blobs()}

    try:
        results = run_keys("p", put, get, list_names)
    finally:
        remaining_before = sorted(list_names())
        cc.delete_container()
    return {
        "account_hns": hns,
        "container": container,
        "results": results,
        "listed_before_container_delete": remaining_before,
    }


# SFTP ----------------------------------------------------------------------


def _sftp_target() -> dict[str, Any]:
    import paramiko

    sys.path.insert(0, str(Path.cwd()))
    from infra import _settings

    transport = paramiko.Transport((_settings.SFTP_HOST, _settings.SFTP_PORT))
    transport.connect(username=_settings.SFTP_USER, password=_settings.SFTP_PASS)
    sftp = paramiko.SFTPClient.from_transport(transport)
    assert sftp is not None
    base = f"upload/{PROBE_PREFIX}-{uuid.uuid4().hex[:12]}"
    # POSIX resolution is physical: a path through `e/` or `a/` needs the
    # directory, so the probe creates the ones the keys walk through.
    sftp.mkdir(base)
    for d in ("a", "e", "g"):
        sftp.mkdir(f"{base}/{d}")

    def walk(path: str) -> set[str]:
        names: set[str] = set()
        for entry in sftp.listdir_attr(path):
            full = f"{path}/{entry.filename}"
            names.add(full)
            if entry.st_mode is not None and (entry.st_mode & 0o170000) == 0o040000:
                names |= walk(full)
        return names

    def put(key: str) -> tuple[int, str]:
        with sftp.open(key, "wb") as fh:
            fh.write(BODY)
        return 200, ""

    def get(key: str) -> tuple[int, str]:
        with sftp.open(key, "rb") as fh:
            fh.read()
        return 200, ""

    try:
        results = run_keys(base, put, get, lambda: walk("upload"))
        home = sftp.normalize(".")
    finally:
        for name in sorted(walk(base), key=len, reverse=True):
            try:
                sftp.remove(name)
            except OSError:
                sftp.rmdir(name)
        sftp.rmdir(base)
        sftp.close()
        transport.close()
    return {"home": home, "base": base, "precreated_dirs": ["a", "e", "g"], "results": results}


_DROP = {"bucket", "container", "region", "az"}
_RANDOM_NAME = re.compile(rf"(rs-conformance|{PROBE_PREFIX})-[0-9a-f]{{12}}(--[a-z0-9-]+--x-s3)?")


def redact(value: Any) -> Any:
    """Strip what could identify an account or a run from a result.

    Resource names, region and zone are dropped and the random folder names
    are replaced by a placeholder. Exceptions reach the result only through
    ``describe``, which keeps no message text.
    """
    if isinstance(value, dict):
        return {k: redact(v) for k, v in value.items() if k not in _DROP}
    if isinstance(value, list):
        return [redact(v) for v in value]
    if isinstance(value, str):
        return _RANDOM_NAME.sub("<probe>", value)
    return value


def main() -> None:
    parser = argparse.ArgumentParser(description="Live probe of raw paths and keys")
    parser.add_argument("--target", required=True)
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    runners: dict[str, Callable[[], dict[str, Any]]] = {
        "s3": lambda: _s3_target(None, express=False),
        "s3express": lambda: _s3_target(None, express=True),
        "minio": lambda: _s3_target(_minio_endpoint(), express=False),
        "azure": lambda: _azure_target(_azure_live_conn()),
        "azurite": lambda: _azure_target(_azurite_conn()),
        "sftp": _sftp_target,
    }
    report: dict[str, Any] = {"date": dt.date.today().isoformat(), "targets": {}}
    for name in args.target.split(","):
        try:
            report["targets"][name] = runners[name]()
        except Exception as exc:  # noqa: BLE001
            report["targets"][name] = {"error": describe(exc)}
        report["targets"][name] = redact(report["targets"][name])
        print(json.dumps({name: report["targets"][name]}, indent=1, ensure_ascii=False))
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(report, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


def _minio_endpoint() -> str:
    sys.path.insert(0, str(Path.cwd()))
    from infra import _settings

    return _settings.MINIO_ENDPOINT


def _azurite_conn() -> str:
    sys.path.insert(0, str(Path.cwd()))
    from infra import _settings

    return _settings.AZURITE_CONN_STR


def _azure_live_conn() -> str:
    from dotenv import load_dotenv

    load_dotenv(override=False)
    value = os.environ["AZURE_STORAGE_CONNECTION_STRING"]
    if "devstoreaccount1" in value or "UseDevelopmentStorage" in value:
        raise SystemExit("AZURE_STORAGE_CONNECTION_STRING points at Azurite")
    return value


if __name__ == "__main__":
    main()
