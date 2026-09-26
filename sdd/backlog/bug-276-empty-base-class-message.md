# BUG-276 — A mapped error still reaches the caller with an empty message through five base-class arms
<!-- doc: repo-only -->

Moved verbatim from [`BACKLOG.md` § 1](../BACKLOG.md#predictable-failure) by the ADR-0040 § 1
pilot, links re-based to this directory. The index entry holds the current
diagnosis; this file is evidence and advisory prescription
([§ Item authority](../BACKLOG.md#how-this-file-works)).

**M, not S**, for the reason BUG-264 gave before the split: the arms need a
decision before a patch, and this item adds scope on top of that — five arms
across four files, a `_errors.py` change that moves what three S3 backends
report, and an unsettled placement question.
**AZ-025 is listed because this fix falsifies a clause there.** That spec
states as current behaviour that the Azure fall-through *can* render blank,
and `test_an_unmapped_exception_still_reaches_the_caller_blank` pins it. Both
go red when this lands, by design — they are the reminder to re-read the
clause, not collateral.
The remainder of BUG-264, which closed the `BackendUnavailable` half. ERR-009
is a claim about `str()` on *any* error, and the same construction spelled with
the base class stands at **7 sites in 5 files**:
`rg -n 'RemoteStoreError\(str\(exc\)' src/`. Line numbers are omitted; the
`rg` is the derivation.

**The construction is not the defect — the guard above each site is.** Five
sites can render blank and two cannot, each driven rather than read:

| Site | Driver | Result |
|---|---|---|
| `_azure_common` final fall-through | `RuntimeError()` | `RemoteStoreError('')` |
| `_s3_pyarrow` `OSError` arm | `OSError()` via `_pyarrow_errors` | `RemoteStoreError('')` |
| `_errors._classify_by_message` final arm | `RuntimeError()` | `RemoteStoreError('')` |
| `_sftp` errno fall-through | `OSError()` — **no args, no errno** | `RemoteStoreError('')` |
| `_sftp` final arm | `RuntimeError()` — non-`OSError`, non-paramiko | `RemoteStoreError('')` |
| `_azure_common` `HttpResponseError` arm | — | `"Operation returned an invalid status 'None'"` |
| `_s3_boto3` `ClientError` arm | — | `"An error occurred (Unknown) when calling…"` |

**The two SFTP arms need different drivers**, which is easy to miss: a bare
`OSError()` stops at the errno fall-through and never reaches the final arm,
and the final arm sits after the `paramiko.SSHException` check and carries
`# pragma: no cover`. **An errno-carrying `OSError` is not blank** —
`OSError(EIO, "")` formats `"[Errno 5] "` — so testing that arm with an errno
wrongly concludes it is already fine.

The last two rows are excluded from the work: `HttpResponseError.__init__`
substitutes for a falsy message, and `ClientError` always formats from a
template. Note that two of the five blank-reachable arms — `_errors.py`'s and
`_s3_pyarrow.py`'s, the pair the keyword guard sits above
(`rg -n 'name or service' src/`) — are the mirror image for
`BackendUnavailable`: that branch needs one of
`endpoint`/`connect`/`timeout`/`dns`/`name or service` and `""` has none, so
reading the guard concludes "safe" and running it finds the exit one line
below.

**What BUG-264 established, so it is not re-derived here.** Every
`BackendUnavailable` the library now constructs carries text: after that fix
`rg -n 'BackendUnavailable\(str\(exc\)' src/` returns **four** call sites
plus one docstring mention, and none of the four can render blank — two sit
behind the keyword guard above, and the two botocore arms are fed by classes
that always format. Every other backend prefixes literal text at every
construction. **The base class is the whole of what is left.**

**Which backends a caller meets it on**, counting observable `backend=` values
rather than modules, since that is what an `except` clause sees:
`azure`, `async-azure` (the twins share `classify_azure_error`), `sftp`, and
all three S3 backends. Driving `_classify_error(RuntimeError(), "delivery.csv")`:
`S3Backend` → `backend='s3'` and `S3PyArrowBackend` → `backend='s3-pyarrow'`
both inherit `_S3Base._classify_error`; `S3Boto3Backend` → `backend='s3-boto3'`
defines its own, whose final line calls the same helper. So `_s3_boto3`'s *own*
site is the unreachable `ClientError` one above and the backend still reaches a
blank, through `_errors.py`. **Six backend names, five arms, four files** —
the three counts differ and the item uses all three.

**Disposition — the decision is the work.** Either a blank `RemoteStoreError`
gets the synthesised fallback Azure's and SFTP's `BackendUnavailable` arms now
carry, or these fall-throughs are *classified* rather than passed through,
since each sits at the end of a dispatch that already failed to recognise the
exception. The second is the more invasive and the more interesting: an arm
that cannot name the failure may be admitting the dispatch above it is
incomplete. Decide once and apply to all five arms. The two unreachable sites
want no change — adding a fallback nothing can reach is invisible to the
coverage gate and reads later as a tested path.
**Fixing `_errors.py`'s arm changes what all three S3 backends report**, so it
needs its own test on the S3 side and not only where the arm lives.
**Placement is part of the decision:** `_errors.py`'s site is shared and the
other six are per-backend. BUG-264 put Azure's in `_azure_common` because both
twins classify through it; that is a precedent for the shape, not the
placement.

## Moved from the § 1 preamble

Verbatim from the section preamble the pilot removed; "this section" is § 1.
In the first chunk "the clause" is the Promise's third clause (the failure says
which failure it was). In the third, "That" is BUG-265's fix of SFTP's connect
path (a refused port and a DNS failure now raise `BackendUnavailable`; its
`BACKLOG-DONE.md` entry), the sentence the removed preamble put before it.

What is left of the clause is the
**base class**, at five blank-reachable arms in four files — including two in the
very `_map_exception` BK-359 rewrote, and one shared helper that puts all three
S3 backends behind it — which is BUG-276, whose disposition is the open question.

A promise clause honoured on one arm of one backend was the shape this
section exists to catch; that the count of arms outlived two items is why
BUG-276 is not the tidy one-line follow-up its ancestor was first filed as.

That is one backend's connect arm, not the clause — BUG-276 and
BUG-293 carry the rest, and all three are the same promise met at different
depths: an error with no message, an error re-typed to a weaker class, and an
error of the wrong class outright.
