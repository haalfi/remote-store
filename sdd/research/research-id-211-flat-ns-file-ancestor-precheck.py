"""ID-211 measurement harness: cost of a HEAD pre-check on flat-NS writes.

Measures the per-write overhead of adding a "for each slash-aligned ancestor,
HEAD it to check whether it's a regular file" gate to S3 / Azure-non-HNS /
SQLBlob ``write()``. The user-nominated optimisation is to skip the gate
when the path has no slash, so the cost only applies to nested-path writes.

Each (backend, depth, variant) cell runs ``ITERATIONS`` writes after
``WARMUP`` discarded warmup writes. The harness reports the per-write wall
time at P50 / P95 / P99 and the mean / median overhead vs the baseline
(write-only) variant at the same depth.

Variants per backend, per depth:

* ``baseline``    -- existing ``write(path, payload)``.
* ``precheck``    -- proposed ``_check_no_file_ancestor`` walk (one
                     ``HEAD`` / ``SELECT`` per slash-aligned ancestor)
                     followed by the existing ``write``.

The harness writes a plain-Markdown table at ``--out`` (default sibling
``.md`` file). Run as:

    hatch run python sdd/research/research-id-211-flat-ns-file-ancestor-precheck.py

Stage-1 envelope: only moto + in-memory SQLite are exercised by default;
Azurite is optional and gated on Docker being available on the host.
Live S3 / Azure ADLS Gen2 are out of scope -- if the disposition is still
unclear after this run, the user can extend the harness via ``--include
azure_live,s3_live`` and supplying ``RS_TEST_LIVE_*`` creds.
"""

from __future__ import annotations

import argparse
import socket
import statistics
import sys
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Silence moto's werkzeug access log: at 100 writes x 4 depths x 2 variants
# the per-request log lines drown out our own output and slow the harness.
import logging  # noqa: E402

for _name in ("werkzeug", "moto", "boto3", "botocore", "s3fs", "urllib3", "azure"):
    logging.getLogger(_name).setLevel(logging.WARNING)
logging.getLogger("werkzeug").setLevel(logging.ERROR)


ITERATIONS = 100
WARMUP = 10
DEPTHS = (0, 1, 3, 6)
PAYLOAD = b"x" * 1024  # 1 KiB

# ---------------------------------------------------------------------------
# Backend bootstrap


@dataclass
class BackendHarness:
    name: str
    backend: object  # remote_store Backend
    head_one: Callable[[str], bool]
    """Return True iff the key exists as a regular file on the backend.

    Used by the simulated pre-check. Each call mirrors one HEAD round trip
    against the underlying store.
    """
    teardown: Callable[[], None]


def _make_path(depth: int, seed: int, tag: str) -> str:
    """Build a slash-aligned path with the requested ancestor depth.

    ``tag`` partitions the per-variant key space so that the
    ``baseline`` and ``precheck`` cells of the same depth do not
    collide on each other's ``f{seed}.bin`` writes (every variant
    writes with ``overwrite=False``, so a collision raises
    ``AlreadyExists`` and aborts the run).
    """
    parts = [f"d{i}_{tag}" for i in range(depth)]
    parts.append(f"f{seed}_{tag}.bin")
    return "/".join(parts)


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _boot_s3_moto() -> BackendHarness | None:
    try:
        import boto3
        from moto.moto_server.threaded_moto_server import ThreadedMotoServer

        from remote_store.backends._s3 import S3Backend
    except ImportError as exc:
        print(f"# s3_moto unavailable: {exc}")
        return None

    port = _free_port()
    server = ThreadedMotoServer(port=port, verbose=False)
    server.start()
    endpoint = f"http://127.0.0.1:{port}"
    bucket = f"id211-{uuid.uuid4().hex[:8]}"
    client = boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id="testing",
        aws_secret_access_key="testing",
        region_name="us-east-1",
    )
    client.create_bucket(Bucket=bucket)
    backend = S3Backend(
        bucket=bucket,
        key="testing",
        secret="testing",
        region_name="us-east-1",
        endpoint_url=endpoint,
    )

    def _head_one(key: str) -> bool:
        # head_object on the raw key -- one HEAD round trip; matches what
        # the proposed _check_no_file_ancestor would actually do.
        try:
            backend._fs.call_s3("head_object", Bucket=bucket, Key=key)  # noqa: SLF001
        except Exception:
            return False
        return True

    def _teardown() -> None:
        backend.close()
        server.stop()

    return BackendHarness(name="s3_moto", backend=backend, head_one=_head_one, teardown=_teardown)


