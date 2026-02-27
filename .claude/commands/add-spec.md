# Add Spec — Create a New Specification with Test Scaffolding

You are creating a new specification for the remote-store project following
the SDD (Spec-Driven Development) process. This skill generates the spec
document and matching test scaffolding.

## Arguments

The user should provide:
- **Topic** (e.g., `glob-strategy`, `async-api`, `retry-policy`)
- **ID prefix** (e.g., `GLOB`, `ASYNC`, `RTR`) — used for section IDs
- **Brief description** of what the spec covers

If not provided, ask the user for these values.

## Step 1: Determine the spec number

Check existing specs in `sdd/specs/` to find the next available number:
```
ls sdd/specs/
```
The new spec gets the next sequential NNN. Current specs go up to 015
(013 memory-backend, 014 pyarrow-filesystem-adapter, 015 store-child),
so the next available is 016 or higher. Always verify with `ls`.

## Step 2: Create the spec document

Create `sdd/specs/NNN-<topic>.md` using this format:

```markdown
# <Topic> Specification

## Overview

<One-paragraph purpose statement explaining what this spec defines and why.>

## <PREFIX>-001: <First Rule Title>

**Invariant:** <what must always be true>

**Preconditions:** <what the caller must ensure>

**Postconditions:** <what the callee guarantees>

**Raises:** <error conditions, referencing ERR-NNN types>

**Example:**
```python
<short code example demonstrating the rule>
```

## <PREFIX>-002: <Second Rule Title>
...
```

Guidelines for writing spec sections:
- Each section defines ONE testable rule or invariant
- Section IDs are sequential and never reused: `PREFIX-001`, `PREFIX-002`, ...
- Use existing specs as reference for depth and style
- Reference existing error types from `sdd/specs/005-error-model.md`
- Reference existing capabilities from `sdd/specs/003-backend-adapter-contract.md`
- Be precise about edge cases — ambiguous specs lead to ambiguous implementations

## Step 3: Create test scaffolding

Create or update the appropriate test file with spec-traced test stubs:

```python
"""Tests for <topic> specification."""
from __future__ import annotations

import pytest


class Test<TopicCamelCase>:
    """<PREFIX>-001 through <PREFIX>-NNN: <description>."""

    @pytest.mark.spec("<PREFIX>-001")
    def test_<first_rule_snake_case>(self) -> None:
        """<PREFIX>-001: <rule title>."""
        ...  # TODO: implement

    @pytest.mark.spec("<PREFIX>-002")
    def test_<second_rule_snake_case>(self) -> None:
        """<PREFIX>-002: <rule title>."""
        ...  # TODO: implement
```

Every spec section MUST have at least one test stub. This is a hard rule from
`sdd/000-process.md`: "No spec without tests."

## Step 4: Register the spec prefix

Update `sdd/000-process.md` to add the new prefix to the ID Prefixes table:

```markdown
| `PREFIX` | <Module> | `NNN-<topic>.md` |
```

Also update `CONTRIBUTING.md` Spec Format section if it lists prefixes.

## Step 5: Update BACKLOG.md

If this spec relates to a backlog item:
- Link the spec in the backlog item description: `→ Spec: sdd/specs/NNN-<topic>.md`
- Update the item status to `[~]` if the spec is the first step

If this is new work not in the backlog:
- Add a new backlog item in the appropriate tier

## Step 6: Verify

- Confirm the spec file follows the format of existing specs
- Confirm every spec section has a matching test stub
- Confirm the prefix is registered in `000-process.md`
- Confirm the backlog references the spec

## Important

- "No code without a spec" is Rule 1 of SDD. This skill ensures the spec
  exists BEFORE implementation begins.
- Spec section IDs are stable and immutable. Once assigned, an ID never
  changes meaning. If a section is deprecated, mark it `[DEPRECATED]`.
- The SDD pipeline is: Spec -> Test -> Implement -> Validate. This skill
  handles Spec + Test scaffolding. Implementation comes after.
