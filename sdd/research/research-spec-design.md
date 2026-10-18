# Research: How a spec should be designed (BK-457)

**Date:** 2026-10-18
**Backlog items:** BK-457
**Status:** Point-in-time record of one maintainer working session. The
proposal it led to is [RFC-0022](../rfcs/rfc-0022-how-specs-are-designed.md),
which is where the decisions live; this record holds the analysis behind them.
**Scope:** What makes a spec good, where one spec ends, which form and which
formal layer fit which kind of truth, worked on one operation: a streaming
read. Decision log: `sdd/decisions/6b9890d9-f718-508d-b861-aef8c0398c78.jsonl`.

**Method and its limit.** The session reasoned from [spec
051](../specs/051-store-tree.md), the README and `CLAUDE.md` only, on purpose:
the question was what a spec should be, not what the repo's specs are. Spec 003
was not read, so § 2 and § 7 restate ground that spec 003's BE-032 and BE-033
already cover in part; § 8 says where.

---

## 1. What made spec 051 good, and what did not

**Spec 051 holds up against its own obligation; its one defect was project
status inside the spec.** Its strengths: one invariant per section, each one
line; axioms (TREE-001 to TREE-008) apart from consequences (TREE-010 to
TREE-012), each consequence named with the lemma that proves it; a scope that
says what it leaves to other specs.

A first list of weaknesses did not survive the question *is this the spec's
obligation?*:

| Claimed weakness | Verdict | Whose it is |
| --- | --- | --- |
| Not tied to backends or operations | Stated scope, not a defect | Backend conformance and the operation specs |
| Static: no operations, no concurrency | Stated scope | Operation specs |
| Empty folders on flat backends | Not this spec's layer | Spec 003, BE-032 |
| Alphabet abstract, no length limits | Deliberate | The input layer (spec 004) |
| Exact name equality vs. coarser file systems | A stated choice with its price | — |
| Rationale is a frozen snapshot | Guards against drift | — |
| Proofs not checkable in a given session | The session's limit, not the spec's | — |

What remained: the layering paragraph carried time-bound status ("yet"), a
backlog ID, and spec 003's detail about flat backends. A backlog item points
to the spec it serves; a spec pointing back at the item goes stale when the
item closes and copies a relation the backlog already records. The sentence
worth keeping was what the sections are tested against. That fix shipped
beside this record.

## 2. One operation, walked

**Even the happy path of a read crosses many owners, and each step has its own
failure.** The plain read:

| # | Step | Owner | What can go wrong |
| --- | --- | --- | --- |
| 1 | Caller passes a key | Caller | Wrong type, empty |
| 2 | Validate the key | Store | `..`, leading or trailing `/`, `//`, control characters, length |
| 3 | Normalize (or not) | Store | Each rewrite creates an alias |
| 4 | Scope to the store root | Store | Escaping the root, nested scopes |
| 5 | Check the capability | Store | Backend cannot read |
| 6 | Hand the key to the backend | Store to backend | Whose key form is passed |
| 7 | Map the key to a native address | Driver | Encoding, reserved characters, case folding, length |
| 8 | Connect and authenticate | Driver | Network, expired token, throttling |
| 9 | Locate the entity | Kernel and driver | Missing, a folder, item and prefix both present, link |
| 10 | Open or fetch | Driver | Permission, concurrent replace, consistency, size |
| 11 | Translate native errors | Kernel | Unmapped, wrong type, credentials in the message |
| 12 | Return bytes or a stream | Backend to store | Who owns the stream |
| 13 | Return to the caller | Store | Fails mid-read, not closed, content changed since step 9 |

**A stream adds time: the handle outlives the call that opened it.** Steps 10
to 13 become a lifetime, and state appears (handle, position, the version seen
at open, the token in use):

| Step | Owner | What can go wrong |
| --- | --- | --- |
| Open the stream | Driver | Handle leaks if a later step raises |
| Wrap it | Store | Native errors escape from inside `read()` |
| Return it; the call ends | Store to caller | Ownership unclear |
| Read a chunk | Caller to driver | Drop, timeout, throttling; resume or fail |
| Content changes between chunks | Another writer | Torn read |
| Entity deleted or moved | Another writer | Continue, fail, or undefined, by backend |
| Seek or range read | Caller | Not seekable; position after an error |
| Credentials expire mid-read | Driver | Re-authenticate or fail |
| Caller idle | Caller | Server drops the connection; pool exhausted |
| Shared across threads or tasks | Caller | Not safe |
| End of stream | Driver | Truncation indistinguishable from the end |
| Close | Caller | Never, raises, twice |
| Store or backend closes first | Owner of the store | Orphaned handle |

## 3. The building blocks

**Ownership, state and time cross the components; they are not inside any
one.** The conceptual blocks the walk needed: caller; store (facade); key;
validator; scope; capabilities; backend contract; kernel (semantics shared by
backends); driver (native I/O); session (credentials, pool, its own lifetime);
transport (timeouts, retries); error model; stream; state carried by a stream;
consistency guard; lifecycle rules; observability. Each has a lifetime, from a
value with none (key) to one longer than any call (session, stream).

## 4. An external review, challenged

