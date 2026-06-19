# Spec 049 — Live Recording Architecture

**Scope:** Test infrastructure. Specifies the HTTP cassette *recording
transport*: the backend-agnostic scrub core, the per-backend cassette
profiles, the pre-signed URL policy, and the scrub audit gates that make
recording against real cloud accounts safe. Not library source code.
The contracts here govern `tests/backends/fixtures/_cassettes*.py`, the
cassette wiring in `tests/backends/conformance/conftest.py`, and
`scripts/record_cassettes.py`.

**Prefix:** `REC`

**Companion docs:** [Spec 048](048-testing-architecture.md) governs the
fixture model and the cassette/replay *contract* (TEST-007 — what a replay
fixture promises); this spec governs the recording *mechanism* TEST-007
deliberately deferred. [`sdd/TESTING.md`](../TESTING.md) quality rules
apply to the tests tracing these clauses.

**Related decisions:**
[ADR-0028](../adrs/0028-testing-architecture-kind-stage-replay.md) records
the kind/stage axes and the HTTP-only replay demotion this layer
implements. The recording layer's own design rationale is carried inline
in the clauses below; it is test tooling beneath ADR-0028, not a separate
architecture decision.

**Tracks:** BK-284 (the redesign that introduced the profile core),
building on the scrub hardening from BK-262.

---

## REC-001: Backend-Agnostic Recording Core

**Invariant:** One shared module holds the recording machinery — the
declarative rule shapes, the cassette-profile dataclass, and the single
generic `vcr_config` factory. It contains no backend-specific constants,
helpers, or hooks. Everything one backend family declares about its
cassettes lives in that family's profile module as one `CassetteProfile`.

**Postcondition:** A third HTTP backend gains recording, replay routing,
and the audit gates by writing a profile module and registering it
(REC-007) — without editing the core, the conformance conftest, or the
recorder's verification steps.

**Rationale:** The previous shape — parallel hand-rolled
`before_record_*` stacks per backend — duplicated bytes/str dispatch,
header-value handling, and live-value threading per family, and every
scrub guarantee lived only in code. Profiles make the guarantees
declarations the audit (REC-006) can enumerate.

---

## REC-002: Named Redaction Rules

**Invariant:** Every body, URI, and live-value scrub is a named rule — a
`RedactPattern` (bytes-domain body redaction), `UriRewrite` (str-domain
URI/header rewrite), or `EnvRedact` (live-value redaction) — carrying an
audit identity prefixed with its backend family (`graph.body.download-url`
style) and a declared expectation: `required-to-fire` or `opportunistic`.

A `required-to-fire` rule must redact at least once over a full-slice
recording: zero fires means the scrub layer silently stopped seeing the
value it owns. An `opportunistic` rule guards a shape a normal recording
may legitimately never produce. Exact counts never gate — they are
workload-dependent.

**Postcondition:** The audit gate (REC-006) asserts by rule name; a rule
cannot exist without an audit identity, and an identity cannot drift from
the pattern it names.

---

## REC-003: Live-Value Coverage

**Invariant:** A declared live value (`EnvRedact`) is redacted wherever
the service can echo it: the request URI, every request-header value
(no per-header enumeration — a value riding an unanticipated header is
still rewritten), the request body, and the response body — bytes and
str domains alike, case-insensitively when declared, and in every
declared `forms` variant (a service may echo a value reshaped: the Graph
drive cid appears both contiguous and hyphen-split inside an MSAL `Oid:`
anchor).

The scrub order is fixed: env-redacts first, then uri-rewrites and body
redactions in declaration order. Resolution happens only in record mode;
in replay mode every env-redact is inactive and the remaining hooks are
deterministic, because vcrpy runs the request hook in both modes to
normalise outgoing requests for cassette matching.

**Rationale:** The header-value half exists because a live value once rode
a request header no scrub list anticipated; per-header enumeration is
exactly the failure mode this clause forbids.

---

## REC-004: Pre-Signed Round-Trip Consistency

**Invariant:** For a profile declaring a `PresignedPolicy`, every
pre-signed URL — request URIs to non-API hosts, `Location` /
`Content-Location` response headers, and URL-valued body fields — rewrites
to the *same, valid-URL* placeholder. The request hook runs in record and
replay mode alike, so the request a backend re-issues from a scrubbed
body or header normalises to the value the recorded request was rewritten
to, and vcrpy matches them.

The placeholder must be a well-formed, non-routable URL. The
counter-example this clause forbids: replacing the value with a bare
token — the backend reads it back and issues a request that matches
nothing, which is exactly how Graph reads failed to replay before the
placeholder.

**Consequence:** Replay of pre-signed traffic is order-dependent — every
pre-signed interaction in a cassette collapses to one method+URI and
vcrpy disambiguates solely by recorded order. Concurrent pre-signed
requests within a single test are unsupported under replay.

