"""Backend-agnostic cassette scrub core: declarative profiles for vcrpy.

Each HTTP backend family declares one ``CassetteProfile`` naming everything
its cassettes must never carry — credentials, account identity, per-run
identifiers, machine-specific strings — plus where its cassettes live and
which fixture ids share them. ``build_profile_vcr_config`` turns a profile
into the ``vcr_config`` dict the conformance conftest feeds to vcrpy. This
module holds the shapes and the one generic config factory; the per-backend
profile declarations live in ``_cassettes_azure.py`` / ``_cassettes_graph.py``
(spec 049, REC-001).
"""

from __future__ import annotations

import json
import os
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal
from urllib.parse import urlsplit

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

Expectation = Literal["required-to-fire", "opportunistic"]
"""Audit expectation of a named rule (REC-002 / REC-006).

``required-to-fire`` rules must redact at least once over a full-slice
recording — zero fires means the scrub layer silently stopped seeing the
secret it owns. ``opportunistic`` rules guard shapes a normal recording
may legitimately never produce. Exact counts never gate: they are
workload-dependent.
"""

# region: named rule shapes (REC-002)


@dataclass(frozen=True)
class RedactPattern:
    """A named bytes-domain redaction applied to request/response bodies.

    Bytes, not str, so binary payloads are scrubbed without a decode that
    would crash on raw bytes; the core owns the str round-trip dispatch.
    """

    name: str
    pattern: re.Pattern[bytes]
    replacement: bytes
    expectation: Expectation = "opportunistic"

    def apply(self, raw: bytes) -> bytes:
        out, fires = self.pattern.subn(self.replacement, raw)
        _record_fires(self.name, fires)
        return out


@dataclass(frozen=True)
class UriRewrite:
    """A named str-domain rewrite applied to request URIs and header values.

    ``replacement`` may use backreferences (``\\1``). Body-side application
    of the same pattern is declared separately as a ``RedactPattern`` bytes
    twin, so each surface has its own audit identity.
    """

    name: str
    pattern: re.Pattern[str]
    replacement: str
    expectation: Expectation = "opportunistic"

    def apply(self, value: str) -> str:
        out, fires = self.pattern.subn(self.replacement, value)
        _record_fires(self.name, fires)
        return out


def _single_form(value: str) -> tuple[str, ...]:
    return (value,)


@dataclass(frozen=True)
class EnvRedact:
    """A live value resolved at record time and redacted everywhere (REC-003).

    ``resolve`` returns the live value in record mode (``None`` disables the
    rule, e.g. replay mode or an unset env var; an empty string is rejected
    at config build — that is a misconfigured resolver, not a disable
    signal). The core rewrites every
    ``forms(value)`` variant to ``fake`` across request URIs, request-header
    values, request bodies, and response bodies — bytes and str alike.
    ``forms`` exists for values a service echoes in more than one shape
    (the Graph cid appears hyphen-split inside an MSAL ``Oid:`` header).
    """

    name: str
    resolve: Callable[[], str | None]
    fake: str
    case_insensitive: bool = False
    forms: Callable[[str], tuple[str, ...]] = _single_form
    expectation: Expectation = "required-to-fire"


# endregion

# region: pre-signed URL policy (REC-004)


@dataclass(frozen=True)
class PresignedPolicy:
    """Collapse every pre-signed URL to one stable placeholder.

    A pre-signed URL carries its own access token, so nothing of it (host,
    path, query) may survive into a cassette. Any request whose host is not
    one of ``api_hosts`` is treated as pre-signed content traffic and has
    its URI (and ``Host`` header) replaced with ``placeholder`` — in record
    and replay mode alike, so the request the backend re-issues from a
    scrubbed body/header normalises to the same value the recorded request
    was rewritten to, and vcrpy matches them.

    Replay is therefore order-dependent: every pre-signed interaction in a
    cassette collapses to one method+URI and vcrpy disambiguates solely by
    recorded order. Concurrent pre-signed requests within a single test are
    unsupported under replay.
    """

    api_hosts: tuple[str, ...]
    placeholder: str

    @property
    def placeholder_host(self) -> str:
        return urlsplit(self.placeholder).hostname or self.placeholder

    def is_presigned(self, uri: str) -> bool:
        """True when *uri*'s host is a pre-signed content host.

        A URI with no host (relative, or a bare token) is *not* pre-signed,
        so it falls through to the normal id-normalisation path — a
        defensive default that never over-redacts.
        """
        host = (urlsplit(uri).hostname or "").lower()
        if not host:
            return False
        return not any(host == h or host.endswith("." + h) for h in self.api_hosts)


# endregion

# region: forbidden-pattern envelope (REC-006)

