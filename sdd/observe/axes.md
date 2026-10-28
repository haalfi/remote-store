# Observation axes

<!-- doc: repo-only -->

The observation axes are the fixed checklist an `/observe` session walks for one entry of the operation catalogue: each axis forces the questions a category of the boundary contract demands, so coverage does not depend on the run. Each axis ends, per entry, in one of three states: **decided** (decision IDs recorded, including an axis an earlier decision already settles, which cites that decision), **explicitly open** (an open item with what blocks it), or **not applicable** with a one-line reason, only when the axis's question cannot arise for the entry. The session ends when no axis is in any other state (S4).

## Vocabulary

- **O1 caller**: the one issuing the call under design.
- **O2 concurrent caller**: another caller using the same API on the same store, overlapping in time.
- **O3 out-of-band actor**: changes the backing storage without going through the API.
- **Environment**: the one declared list of actions O2, O3 and the world may take, fault actions included. Axes reference it; they never restate it. It lives in the Environment section of the entry's record (`sdd/observe/records/<entry>.md`), rows `<entry>/E<n>`, drafted and decided when the doc is created; AX-7 checks it is complete, and a missing action is added there by a decision. Each entry keeps its own list until a shared one is admitted to the ground; the consistency check compares it with the lists of admitted entries.

**Non-commitment answers (F3).** Where a decision commits to no single outcome, it says so with a term, and the terms answer different questions. What the contract leaves open: *unspecified* (one of a stated set), *optional (MAY)*, *deliberately not promised* (goes to AX-14). Who fixes it: *profile-declared* (AX-15). What the caller can know: *indeterminate* (may or may not have taken effect; AX-12). Every such answer still names the observations it admits, so an observation outside them is a violation a check can catch; *undefined* is not allowed for that reason. A term is a decision; "not decided yet" is an open item, not a term.

**Facets, not boxes (F2).** A question that touches several categories, such as a failure while a handed-out resource is in use, has one home axis and cites the others.

## Axes

| ID | Axis | Category | Questions it forces | Normative form | Counterexample prompt |
|---|---|---|---|---|---|
| `AX-1` | Addressed structure | structure | What does the operation address, and which structural constraint must hold for it to be meaningful? Which parameters does it take, and, if it hands out an object, which methods does prior art give that object, per form (sync, async)? Each is decided or open, an invalid value included. | formula over one instant | an argument the structure rules out is accepted, or a valid one is rejected |
| `AX-2` | Pure values | value function | Which output values are a pure function of inputs alone? Is the map total, and what is its case split? | formula, or table row per case | the same inputs give different values, or a case falls in two rows or none |
| `AX-3` | Outcome partition | single call | For each pre-state class, what is the outcome: return value, post-state, or signalled failure? Is the partition complete and disjoint? | case table row: pre-state, outcome | an observed outcome outside its row's allowed set, or a pre-state with no row |
| `AX-4` | Frame | single call | What else may observably change when the call succeeds or fails? | formula: the unchanged set | a successful or failed call changes something outside the frame |
| `AX-5` | Termination | single call | Must the call return or fail, and under which environment assumption? Is the claim checked only by a timeout assumption? How does a caller impose their own deadline, and what does it cost a handed-out object? | formula naming its timeout assumption | the call neither returns nor fails within the stated bound while the environment is quiet |
| `AX-6` | Handed-out resource | resource life | Does the operation hand out an object that outlives the call? Which states does it have, and what does each operation do in each, including after close and after a failure? Is a failure raised again the same exception or a new one? | transition: state × operation cell | a cell's operation yields an outcome its cell does not allow, or a cell is empty |
| `AX-7` | Environment exposure | environment | Which declared environment actions can affect this operation, and between which of its steps? Does it need a fault action not yet declared? | reference to an environment table row | an environment action fired at an allowed point produces an outcome no clause admits |
| `AX-8` | Concurrent caller view | multi-observer guarantee | What may O1 observe given overlapping O2 calls? If the operation has an extent, is it one interval with one output or several partial outputs? | history predicate over interval operations | a recorded history with O2 that violates the predicate |
| `AX-9` | Out-of-band view | multi-observer guarantee | What may O1 observe given O3 changes before or during the call? Does O3 get the same rights as O2 or different ones? | history predicate over interval operations | a recorded history with O3 that violates the predicate |
| `AX-10` | Failure category | failures | Which category does the caller see for each failure, per pre-state and resource state? | table row: (state, category) | a failure surfaces with a category its row does not list, or as an untyped error |
| `AX-11` | Failure phase | failures | In which phase can each failure be reported: at the call, at a later use of a handed-out resource, at close? | table row: failure, phase | a failure reported in a phase its row excludes |
| `AX-12` | Effect after failure | failures | After each failure, what can the caller establish about the effect (none, complete, or indeterminate), and what may O2 or O3 observe of it, which may differ? | table cell, referencing AX-6 or AX-8 for temporal or multi-observer parts | an observer sees an effect state the failure's cell excludes |
| `AX-13` | Retry | failures | Could retrying repeat the failure, and does a retry after an indeterminate outcome change the result? Which guarantees of this operation does retry safety rest on (no mutation, same content, a condition the caller supplies)? | table column per failure | a retry produces an outcome the retry cell excludes |
| `AX-14` | Non-promises | non-promise register | Which observable properties (latency, request count, buffering, and the like) are deliberately not promised, with which scope? Only those a caller could plausibly infer from the operation's name or familiar prior art. | register row: ID, scope | a test explicitly asserts a registered non-promise |
| `AX-15` | Variation points | profile | Which claim's truth differs by backend, and what is its normal value? Which deviations exist, within which ordered range? Static or probed, and is a stronger guarantee requested by the caller (request or refuse)? | variation point row: normal value, declared deviations | a backend shows behaviour outside the normal value plus its declared deviations, or deviates undeclared |