def _boot_sqlblob() -> BackendHarness | None:
    try:
        import sqlalchemy as sa

        from remote_store.backends._sqlalchemy import SQLBlobBackend
    except ImportError as exc:
        print(f"# sqlblob unavailable: {exc}")
        return None

    backend = SQLBlobBackend(url="sqlite:///:memory:")
    table = backend._table  # noqa: SLF001
    engine = backend._engine  # noqa: SLF001

    def _head_one(key: str) -> bool:
        with engine.connect() as conn:
            row = conn.execute(sa.select(sa.literal(1)).where(table.c.key == key)).first()
        return row is not None

    def _teardown() -> None:
        backend.close()

    return BackendHarness(name="sqlblob_sqlite", backend=backend, head_one=_head_one, teardown=_teardown)


def _azurite_reachable(host: str = "127.0.0.1", port: int = 10000) -> bool:
    try:
        s = socket.create_connection((host, port), timeout=1)
    except OSError:
        return False
    s.close()
    return True


def _boot_azurite() -> BackendHarness | None:
    if not _azurite_reachable():
        print("# azurite unavailable: 127.0.0.1:10000 unreachable (Docker not started)")
        return None
    try:
        from azure.storage.blob import BlobServiceClient

        from infra._settings import AZURITE_HOST, AZURITE_PORT
        from remote_store.backends._azure import AzureBackend
    except ImportError as exc:
        print(f"# azurite unavailable: {exc}")
        return None

    conn_str = (
        "DefaultEndpointsProtocol=http;"
        "AccountName=devstoreaccount1;"
        "AccountKey=Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq/K1SZFPTOtr/KBHBeksoGMGw==;"
        f"BlobEndpoint=http://{AZURITE_HOST}:{AZURITE_PORT}/devstoreaccount1;"
    )
    container = f"id211-{uuid.uuid4().hex[:8]}"
    service = BlobServiceClient.from_connection_string(conn_str)
    service.create_container(container)
    backend = AzureBackend(container=container, connection_string=conn_str)

    def _head_one(key: str) -> bool:
        from azure.core.exceptions import ResourceNotFoundError

        bc = backend._blob_client(key)  # noqa: SLF001
        try:
            bc.get_blob_properties()
        except ResourceNotFoundError:
            return False
        return True

    def _teardown() -> None:
        backend.close()
        try:
            service.delete_container(container)
        finally:
            service.close()

    return BackendHarness(name="azurite", backend=backend, head_one=_head_one, teardown=_teardown)


# ---------------------------------------------------------------------------
# Measurement core


def _simulated_precheck(harness: BackendHarness, path: str) -> None:
    """Mirror the proposed _check_no_file_ancestor walk.

    Skips when the path has no slash (the user's O(1) early exit). For
    nested paths, performs one HEAD per slash-aligned ancestor. A real
    helper would raise InvalidPath on the first hit -- in the harness none
    of the ancestors exist, so every walk runs to completion (the
    worst-case row).
    """
    if "/" not in path:
        return
    parts = path.split("/")
    for i in range(1, len(parts)):
        ancestor = "/".join(parts[:i])
        if harness.head_one(ancestor):
            return  # would raise InvalidPath in production


def _time_one(fn: Callable[[], None]) -> float:
    t0 = time.perf_counter()
    fn()
    return time.perf_counter() - t0


def _measure(harness: BackendHarness, depth: int, variant: str) -> list[float]:
    samples: list[float] = []
    tag = f"d{depth}_{variant}"
    for i in range(WARMUP + ITERATIONS):
        path = _make_path(depth, seed=i, tag=tag)

        def _baseline() -> None:
            harness.backend.write(path, PAYLOAD)  # type: ignore[attr-defined]

        def _precheck() -> None:
            _simulated_precheck(harness, path)
            harness.backend.write(path, PAYLOAD)  # type: ignore[attr-defined]

        fn = _baseline if variant == "baseline" else _precheck
        dt = _time_one(fn)
        if i >= WARMUP:
            samples.append(dt)
    return samples


# ---------------------------------------------------------------------------
# Reporting