# Env-independent "must never appear in a committed cassette" markers shared
# by EVERY profile. Each encodes a failure mode — a credential form, token
# shape, or identity leak the scrub layer owns — so a re-record, hand edit,
# or bad merge cannot silently reintroduce one. Two consumers run the same
# combined view (``CassetteProfile.all_forbidden_patterns``): the recorder's
# Step-4 scrub-verify and the creds-free CI sweep in ``test_cassettes.py``.
# Patterns are bytes, matched case-insensitively.
FORBIDDEN_ENVELOPE: tuple[tuple[str, bytes], ...] = (
    # A bearer token that did NOT get redacted to ``Bearer REDACTED``.
    ("bare bearer token", rb"Bearer (?!REDACTED)\S"),
    # Any JWT (``eyJ<base64url>.``) regardless of the surrounding key, so a
    # token leaking outside an Authorization header is still caught.
    ("bare JWT", rb"eyJ[A-Za-z0-9_-]{10,}\."),
    # OAuth credential form fields that escaped the request-body scrub.
    ("unredacted client_secret", rb"client_secret=(?!REDACTED)"),
    ("unredacted refresh_token", rb"refresh_token=(?!REDACTED)"),
    ("unredacted assertion", rb"(?:client_)?assertion=(?!REDACTED)"),
    # An MSAL ``Oid:`` anchor (``X-AnchorMailbox``) embeds the account id as
    # a full GUID whose low bits are the drive cid in hyphen-split form —
    # missed by a contiguous-id rewrite, so it gets its own marker.
    ("oid anchor (hyphen-split account id)", rb"Oid:[0-9a-fA-F-]{36}"),
    # A bare email address anywhere in the tree (account PII). The widest
    # false-positive surface of any marker: a future cassette legitimately
    # carrying an ``x@y.tld``-shaped value would turn the sweep red with no
    # real leak. Kept deliberately — a raw account email is a real failure
    # mode no other marker covers on every surface. If it ever trips on
    # benign content, scope it (exclude the matched domain/field) rather
    # than dropping the gate.
    ("bare email address", rb"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
)

# endregion

# region: profile


@dataclass(frozen=True)
class CassetteProfile:
    """Everything one HTTP backend family declares about its cassettes (REC-007).

    Registering a fixture with a profile (``BackendFixture.cassette_profile``)
    is the single registration act: directory routing, cassette-name aliasing,
    the missing-cassette skip, scrub config, and audit inclusion all derive
    from the profile — there is no second table to extend. A fixture id
    carrying a profile must appear in that profile's ``fixture_aliases``;
    the conformance conftest fails loud at routing-map build otherwise.
    """

    backend: str
    """Backend family name (``"azure"``, ``"graph"``)."""
    cassette_dir: Path
    """Per-backend cassette directory (``tests/backends/cassettes/<backend>/``)."""
    fixture_aliases: Mapping[str, str]
    """fixture id → canonical cassette suffix (``{"azure_live": "azure", ...}``).

    Live (record) and replay (playback) fixture ids map to one shared suffix
    so both read and write the same cassette file.
    """
    filter_headers: tuple[Any, ...] = ()
    """vcrpy-native request-header filter: a plain entry deletes the header,
    a ``(name, value)`` tuple rewrites a *present* header in place (and never
    adds one when absent). Composed by vcrpy BEFORE the custom hook, matched
    case-insensitively; the declared key case is what a rewrite re-inserts,
    so it must match the case cassettes record (REC-005)."""
    filter_query_parameters: tuple[str, ...] = ()
    env_redacts: tuple[EnvRedact, ...] = ()
    uri_rewrites: tuple[UriRewrite, ...] = ()
    presigned: PresignedPolicy | None = None
    request_body_redactions: tuple[RedactPattern, ...] = ()
    response_body_redactions: tuple[RedactPattern, ...] = ()
    response_header_deletes: frozenset[str] = frozenset()
    rewrite_response_headers: tuple[str, ...] = ()
    """Response headers whose *values* get the env-redact + uri-rewrite chain
    (e.g. ``x-ms-copy-source`` echoing the live account)."""
    url_response_headers: tuple[str, ...] = ()
    """Response headers whose values are URLs (``Location``): a pre-signed
    host collapses to the placeholder; an API-host value keeps host + path
    for review but has its whole query wiped value-based (it is response-side
    and never matched, so over-wiping is safe — unlike request URIs, which
    keep their query structure because it is part of vcrpy's match key)."""
    forbidden_patterns: tuple[tuple[str, bytes], ...] = ()
    """Per-profile additions to ``FORBIDDEN_ENVELOPE``."""
    match_on: tuple[str, ...] | None = None
    """Custom vcrpy matcher set, or ``None`` for vcrpy's default."""
    decode_compressed_response: bool = True

    def resolve_live_values(self) -> dict[str, str | None]:
        """Resolve every ``EnvRedact`` to its live value (record mode only)."""
        return {er.name: er.resolve() for er in self.env_redacts}

    def all_forbidden_patterns(self) -> tuple[tuple[str, bytes], ...]:
        """The envelope plus this profile's additions — the Step-4/CI gate set."""
        return (*FORBIDDEN_ENVELOPE, *self.forbidden_patterns)

    def named_rules(self) -> tuple[tuple[str, Expectation], ...]:
        """Audit inventory: ``(rule_name, expectation)`` for every named rule."""
        rules: list[tuple[str, Expectation]] = [(er.name, er.expectation) for er in self.env_redacts]
        rules.extend((uw.name, uw.expectation) for uw in self.uri_rewrites)
        rules.extend(
            (rp.name, rp.expectation) for rp in (*self.request_body_redactions, *self.response_body_redactions)
        )
        return tuple(rules)


# endregion

# region: scrub-fire manifest (REC-006)

# Per-rule fire counts for the recorder's named-pattern audit. Counting is
# always on (a Counter increment per applied rule); the dump is gated on the
# manifest path so a normal test run writes nothing.
_SCRUB_MANIFEST_ENV = "_RS_SCRUB_MANIFEST"
_FIRE_COUNTS: Counter[str] = Counter()


def _record_fires(rule_name: str, fires: int) -> None:
    if fires:
        _FIRE_COUNTS[rule_name] += fires


def reset_scrub_fire_counts() -> None:
    """Clear the fire counters (test isolation)."""
    _FIRE_COUNTS.clear()


def scrub_fire_counts() -> dict[str, int]:
    """Snapshot of the per-rule fire counts accumulated so far."""
    return dict(_FIRE_COUNTS)


def dump_scrub_manifest() -> Path | None:
    """Write ``{rule_name: count}`` to the ``_RS_SCRUB_MANIFEST`` path.

    No-op (returns ``None``) unless the env var is set. Under xdist each
    worker writes its own ``<path>.<worker>`` file; the reader aggregates
    by glob. Called from the conformance conftest at session finish.
    """
    path_str = os.environ.get(_SCRUB_MANIFEST_ENV)
    if not path_str:
        return None
    worker = os.environ.get("PYTEST_XDIST_WORKER")
    path = Path(f"{path_str}.{worker}" if worker else path_str)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(_FIRE_COUNTS), sort_keys=True), encoding="utf-8")
    return path


