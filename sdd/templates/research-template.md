# Research: <Topic> (<Backlog-ID>)

**Date:** YYYY-MM-DD
**Backlog items:** <ID> (<Brief title>)
**Status:** Research complete — ready for design decisions | In progress

<!-- The **Date:** line above is load-bearing: it fills the "Date (as of)"
     column of the published research index and orders it newest first. Keep
     the exact `**Date:** YYYY-MM-DD` spelling, in the header (above the first
     `---` rule); `hatch run check-sdd-index` rejects a doc without it. -->


---

## 1. Problem Statement

Describe the problem this research addresses. Include:

- The current limitation and who is affected.
- Relevant constraints from existing specs, ADRs, or DESIGN.md.
- The decision this research is meant to inform.

---

## 2. Survey: <Landscape / Options / Prior Art>

### 2.1 <Option or approach A>

**Pattern:** What is the core idea?

**How it works:** Mechanism in enough detail to evaluate it.

**Trade-offs:**
- Pro: ...
- Con: ...

### 2.2 <Option or approach B>

...

---

## 3. Evaluation

Side-by-side comparison or scoring of the options against the constraints.

| Criterion | Option A | Option B |
|-----------|----------|----------|
| ...       | ...      | ...      |

---

## 4. Recommendation

State the recommended direction and the key reason. Include any preconditions
or open questions that must be resolved before implementation.
