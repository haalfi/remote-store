# <NNN>: <Topic> Specification

## Overview

The core claim in at most three sentences: what this spec states, of which
kind of truth, about which subject. Then the scope, and what is out of scope
with the spec that owns it. Rules: [`SPEC-DESIGN.md`](../SPEC-DESIGN.md).

## Terms

Every symbol and term the sections use, including any word the repo also uses
in another sense.

---

## <PREFIX>-001: <First Invariant Title>

**Invariant:** One invariant, in one or two declarative sentences. Name the
observable outcome, not how an implementation reaches it.

## <PREFIX>-002: <Single-Call Section Title>

**Invariant:** ...

| State when the call runs | Result | Raises |
| --- | --- | --- |
| ... | ... | ... |

**See also:** the spec that owns a property this section relies on.

---

## Assumptions

What the spec relies on and cannot check itself, one line each, named so a
conformance test can cite it. An assumption several specs share is stated once,
in its owning environment spec, and linked from the others.

- **<Assumption name>:** what the system relies on from outside it.

## Notes

Not normative. Derived properties and the proofs behind them.

## Tested against

The reference model or suite the sections are checked against, named so a
reader can run it.