def _summarise(samples: list[float]) -> dict[str, float]:
    samples = sorted(samples)
    return {
        "p50_ms": samples[len(samples) // 2] * 1000,
        "p95_ms": samples[int(len(samples) * 0.95)] * 1000,
        "p99_ms": samples[int(len(samples) * 0.99)] * 1000,
        "mean_ms": statistics.mean(samples) * 1000,
    }


def _format_md(rows: list[dict[str, object]]) -> str:
    by_backend: dict[str, list[dict[str, object]]] = {}
    for row in rows:
        by_backend.setdefault(str(row["backend"]), []).append(row)

    out: list[str] = []
    out.append("## Measurement results\n")
    out.append(
        f"Each row: {ITERATIONS} writes of a {len(PAYLOAD)}-byte payload after "
        f"{WARMUP} discarded warmups. Backend = harness wrapper around the same "
        "production code paths the conformance suite drives.\n"
    )
    out.append(
        "Worst case: in `precheck`, no ancestor exists, so every slash-aligned "
        "ancestor HEAD runs to completion (a real `InvalidPath` hit would short "
        "circuit on the first file ancestor). Numbers are the upper bound on "
        "the proposed gate's per-call cost.\n"
    )
    for backend, brows in by_backend.items():
        out.append(f"\n### {backend}\n")
        out.append("| depth | variant   | P50 (ms) | P95 (ms) | P99 (ms) | mean (ms) | overhead vs baseline (mean) |")
        out.append("| ----- | --------- | -------- | -------- | -------- | --------- | --------------------------- |")
        baselines = {int(r["depth"]): float(r["mean_ms"]) for r in brows if r["variant"] == "baseline"}  # type: ignore[arg-type]
        for r in brows:
            depth = int(r["depth"])  # type: ignore[arg-type]
            mean_ms = float(r["mean_ms"])  # type: ignore[arg-type]
            base = baselines.get(depth, 0.0)
            if r["variant"] == "baseline":
                overhead = "—"
            else:
                delta = mean_ms - base
                pct = (delta / base * 100) if base > 0 else 0.0
                overhead = f"{delta:+.3f} ms ({pct:+.1f}%)"
            out.append(
                "| {depth} | {variant:<9s} | {p50:>8.3f} | {p95:>8.3f} | {p99:>8.3f} | {mean:>9.3f} | {ov} |".format(
                    depth=depth,
                    variant=str(r["variant"]),
                    p50=float(r["p50_ms"]),  # type: ignore[arg-type]
                    p95=float(r["p95_ms"]),  # type: ignore[arg-type]
                    p99=float(r["p99_ms"]),  # type: ignore[arg-type]
                    mean=mean_ms,
                    ov=overhead,
                )
            )
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------------------
# Entry point


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--include",
        default="s3_moto,sqlblob_sqlite,azurite",
        help="Comma-separated backends to bootstrap.",
    )
    ap.add_argument(
        "--out",
        default=str(REPO_ROOT / "tmp" / "id211-results.md"),
        help=(
            "Write the Markdown table here (in addition to stdout). "
            "Defaults to ./tmp/id211-results.md (gitignored); the curated "
            "table lives in research-id-211-flat-ns-file-ancestor-precheck.md."
        ),
    )
    args = ap.parse_args()

    booters: dict[str, Callable[[], BackendHarness | None]] = {
        "s3_moto": _boot_s3_moto,
        "sqlblob_sqlite": _boot_sqlblob,
        "azurite": _boot_azurite,
    }
    want = [name.strip() for name in args.include.split(",") if name.strip()]

    harnesses: list[BackendHarness] = []
    for name in want:
        if name not in booters:
            print(f"# unknown backend: {name}", file=sys.stderr)
            continue
        h = booters[name]()
        if h is not None:
            harnesses.append(h)

    if not harnesses:
        print("# no backends bootstrapped; aborting", file=sys.stderr)
        return 1

    rows: list[dict[str, object]] = []
    try:
        for h in harnesses:
            for depth in DEPTHS:
                for variant in ("baseline", "precheck"):
                    samples = _measure(h, depth, variant)
                    stats = _summarise(samples)
                    row: dict[str, object] = {"backend": h.name, "depth": depth, "variant": variant, **stats}
                    rows.append(row)
                    print(
                        f"{h.name} depth={depth} variant={variant} "
                        f"P50={stats['p50_ms']:.3f}ms P95={stats['p95_ms']:.3f}ms "
                        f"P99={stats['p99_ms']:.3f}ms mean={stats['mean_ms']:.3f}ms"
                    )
    finally:
        for h in reversed(harnesses):
            try:
                h.teardown()
            except Exception as exc:  # noqa: BLE001
                print(f"# teardown of {h.name} failed: {exc}", file=sys.stderr)

    md = _format_md(rows)
    Path(args.out).write_text(md, encoding="utf-8")
    print(f"\n# wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
