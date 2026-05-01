# ADR-0027: Single Bridge with Enforcement, Not Layered Mechanisms

## Status

Draft

## Context

The docs build has evolved by addition: each new content shape brought a
new bridge mechanism into the gen-files pipeline, and prior mechanisms
were kept. The shape recurs across [ADR-0006](0006-documentation-architecture.md),
[ADR-0007](0007-docs-src-literate-nav.md), and the BK-167 framework
landing — each step solved a real problem by introducing one more way
to put a repo file on the docs site, and none retired the previous way.

[Audit-012](../audits/audit-012-docs-structure.md) reports the structural
result: parallel mechanisms with no rule for which applies, link breakage
that the build does not catch, and an exclusion set that no single file
describes. The audit is the symptom inventory; this ADR addresses the
root cause.

[BK-167](../BACKLOG-DONE.md) wrote the rule
([`AUTHORING.md`](../AUTHORING.md) Rule 4: exactly one bridge applies)
but did not pick or enforce the mechanism, so the rule and the build
disagreed.

## Decision

Two coupled commitments: an architectural choice and the gate that
keeps it true. The recurring failure across the prior ADRs was not
that the chosen mechanism was wrong; each was reasonable for the case
that introduced it. The failure was that nothing prevented the next
mechanism from being added alongside. A decision to "use one bridge"
without a check that detects the second bridge degrades to a
preference. The architecture below is the choice; the gate (third
sub-decision) is what stops the preference from being negotiated away
on the next deadline.

Three sub-decisions follow: the bridge itself, the classification
mechanism (an aspect of the architecture, chosen so the bridge does
not need a parallel for special cases), and the gate.

### One bridge, by construction

`scripts/docs/scan.py:scan_dual_files` is the single source-discovery
function for dual content. `scripts/docs/render.py:render_dual_pages` is
the single render function. Other discovery and render helpers in the
docs pipeline are removed, not deprecated. New content shapes extend
this one mechanism; they do not add a parallel one. Contracts in
[spec 047](../specs/047-docs-framework-tooling.md) DOCFRAME-001,
DOCFRAME-005.

### Classification next to the file, not in a manifest

Each `.md` file declares its class on itself via an HTML-comment marker;
absence falls back to a directory-default rule or to `dual` (the safe
default named in [`AUTHORING.md`](../AUTHORING.md) Rule 1). A central
manifest is auditable but lives apart from the files it classifies, so
additions land in one place and the manifest in another. The marker
cannot drift from the file because it is part of the file. Contracts in
[spec 047](../specs/047-docs-framework-tooling.md) DOCFRAME-002.

### Enforcement at PR time

A check script (DOCFRAME-004) fails the build if any framework rule is
violated, including the "one bridge" rule itself. This is the half that
the prior ADRs left out. Without it, the next contributor under
deadline pressure adds the next mechanism and the cycle resumes.

## Consequences

- One discovery function, one render function. Reviewers can read the
  bridge end to end without crossing layers.
- Excluded files are auditable from the file itself plus the directory
  defaults; no central exclusion list is needed or permitted.
- Contributors learn one marker syntax. The cost is paid once per
  classified-non-default file.
- The docs build fails on link breakage, on Jinja in dual files, and on
  any return of a parallel bridge, in CI rather than in audit.

## Alternatives considered

**Keep parallel mechanisms, document the rule for which applies.**
Rejected: this is the state [`AUTHORING.md`](../AUTHORING.md) Rule 4
already forbids, and it is the state ADR-0006 → ADR-0007 → BK-167
arrived at by accumulation. Repeating it under a new label does not
change the dynamic.

**Central classification manifest.** Rejected: introduces a second
source of truth that drifts from the files, and recreates the audit
problem the marker resolves.

**YAML frontmatter instead of HTML comments.** Acceptable on substance;
deferred for cost. Frontmatter requires a YAML parser on the gate hot
path and a syntax convention on every classified file. The HTML comment
is parseable in regex and invisible in every Markdown renderer. If a
later need (e.g. structured per-page metadata) justifies frontmatter,
this ADR can be superseded.

**Move `sdd/` under `docs-src/design/`.** Rejected: the recurring
pattern is "add a mechanism to fit the path"; moving the path to fit
the mechanism is the same pattern with the arrow reversed. The bridge's
role is to adapt the build to canonical repo paths. Skills, agents, and
ripple-check entries treat `sdd/` as canonical.