# endregion

# region: generic vcr_config factory

# Wipes the whole query of a URL-valued response header. Value-based rather
# than an enumerated param list: the entire query of a pre-signed URL is
# token machinery, so a novel/undocumented param name must not survive on
# the strength of not being in a list.
_URL_QUERY_RE: re.Pattern[str] = re.compile(r"\?\S*")


def _compile_env(
    profile: CassetteProfile, live_values: Mapping[str, str | None] | None
) -> list[tuple[EnvRedact, re.Pattern[str], re.Pattern[bytes]]]:
    """Compile the active env-redacts against their resolved live values.

    ``None`` disables a rule (the resolver's documented signal — replay mode
    or no live creds configured). An empty string is not a disable signal:
    it is the shape of a misconfigured resolver, and silently skipping the
    scrub here would record unredacted, so it fails loud instead.
    """
    live_values = live_values or {}
    compiled: list[tuple[EnvRedact, re.Pattern[str], re.Pattern[bytes]]] = []
    for er in profile.env_redacts:
        value = live_values.get(er.name)
        if value is None:
            continue
        if not value:
            raise ValueError(
                f"env-redact {er.name!r} resolved to an empty string; "
                "a resolver signals 'rule disabled' by returning None"
            )
        source = "|".join(re.escape(form) for form in er.forms(value))
        flags = re.IGNORECASE if er.case_insensitive else 0
        compiled.append((er, re.compile(source, flags), re.compile(source.encode(), flags)))
    return compiled