Splits: single call into AX-3 to AX-5, because the report gives the frame and termination their own form and check (frame clause; timeout assumption). Multi-observer into AX-8 and AX-9, because whether O2 and O3 need different rights is an open question the report names. Failures into AX-10 to AX-13, one per F6 part.

## Per-question loop

Each question an axis raises becomes one decision in the entry's record (S5):

1. **Decision ID** (`<entry>/D<n>`, numbered in order, never reused) and the axis it answers.
2. **Scenario**: one concrete sequence of calls and environment actions that makes the question bite.
3. **Options**, each with its consequences for callers and backends.
4. **Recommendation**, with its reason and its source: a ground clause ID or a named prior-art reference, else marked `unsourced`.
5. **Asked**: per dialog that answered it, the question's opening words and the answer, quoted, so `/observe-review` can pair the two.
6. **Decision**: an option, or an F3 term.
7. **Consistency check** against earlier decisions and the ground (S1); conflicts named.
8. **Open items** it raises, as IDs of entries in the record's one Open items section.

## Sources

Drafted unprimed by an agent that read only the two sources below (research
§ 9 step 3, BK-485). The axes follow F2's provisional categories, so they are revisited
with F2 after the `read()` flow (research § 6).

`haalfi/research`, branch `research/black-box-boundary-spec`, `reports/Black box boundary spec methods.md`; `sdd/research/research-spec-first-reset.md` § 4 to § 6.

Refined after the draft from an unverified ChatGPT critique of F1 to F6, taking
only what holds within them (F2 facets; F3's admitted observations; AX-12 to
AX-14). The rest, F4 above all, is input to the format RFC and kept in the
[BK-485 dossier](../backlog/bk-485-spec-first-reset.md).

AX-1's parameters and handed-out methods, AX-5's caller deadline and AX-6's
re-raised failure were added by RFC-0028 P4 (BK-499), generalised from the
questions no axis raised in OP-01's session
([audit-025](../audits/audit-025-op-01-record-review.md) C7, G1 to G4).