An external model proposed a spec per component, topology and lifecycle files,
Mermaid diagrams, contract tables and Gherkin scenarios. Its central diagnosis
held: prose that mandates internal algorithmic order is the pitfall. Two tests
follow from it for every sentence: could two different correct implementations
both satisfy it, and could a black-box test fail it?

| Proposal | Verdict |
| --- | --- |
| Let types enforce what types can (a key as a value, not a string) | Holds: an order that is impossible to bypass needs no prose |
| Pre, post and error contracts per boundary | Holds |
| States and allowed transitions instead of narrative | Holds |
| Shared contract tests unchanged across drivers; leak detectors | Holds |
| A spec per component, plus a topology file | Fails: the hard properties cross components, and the topology restates the component files |
| Diagrams and tables as the spec | Fails as illustration; holds for a lifecycle when closed-world and checked (below) |
| Gherkin scenarios as the spec | Fails: a scenario covers one case and an invariant all of them; Given and When invite step order |
| Several of its own rules (capture the version "at the exact moment", regex masking, "reverse order", a named design pattern) | Fail its own diagnosis: they prescribe how |

**A state diagram reconsidered.** The maintainer's objection held: for a
lifecycle a state diagram is clearer than any sequence of sentences. It can be
the source when three conditions hold: closed world (an undrawn transition is
forbidden), one source (no prose restating the arrows), and a check that parses
it and compares it with the model.

## 5. Proof instead of review

**Formal layers fit kinds of truth, and each needs a bridge to the code or it
proves only a model.**

| Part of the flow | Property | Tool |
| --- | --- | --- |
| Validator | Accepts exactly the keys spec 051 admits; no two inputs map to one key | Dafny |
| Scope | Never escapes the root; nested scopes compose | Dafny |
| Capability gate | No driver call for an undeclared capability | Dafny or tests |
| Error model | Total mapping | Dafny; "no secret in a message" stays a test |
| Stream lifecycle | Closed once, no read after close, one owner | TLA+ |
| Concurrent writer | One version or a fault, where the backend can tell | TLA+ with an environment model |
| Close order | No orphan, a defined result for every order | TLA+ |
| Retry and resume | Terminates; no duplicated or skipped bytes | TLA+ (liveness) |
| Native I/O | — | Contract tests only |

Bridges: a Python twin checked for parity, or the compiled oracle (Dafny);
tests derived from the model's states, or recorded runs replayed against it
(TLA+); what a backend guarantees natively written as an explicit assumption
that conformance tests check per backend. Review then moves from "is the
behaviour right?" to "is this the right property, and are the assumptions
realistic?".

## 6. What makes a spec good

| Property | Means | Checked by |
| --- | --- | --- |
| Well founded | Every clause has a traceable reason | Axioms apart from consequences; a countermodel per axiom |
| Verifiable | Every clause can fail | The two tests of § 4 |
| Lasting | True without edits as the project moves | The six-month test; links point at the spec |
| Correct | Says what the system must do, and it can | Proof or model check; contract tests |
| Free of contradictions | No two clauses or neighbouring specs disagree | One home per fact; the model has an instance |
| No unstated gaps | Whatever is open is declared open | Scope and non-scope; closed world; assumptions |
| Placed | Covers only its own layer | § 1's defect |
| Comprehensible | Leads with its claim, in the form its content needs | Rule 7; § 4's diagram |

## 7. The streaming read, split

**Split where the kind of truth changes.**

| Spec | Subject | Kind | Authority |
| --- | --- | --- | --- |
| Store tree | What a key denotes | Structure | Alloy and Lean (spec 051) |
| Key admission | Input to key, or rejected | Function | Dafny |
| Scope | Store-relative key to backend key | Function | Dafny |
| Read contract | One `read(k)` at the moment it opens | Single call | Dafny and contract tests |
| Stream lifecycle | A handle from open to close | Lifetime | TLA+ |
| Read consistency | Open stream and a concurrent writer | Lifetime and environment | TLA+ with assumptions |
| Error model | Native failure to library error | Function | Dafny and tests |
| Session and transport | Retry, resume, timeout | Liveness | TLA+ |

Each takes spec 051's skeleton: overview (claim and scope), terms, one
invariant per section, assumptions where the environment matters, notes for
derived properties, tested against.

**Decided in the session:** key admission rejects non-canonical input rather
than normalizing it; the stream lifecycle comes first.

## 8. A lifecycle drafted

States Open, Faulted, Closed; owners backend, store, caller. Transitions:
open to Open; read keeps Open; fault or session close moves Open to Faulted;
close moves Open or Faulted to Closed; close on Closed is a no-op. Invariants
drafted: one state at a time; only the drawn transitions; Closed terminal; one
owner, handed only backend to store to caller; an owner that cannot hand over
closes; resources released once, on entering Closed; Faulted and Closed deliver
no bytes; a session close faults its open streams and the owner still closes
them; position never decreases. Not guaranteed: that a caller ever closes.

**Decided in the session:** a second close is a no-op; a session close faults
its open streams.

**Overlap.** Spec 003's BE-033 already states a lifecycle-scoped interaction
protocol (ownership, transitions, cancellation), and BK-454 and BK-455 hold the
read handle and the `Session` state set. This draft was made without reading
them; reconciling it is their work, and RFC-0022 uses it only as an
illustration.
