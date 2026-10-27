# Shared decisions

<!-- doc: repo-only -->

**Where a decision that binds every operation lives: one section per subject,
each defining its subject and naming the flow that fills it.** No section
holds a clause yet; a section gets one when the flow it names writes it, and
the clause joins the ground under RFC-0024 § R1, with that flow's spec and
model. An `/observe` session never writes here: it records such a decision in
its own record and lists it there under Open items with one tag, which the
flow after the session (research § 3: record, then spec) acts on:

- `shared: <section>`: that flow writes it into the section.
- `shared: <home>`, a home Lands elsewhere names: the session's own entry's
  flow writes it; a ground home receives it as a reopen, another entry's flow
  as an addition to that entry's input file, never as a direct write.
- `shared: unhomed`: that flow first gives it a home, a section or a row below.

Changing a filled section is a reopen
([RFC-0027](../rfcs/rfc-0027-observe-playground.md)).

## Session

Two kinds, never written bare as "session":

- **Design session:** one `/observe` session, which decides one catalogue
  entry with the maintainer and writes that entry's record.
- **Caller session:** the calls one caller makes through one handle.

Filled by: nothing; this section only fixes the words.

## Handle

The object through which a caller acts on one store: spec 053's Store and
AsyncStore. What a caller observes of a handle itself, apart from any one
entry's operations.

Filled by: OP-01's flow, the first to act through a handle. How a handle is
obtained, configured and spelled is the API spec's (BK-496).

## Lifetime

The span of a handle from the moment a caller holds it to the moment it can no
longer be used.

Filled by: OP-21's flow, which ends it.

## State

What a handle holds between calls that can change an operation's outcome.
Not the store's state, which is spec 051's.

Filled by: OP-01's flow; OP-21's flow adds what ending a lifetime does to it.

## Lands elsewhere

Decisions that bind every operation, or recur in every entry, whose home is not
a section above. Each was raised by RFC-0026 Open Question 1 (research note 7
of `research-operation-catalogue.md`) or by the first `/observe` run (BK-485's
dossier).

| Decision | Raised by | Home |
|---|---|---|
| `..` containment | RFC-0026 OQ1 | Spec 052 |
| Sync and async parity | RFC-0026 OQ1 | Spec 053 (OPS-002); that both forms behave alike, each entry's spec |
| A missing key on delete | RFC-0026 OQ1 | OP-10's flow |
| Exception typing: the failure categories a caller sees | RFC-0026 OQ1 | The error layer RFC-0024 D5 grows from OP-01's flow, which names its home; each entry's AX-10 |
| An unacceptable key refused identically by every operation | BK-485 (`exists`'s D2) | Spec 052 refuses it; the category the caller sees, the error layer above |
| Retry coupled to idempotency | RFC-0026 OQ1 | Each entry's AX-13 |
| An exception during a streamed write | RFC-0026 OQ1 | OP-03's flow |
| No silent drop of a condition | RFC-0026 OQ1 | OP-05's flow |
| No silent drop of an unsupported option | RFC-0026 OQ1 | OP-18's flow |
| How a caller learns a store's profile | BK-485 (`exists`'s open item) | OP-18's flow |
| A timeout bound | BK-485 (`exists`'s open item) | Each entry's AX-5; a bound shared by every operation, OP-01's flow |