def build_profile_vcr_config(
    profile: CassetteProfile,
    live_values: Mapping[str, str | None] | None = None,
) -> dict[str, Any]:
    """Build the ``vcr_config`` dict for *profile*.

    ``live_values`` maps each ``EnvRedact.name`` to its resolved live value
    (record mode — see ``CassetteProfile.resolve_live_values``) or is ``None``
    in replay mode, which deactivates every env-redact. The hooks below run
    in both modes — vcrpy normalises outgoing requests for cassette matching
    during replay too — so everything except the response hook must be
    deterministic without live values.

    Scrub order is fixed (REC-003): env-redacts first, then uri-rewrites
    (URIs and header values) and declared body redactions in declaration
    order. Native filters (``filter_headers``, ``filter_query_parameters``)
    are composed by vcrpy BEFORE the custom hooks (REC-005).
    """
    env = _compile_env(profile, live_values)
    presigned = profile.presigned
    url_headers = frozenset(h.lower() for h in profile.url_response_headers)
    rewrite_headers = frozenset(h.lower() for h in profile.rewrite_response_headers)

    def _env_str(value: str) -> str:
        for er, pattern, _ in env:
            value, fires = pattern.subn(er.fake, value)
            _record_fires(er.name, fires)
        return value

    def _env_bytes(raw: bytes) -> bytes:
        for er, _, pattern in env:
            raw, fires = pattern.subn(er.fake.encode(), raw)
            _record_fires(er.name, fires)
        return raw

    def _rewrite_str(value: str) -> str:
        value = _env_str(value)
        for uw in profile.uri_rewrites:
            value = uw.apply(value)
        return value

    def _scrub_body(body: Any, redactions: tuple[RedactPattern, ...]) -> Any:
        """Bytes-domain scrub with str round-trip (str in -> str out)."""
        if not isinstance(body, (str, bytes)):
            return body
        raw = body.encode() if isinstance(body, str) else body
        raw = _env_bytes(raw)
        for rp in redactions:
            raw = rp.apply(raw)
        return raw.decode() if isinstance(body, str) else raw

    def _scrub_url_value(value: str) -> str:
        """Scrub a URL-valued response header (``Location``)."""
        if presigned is not None and presigned.is_presigned(value):
            return presigned.placeholder
        value = _URL_QUERY_RE.sub("?REDACTED", value)
        return _rewrite_str(value)

    def _map_header_value(value: Any, fn: Callable[[str], str]) -> Any:
        if isinstance(value, list):
            return [fn(v) if isinstance(v, str) else v for v in value]
        return fn(value) if isinstance(value, str) else value

    def before_record_request(request: Any) -> Any:
        if presigned is not None and presigned.is_presigned(request.uri):
            # Nothing of a pre-signed URL survives: URI and Host header both
            # collapse to the placeholder. The body still gets the declared
            # redactions — an OAuth token exchange against an auth host
            # outside ``api_hosts`` lands in this branch too, and its
            # credential form fields must not record (a no-op on the usual
            # opaque upload-chunk body).
            request.uri = presigned.placeholder
            for key in list(request.headers):
                if key.lower() == "host":
                    request.headers[key] = presigned.placeholder_host
            body = getattr(request, "body", None)
            if body is not None:
                request.body = _scrub_body(body, profile.request_body_redactions)
            return request
        request.uri = _rewrite_str(request.uri)
        # Every request-header VALUE gets the same chain, so a live value
        # riding an unanticipated header (the X-AnchorMailbox class of leak)
        # is rewritten without per-header enumeration (REC-003).
        for key in list(request.headers):
            value = request.headers[key]
            if isinstance(value, str):
                rewritten = _rewrite_str(value)
                if rewritten != value:
                    request.headers[key] = rewritten
        body = getattr(request, "body", None)
        if body is not None:
            request.body = _scrub_body(body, profile.request_body_redactions)
        return request

    def before_record_response(response: dict[str, Any]) -> dict[str, Any]:
        headers = response.get("headers", {})
        for key in list(headers):
            lower = key.lower()
            if lower in profile.response_header_deletes:
                del headers[key]
            elif lower in url_headers:
                headers[key] = _map_header_value(headers[key], _scrub_url_value)
            elif lower in rewrite_headers:
                headers[key] = _map_header_value(headers[key], _rewrite_str)
        body = response.get("body", {})
        raw = body.get("string")
        if isinstance(raw, (str, bytes)):
            body["string"] = _scrub_body(raw, profile.response_body_redactions)
        return response

    config: dict[str, Any] = {
        # Decoded bodies keep cassettes diff-reviewable (TEST-009) and let
        # the body redactions run against plain text.
        "decode_compressed_response": profile.decode_compressed_response,
        "filter_headers": list(profile.filter_headers),
        "filter_query_parameters": list(profile.filter_query_parameters),
        "before_record_request": before_record_request,
        "before_record_response": before_record_response,
    }
    if profile.match_on is not None:
        config["match_on"] = list(profile.match_on)
    return config


# endregion


__all__ = [
    "FORBIDDEN_ENVELOPE",
    "CassetteProfile",
    "EnvRedact",
    "Expectation",
    "PresignedPolicy",
    "RedactPattern",
    "UriRewrite",
    "build_profile_vcr_config",
    "dump_scrub_manifest",
    "reset_scrub_fire_counts",
    "scrub_fire_counts",
]
