# Artifact Drift Rules
<!-- doc: dual dest=explanation/design/drift-rules.md -->

## Intent & Scope

THE source for how a check that compares two descriptions of the same thing is
designed and reviewed. Applies whenever a change adds a `check_*` gate, adds a
second description of something already described, or sets how often a recurring
check runs.

"Drift" here means artifacts disagreeing with each other, not the
storage-consistency sense used in the library's own contracts, and not only the
dependency drift [`drift-guard.yml`](../.github/workflows/drift-guard.yml) watches.
Placement, shape and longevity of the documents themselves are governed by the
[documentation framework](../CLAUDE.md#documentation-framework).

<a id="rules"></a>
## Rules

1. <a id="one-driver"></a>**Prefer one normative description driving N artifacts
   over N² pairwise checks.** [review-enforced]
   Drive every implementation from one shared suite rather than comparing
   implementations to each other. Use a pairwise parity assertion only when the two
   artifacts are genuinely two renderings for two audiences. Pairwise consistency
   does not compose.

2. <a id="localize"></a>**A check must localize, not merely fail.** [review-enforced]
   Report *which* element differs, not that a difference exists. A gate that cannot
   name the differing element is not ready to add.

3. <a id="claim-space"></a>**Enumerate the claim space from a canonical artifact,
   and require an accounted-for result per claim.** [review-enforced]
   The enumeration must be **derived** from the authoritative artifact, not
   maintained beside it, and requires stable identifiers. State the granularity: the
   check reaches no further than the enumeration does.

4. <a id="authority"></a>**Declare the authority rule per artifact pair, in
   writing, before the check exists.** [review-enforced]
   Which side governs is a decision, not a fact. Declared so far: spec beats code
   ([`000-process.md` Rule 3](000-process.md#rules)), backlog beats history
   ([`CLAUDE.md` principle 5](../CLAUDE.md)), Dafny oracle beats test
   ([`sdd/formal/README.md`](formal/README.md)). Add the pair you introduce.

5. <a id="mandatory-path"></a>**Put the detector on a path nobody can route
   around.** [review-enforced]
   A new check belongs in `preflight`, `lint` or CI. If it is not worth gating,
   do not build it.

6. <a id="tolerated"></a>**Distinguish tolerated from unnoticed, structurally.**
   [review-enforced]
   Every accepted divergence gets a register entry with an owner and a rationale —
   an xfail entry, a `[~]` marker, a baseline allow-list. A check with no such
   register will be switched off instead.

7. <a id="miss-rate"></a>**State the bound, and estimate the miss rate.**
   [review-enforced]
   Document in the check itself what it does not catch. Where feasible, seed known
   discrepancies and report what fraction was caught. An unstated bound gets
   trusted past its range.

8. <a id="independence"></a>**Verify independence of derivation path; never assume
   it.** [review-enforced]
   When adding a second description, record what it was derived from. Independent
   authors do not produce independent errors.

9. <a id="period"></a>**Set the period from the drift rate, not the calendar.**
   [review-enforced]
   Anchor a recurring check to the events that can invalidate the artifact, not to
   a date. Cost decides how often you look, never what is detectable.

## Guides

### Examples (bad → good)

```text
# Rule 1: one driver, not N² pairs
# bad:  check_backend_a_vs_b.py, check_backend_a_vs_c.py, check_backend_b_vs_c.py
# good: one conformance suite parameterized over every backend

# Rule 2: localize
# bad:  "capability sets differ between Python and Dafny"
# good: "CapSeekableRead present in Python, absent from Dafny CapabilityName arms"

# Rule 3: derived enumeration, not a parallel list
# bad:  a hand-maintained checklist of things a backend must implement
# good: enumerate Backend.__abstractmethods__ and difference it against the guide

# Rule 7: state the bound
# bad:  "verifies spec-to-test traceability"
# good: "verifies a marker citing the ID exists; does not verify the test asserts
#        the clause, is enabled, or cites the right ID"
```

### How the rules interact

Rules 3, 4 and 8 are **preconditions**: without a derived enumeration, a declared
authority rule and genuine independence, the rest produce checks that pass for the
wrong reasons. Rules 1, 2 and 7 govern a check's **design**. Rules 5, 6 and 9
govern whether it **survives a schedule**.

### Provenance

Derived from
[`sdd/research/research-inconsistency-detection-multi-artifact.md`](research/research-inconsistency-detection-multi-artifact.md)
§ 8, which carries the argument, the cross-discipline evidence and the graded
citations behind each rule.
