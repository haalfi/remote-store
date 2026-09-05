# Artifact Drift Rules
<!-- doc: dual dest=explanation/design/drift-rules.md -->

## Intent & Scope

THE source for how a mechanism that detects artifacts disagreeing with each
other is designed and reviewed — whether it compares two descriptions and fails,
or aggregates a drift signal and only reports. Applies whenever a change adds a
`check_*` gate, adds a non-gating drift report, adds a second description of
something already described, or sets how often a recurring check runs. The rules
below apply **in full** to each: a report is not a reduced-obligation category,
and Rule 5 already contemplates advisory checks. "Drift" here is artifacts
disagreeing with each other, not the storage-consistency sense used in the
library's own contracts.

Siblings: the [documentation framework](../CLAUDE.md#documentation-framework)
governs the documents themselves; [`CI-OPERATIONS.md`](CI-OPERATIONS.md) governs
operating a guard once built, and owns the guard-side surfaces rules 5, 6 and 9
touch.

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
   Which side governs is a decision, not a fact. Declare it in the document that
   owns the pair, next to the contract it arbitrates — [`000-process.md`
   Rules 3 and 7](000-process.md#rules), [`CLAUDE.md` principles](../CLAUDE.md#principles) and
   [`sdd/formal/README.md`](formal/README.md) each carry theirs. Do not restate
   them here: a second copy of a direction is a second thing to get backwards.

5. <a id="mandatory-path"></a>**Prefer the mandatory path; when a check is
   deliberately advisory, state why.** [review-enforced]
   Default a new check into `preflight`, `lint` or CI. Advisory checks are
   legitimate under the durable-TODO principle
   ([`CI-OPERATIONS.md`](CI-OPERATIONS.md#rules)); record the reason a check is
   not gating.

6. <a id="tolerated"></a>**Distinguish tolerated from unnoticed, structurally.**
   [review-enforced]
   Every accepted divergence gets a register entry with an owner and a rationale.
   An xfail entry, a `[~]` marker and a baseline allow-list are the usual forms;
   the list is not closed, so any durable home carrying both an owner and a
   rationale qualifies. A check with no such register will be switched off instead.

7. <a id="miss-rate"></a>**State the bound, and declare the subject, in the check
   itself.** [review-enforced]
   Document what the check does not catch. Where feasible, seed known
   discrepancies and report what fraction was caught. An unstated bound gets
   trusted past its range.
   Declare in the same docstring **what the mechanism compares** — the artifact
   pair, the rule when it guards a single artifact, or what it surfaces when it
   only measures — in the machine-readable `Drift-gate::` block that
   [`gen_gate_inventory.py`](../scripts/gen_gate_inventory.py) reads to derive
   [`GATE-INVENTORY.md`](GATE-INVENTORY.md). The declaration lives beside the
   code because a curated mapping of which mechanism watches which pair is the
   parallel artifact Rule 3 forbids, one layer up.
   **What enforcement reaches, stated because this rule is the one that asks for
   bounds:** wiring a script named `check_*`, `gen_*`, `drift_*` or `report_*`
   as a command without a block fails that gate. A mechanism named outside those
   prefixes **and** carrying no block passes silently — declaring is what puts a
   mechanism in the inventory, whatever it is called; the prefixes only decide
   what failing to declare costs. So the obligation is on the author, and the
   gate is a backstop for the conventional case rather than a guarantee of
   coverage. The generated inventory carries the full bound list, including the
   other ways a mechanism escapes.

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

# Rule 7: declare the subject, machine-readably, in the same docstring
# bad:  a row added by hand to an inventory of what checks what
# good: Drift-gate:: kind: pair / compares: A <-> B / domain: intent <-> verification
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
citations behind each rule as `S1`–`S9`, in the same order as the rules above.
