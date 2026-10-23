"""Checks of the probe's key templates and of what its output may contain."""

from __future__ import annotations

import posixpath

import pytest
from azure.core.exceptions import ResourceNotFoundError, ServiceRequestError
from botocore.exceptions import ClientError, EndpointConnectionError
from probe_paths import above_root, describe, redact

HOST = "probeacct7.blob.core.windows.net"
BUCKET_HOST = "rs-private-bucket.s3.eu-central-1.amazonaws.com"


@pytest.mark.parametrize("base", ["p", "upload/x", "a/b/c"])
def test_above_root_climbs_one_level_past_the_root(base: str) -> None:
    resolved = posixpath.normpath(f"/root/{base}/{above_root(base)}/x")
    assert resolved == "/x"


@pytest.mark.parametrize(
    ("exc", "expected"),
    [
        (ServiceRequestError(f"Failed to establish a new connection to {HOST}"), "ServiceRequestError"),
        (EndpointConnectionError(endpoint_url=f"https://{BUCKET_HOST}/k"), "EndpointConnectionError"),
        (
            ClientError({"Error": {"Code": "AccessDenied", "Message": f"denied on {BUCKET_HOST}"}}, "CreateBucket"),
            "ClientError: AccessDenied",
        ),
        (ResourceNotFoundError(f"The specified blob does not exist at {HOST}"), "ResourceNotFoundError"),
        (PermissionError(13, "Permission denied"), "PermissionError: EACCES"),
        (FileNotFoundError(2, "No such file"), "FileNotFoundError: ENOENT"),
        (OSError("Failure"), "OSError: Failure"),
        (OSError(f"Server connection dropped: {HOST}"), "OSError"),
    ],
)
def test_describe_keeps_class_and_code_never_message_text(exc: BaseException, expected: str) -> None:
    text = describe(exc)
    assert text == expected
    assert redact(text) == expected


def test_redact_drops_names_and_keeps_attempt_codes() -> None:
    out = redact({"bucket": "b", "region": "r", "az": "z", "attempt_codes": ["AccessDenied"], "key": "x"})
    assert out == {"attempt_codes": ["AccessDenied"], "key": "x"}
