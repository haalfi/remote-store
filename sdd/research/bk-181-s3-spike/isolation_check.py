"""Minimal vcrpy + s3fs isolation check.

Bypasses pytest-recording entirely: drives vcrpy's ``use_cassette`` context
manager directly to determine whether the failure mode observed in
``test_spike.py`` is a pytest-recording interaction (workaround possible)
or a fundamental vcrpy + aiobotocore incompatibility (PR 2 fail path).

Run::

    RS_TEST_LIVE_S3=1 hatch run python sdd/research/bk-181-s3-spike/isolation_check.py
"""

from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path

import vcr
from dotenv import load_dotenv

BUCKET = "rs-conformance-bk181spike"
CASSETTE = Path(__file__).parent / "isolation.yaml"
SMALL_PAYLOAD = b"hello s3 isolation\n"


def _require_live_credentials() -> dict[str, str]:
    load_dotenv(override=False)
    if os.environ.get("RS_TEST_LIVE_S3") != "1":
        sys.exit("recording requires RS_TEST_LIVE_S3=1 (a real AWS S3 account)")
    out: dict[str, str] = {}
    for var in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_DEFAULT_REGION"):
        value = (os.environ.get(var) or "").strip()
        if not value:
            sys.exit(f"recording requires {var}")
        out[var] = value
    return out


def main() -> int:
    creds = _require_live_credentials()
    print(f"region: {creds['AWS_DEFAULT_REGION']}, bucket: {BUCKET}")

    # Ensure bucket exists with sync boto3 (vcrpy's boto3_stubs handles botocore).
    import boto3
    from botocore.exceptions import ClientError

    sync_client = boto3.client(
        "s3",
        aws_access_key_id=creds["AWS_ACCESS_KEY_ID"],
        aws_secret_access_key=creds["AWS_SECRET_ACCESS_KEY"],
        region_name=creds["AWS_DEFAULT_REGION"],
    )
    try:
        kwargs: dict[str, object] = {"Bucket": BUCKET}
        if creds["AWS_DEFAULT_REGION"] != "us-east-1":
            kwargs["CreateBucketConfiguration"] = {"LocationConstraint": creds["AWS_DEFAULT_REGION"]}
        try:
            sync_client.create_bucket(**kwargs)
            print("bucket: created")
        except ClientError as e:
            code = e.response.get("Error", {}).get("Code", "")
            if code in ("BucketAlreadyOwnedByYou", "BucketAlreadyExists"):
                print(f"bucket: already exists ({code})")
            else:
                raise
    finally:
        sync_client.close()

    # Now try the s3fs path under vcrpy cassette.
    if CASSETTE.exists():
        CASSETTE.unlink()
        print(f"removed stale cassette: {CASSETTE.name}")

    print("\n--- attempting record via vcr.use_cassette ---")
    my_vcr = vcr.VCR(
        record_mode="all",  # always record on this run
        decode_compressed_response=True,
        filter_query_parameters=[
            "X-Amz-Signature",
            "X-Amz-Credential",
            "X-Amz-Date",
            "X-Amz-Expires",
            "X-Amz-SignedHeaders",
            "X-Amz-Algorithm",
            "X-Amz-Security-Token",
        ],
    )
    try:
        with my_vcr.use_cassette(str(CASSETTE)):
            import s3fs

            fs = s3fs.S3FileSystem(
                key=creds["AWS_ACCESS_KEY_ID"],
                secret=creds["AWS_SECRET_ACCESS_KEY"],
                client_kwargs={"region_name": creds["AWS_DEFAULT_REGION"]},
                anon=False,
            )
            print(f"s3fs version: {s3fs.__version__}")
            print(f"calling pipe_file({BUCKET}/isolation/small.bin)")
            fs.pipe_file(f"{BUCKET}/isolation/small.bin", SMALL_PAYLOAD)
            print("pipe_file: OK")

            print("calling cat_file")
            got = fs.cat_file(f"{BUCKET}/isolation/small.bin")
            print(f"cat_file: {len(got)} bytes")
            assert got == SMALL_PAYLOAD, f"bytes mismatch: {got!r} != {SMALL_PAYLOAD!r}"
            print("RESULT: PASS (record succeeded, bytes match)")
    except Exception as exc:
        print(f"\nRESULT: FAIL during record — {type(exc).__name__}: {exc}")
        traceback.print_exc()
        return 1

    # Check cassette contents.
    if not CASSETTE.exists():
        print("\nERROR: cassette was not written")
        return 1
    size = CASSETTE.stat().st_size
    print(f"\ncassette: {CASSETTE.name} ({size} bytes)")

    print("\n--- attempting replay via vcr.use_cassette ---")
    replay_vcr = vcr.VCR(record_mode="none")
    try:
        with replay_vcr.use_cassette(str(CASSETTE)):
            import s3fs

            fs = s3fs.S3FileSystem(
                key="AKIAFAKE",
                secret="fake",  # noqa: S106 -- replay fake
                client_kwargs={"region_name": creds["AWS_DEFAULT_REGION"]},
                anon=False,
            )
            print("replay cat_file")
            got = fs.cat_file(f"{BUCKET}/isolation/small.bin")
            print(f"replay cat_file: {len(got)} bytes")
            assert got == SMALL_PAYLOAD, f"bytes mismatch on replay: {got!r} != {SMALL_PAYLOAD!r}"
            print("RESULT: PASS (replay succeeded, bytes match)")
            return 0
    except Exception as exc:
        print(f"\nRESULT: FAIL during replay — {type(exc).__name__}: {exc}")
        traceback.print_exc()
        return 2


if __name__ == "__main__":
    sys.exit(main())
