# Artifact Drift Rules
<!-- doc: dual dest=explanation/design/drift-rules.md -->

## Intent & Scope

Rules for designing and reviewing a check that detects **drift between two
descriptions of the same thing** — spec against implementation, guide against
contract, generated surface against its source, one twin against the other.
Applies whenever a change adds a `check_*` gate, adds a second description of
something already described, or decides how often an existing check should run.

Scope note: "drift" here means *artifacts disagreeing with each other*, not the
storage-consistency sense used in the library's own contracts, and not only the
dependency drift that [`drift-guard.yml`](../.github/workflows/drift-guard.yml)
watches — that guard is one instance of Rule 9.

Companion to the documentation framework (see [`CLAUDE.md` § Documentation
framework](../CLAUDE.md#documentation-framework)), which governs how documents are
placed, shaped and kept accurate; this file governs how *checks between* them are
designed.

<a id="rules"></a>
## Rules

1. <a id="one-driver"></a>**Prefer one normative description driving N artifacts
   over N² pairwise checks.** [review-enforced]
   Drive every implementation from one shared suite rather than comparing
   implementations to each other. Reach for a pairwise parity assertion only when
   the two artifacts are genuinely two renderings for two audiences. Pairwise
   consistency does not compose: a green wall of parity checks licenses no
   conclusion about the artifact set as a whole.

2. <a id="localize"></a>**A check must localize, not merely fail.** [review-enforced]
   Report *which* element differs, not that a difference exists. "These two
   disagree" leaves the expensive half of the work to the reader, and is the
   quality bar a new gate has to clear before it is worth adding.

3. <a id="claim-space"></a>**Enumerate the claim space from a canonical artifact,
   and require an accounted-for result per claim.** [review-enforced]
   This is the only known defense against *omission* — a claim binding in one
   description and silently absent from another. It works only where the
   enumeration is **derived** from the authoritative artifact rather than
   maintained beside it, and it depends on stable identifiers. Its reach stops
   exactly where the enumeration's granularity stops.

4. <a id="authority"></a>**Declare the authority rule per artifact pair, in
   writing, before the check exists.** [review-enforced]
   Which side governs when they disagree is a decision, not a fact. Undeclared, a
   finding stalls indefinitely with detection complete and nobody able to act.
   Existing declarations: spec beats code ([`000-process.md` Rule 3](000-process.md#rules)),
   backlog beats history ([`CLAUDE.md` principle 5](../CLAUDE.md)), and the Dafny
   oracle beats the test ([`sdd/formal/README.md`](formal/README.md)).

5. <a id="mandatory-path"></a>**Put the detector on a path nobody can route
   around.** [review-enforced]
   A check that runs only when someone remembers is a check that stops running.
   If it is worth building it belongs in `preflight`, `lint` or CI; if it is not
   worth gating, question whether it is worth building. An excellent optional
   checker is plausibly worth less than a mediocre mandatory one.

6. <a id="tolerated"></a>**Distinguish tolerated from unnoticed, structurally.**
   [review-enforced]
   Known-and-accepted divergence needs a register with an owner and a rationale —
   an xfail entry, a `[~]` marker, a baseline allow-list. Without one, the only
   way to make a red gate green is to stop looking, and that is what teams do
   under schedule pressure.

7. <a id="miss-rate"></a>**State the bound, and estimate the miss rate.**
   [review-enforced]
   Every check has a blind spot that follows from its construction. Document it
   *in the check*, because an undocumented blind spot gets trusted outside its
   range. Where feasible, seed known discrepancies and measure what fraction is
   caught: findings are a numerator, and without a denominator "we ran it and
   found nothing" is uninterpretable.

8. <a id="independence"></a>**Verify independence of derivation path; never assume
   it.** [review-enforced]
   A second description is informative only if it was produced from different
   inputs. Independent *authors* do not produce independent *errors* — a
   specification that handles a case badly misleads everyone who reads it. When
   adding a second description, record what it was derived from, so a reviewer can
   see whether it is genuinely second.

9. <a id="period"></a>**Set the period from the drift rate, not the calendar.**
   [review-enforced]
   Inherited periods are fossils of what it used to cost to stop and look. Ask
   what a check's period would be if it were free, and anchor recurring checks to
   the events that can invalidate the artifact rather than to a date. Note the
   boundary: cost decides how often you look, never what is detectable.

## Guides

### Examples (bad → good)

```text
# Rule 1 — one driver, not N² pairs
# bad:  check_backend_a_vs_b.py, check_backend_a_vs_c.py, check_backend_b_vs_c.py
# good: one conformance suite parameterized over every backend

# Rule 2 — localize
# bad:  "capability sets differ between Python and Dafny"
# good: "CapSeekableRead present in Python, absent from Dafny CapabilityName arms"

# Rule 3 — derived enumeration, not a parallel list
# bad:  a hand-maintained checklist of things a backend must implement
# good: enumerate Backend.__abstractmethods__ and difference it against the guide

# Rule 7 — state the bound
# bad:  "verifies spec-to-test traceability"
# good: "verifies a marker citing the ID exists; does not verify the test asserts
#        the clause, is enabled, or cites the right ID"
```

### How the rules interact

Rules 3, 4 and 8 are **preconditions**: without a derived enumeration, a declared
authority rule, and genuine independence, the remaining rules produce checks that
are green for the wrong reasons. Rules 1, 2 and 7 govern a check's **design**.
Rules 5, 6 and 9 govern whether it **survives contact with a schedule** — the most
common way a working check stops working.

The recurring failure is treating "a standard requires it" or "we have a gate for
that" as evidence that a class of drift is covered. Rule 7 is the antidote: a
check whose bound is written down can be reasoned about, and one whose bound is
implicit will be trusted past it.

### Provenance

Derived from
[`sdd/research/research-inconsistency-detection-multi-artifact.md`](research/research-inconsistency-detection-multi-artifact.md)
§ 8, which carries the argument, the cross-discipline evidence, and the graded
citations behind each rule. This file states the rules; that document defends
them.