---

## REC-005: Native-Filter Half and Its Defence Boundary

**Invariant:** Request-header deletes and the User-Agent rewrite run
through vcrpy's native `filter_headers`, declared on the profile. vcrpy
composes the native filters *before* the custom hooks in both modes,
matches header names case-insensitively, and re-inserts a rewritten
header under the declared key's case — so the declared case must match
what cassettes record. The tuple form rewrites a *present* header and
never adds one when absent; re-record byte-identity rests on that.

The native half never touches a named rule and is therefore invisible to
the named-rule audit; its defence is the forbidden-pattern envelope
(REC-006) plus per-PR cassette diff review. Neither half may be assumed
to cover the other.

`filter_post_data_parameters` is excluded from the native half: vcrpy's
implementation is POST-only and re-serialises every `application/json`
body even when no parameter matches, churning the security-review diff on
re-record. The OAuth credential-form scrub therefore stays in the
declarative half as named `RedactPattern`s — which also makes it
audit-visible. Revisit only if vcrpy gains a non-rewriting filter.

---

## REC-006: Scrub Audit Gate

**Invariant:** Two independent gates verify every recording, fed by the
same profile declarations:

1. **Forbidden-pattern byte-scan** (env-independent). A module-level
   `FORBIDDEN_ENVELOPE` of universal leak markers — credential forms,
   token shapes, account PII — that every profile inherits, plus
   per-profile additions, combined by `all_forbidden_patterns()`. Two
   consumers run the identical set: the recorder's scrub-verify step on
   the live path, and a creds-free CI sweep over every registered
   profile's *committed* cassette tree — so a hand edit, bad merge, or
   mis-configured re-record is caught in CI, not by a manual grep.
2. **Named-rule audit** (full recordings only). The scrub core counts
   each named rule's fires; the conformance session dumps the counts to a
   manifest when the recorder exports the manifest path, and the
   recorder's verify step fails any `required-to-fire` rule at zero.
   Verify-only and single-cassette runs skip this half — fire counts are
   workload-dependent — while the byte-scan half always runs.

**Postcondition:** A scrub regression surfaces as a named rule at zero or
a forbidden marker hit *before* the cassettes can be committed, and a
leak that slips past recording is still caught by the CI sweep.

---

## REC-007: Per-Backend Extension Contract

**Invariant:** Registering a fixture with `cassette_profile=<PROFILE>`
(a field on the fixture registry record, TEST-004) is the *single
registration act*. The profile declares the family's cassette directory,
the fixture-id → canonical-cassette-suffix aliases (live and replay ids
collapse to one shared cassette file), the native filters, the named
redaction rules, the optional pre-signed policy, the forbidden-pattern
additions, and the optional vcrpy matcher override.

In return the core provides: cassette-directory routing, cassette-name
normalisation, the missing-cassette skip (TEST-007), the scrub config,
and inclusion in both audit gates (REC-006). There is no second
registration point; the one cross-check — a profile-bearing fixture must
appear in its profile's aliases — fails loud at routing-map build, and a
vcr-marked test whose fixture carries no profile fails loud rather than
falling back. Fixtures without a profile are invisible to all cassette
machinery.

**Profile routing is independent of conformance enumeration.** A fixture
carrying a profile routes, scrubs, and records regardless of whether it
participates in the conformance walk. A per-backend HTTP *deviation* suite
(TEST-003) therefore shares its family's profile and cassette directory while
staying out of conformance via the `conformance_excluded` registry flag — it
adds its live and replay fixture ids to the profile's aliases (under a distinct
canonical suffix) and the recorder records its tree alongside the conformance
tree in one run. Example: the Azure HNS suite's `azure_live_hns` /
`azure_replay_hns` pair (BK-303).

---

## REC-008: Async-Transport Capture

**Invariant:** What vcrpy can capture per async HTTP stack is pinned, not
assumed:

- **httpx** (the Graph backend): vcrpy patches `httpx.AsyncClient`
  directly, including `stream()` — no transport shim. Proven by the
  streaming record-then-replay-offline test in the fixtures package.
- **aiohttp via azure.core** (the async Azure backend): vcrpy's aiohttp
  stub drops streamed bodies on record and deadlocks on replay, so the
  async Azure fixtures inject `AsyncioRequestsTransport` (requests/urllib3
  in a thread pool) through the backend's existing `client_options` —
  production code unchanged. The live fixture injects it only while
  recording (the runner exports `_RS_CASSETTE_RECORDING=1`); the replay
  fixture always uses it.

**Fidelity caveat:** under the shim, defects living purely in
`AioHttpTransport` itself are invisible to replay; the live Stage-3
fixture remains the source of truth for that layer.
