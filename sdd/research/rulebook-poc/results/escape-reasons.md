# Arm-A escape reasons

<!-- doc: repo-only -->

Every escape recorded by the eight arm-A runs, with the reason the agent gave.
The `*.txt` result files carry `file :: section` pairs only; these are the third
field. Research doc § 6 rests on this evidence, so it is transcribed here rather
than summarised. Arm B is absent because every arm-B escape block is `NONE`.

Transcribed verbatim from the agent outputs, wrapped for width. `RULEBOOK` refers
to the artefact as tested, whose header called itself non-authoritative and
hand-compiled.

## Tally

Of the 8 arm-A runs, **5 cite the artefact's non-authoritative / hand-compiled
disclaimer** as a reason to escape: BK-171 run 1, BK-171 run 2, BK-167 run 1,
BUG-199 run 1, BUG-199 run 2. The other 3 escape on **condensation** instead
("condenses this to a link", "explicitly defers the table", "only summarises and
links out"). Both are refusals to rely on the digest; the stated grounds differ,
and § 6 is about the first group only.

## BK-167a run 1

- `sdd/AUTHORING.md :: Classification markers` — RULEBOOK 4a condenses this to a
  link; BK-167a implements exactly these marker forms and directory defaults, so
  the literal syntax and the default table are load-bearing, not paraphrasable.
- `sdd/000-process.md :: Feature-type Definition of Done` — RULEBOOK 1 links the
  exit-criteria checklist without reproducing it; this item is a bridge/adapter
  feature, so its DoD is the closing condition.
- `sdd/000-process.md :: Document types` — naming/lifecycle rules for the new
  spec 047 and ADR-0027; templates give shape but not the placement/numbering
  contract.
- `sdd/TESTING.md :: Test Subpackage Placement` — RULEBOOK 3 explicitly defers
  the table; new tests under `tests/scripts/` must land in the right subpackage
  or the lint rule fails.
- `sdd/DOCUMENTATION.md :: Content homes / Cross-linking requirements` —
  RULEBOOK 4b condenses both tables; `render.py` must emit destinations that
  match the documentation-vs-source-file link authority split.
- `sdd/traces/_schema.yml :: whole file` — trace authoring is mandatory before
  starting, and the schema is the source for step/outcome/audience fields;
  blocked because `sdd/traces/` is off-limits.

## BK-167a run 2

- `sdd/AUTHORING.md :: Rule 1 + Classification markers` — spec 047 DOCFRAME-002
  explicitly defers to AUTHORING.md as normative for marker syntax and defaults;
  the parser and G-01 cannot be implemented from the spec alone. RULEBOOK 4a only
  summarises and links out.
- `sdd/AUTHORING.md :: Rules 2, 3, 4, 5` — G-02, G-03, G-04, G-05 each assert an
  AUTHORING rule verbatim; the exact wording fixes each gate's pass/fail
  boundary.
- `sdd/DOCUMENTATION.md :: Rules 7, 8, 9` — G-06 and G-07 are defined as
  "DOCUMENTATION R7/R8"; DOCFRAME-007's required `_nav.yml` shape derives from
  R9.
- `sdd/CONTENT-RULES.md :: Rule 6` — G-03 must permit `--8<--` while rejecting
  Jinja/macros; the carve-out's exact scope lives here.
- `sdd/000-process.md :: Rules + Feature-type Definition of Done` — spec 047
  cites 000-process Rule 2 for the `@pytest.mark.spec` obligation; the
  bridge/adapter DoD checklist is the exit criteria for exactly this feature
  type.
- `sdd/DRIFT-RULES.md :: Rules` — G-01..G-07 is a new cross-artifact check
  family; the gate's failure-output/enumeration design is governed by these
  rules.
- `sdd/TESTING.md :: Rules + Test Subpackage Placement` — new gate/scanner tests
  land under `tests/scripts/`; placement table and quality rules bind them.
- `sdd/DESIGN.md :: Rules 1–4, 7, 9` — new modules must satisfy
  ruff/mypy-strict, module docstrings, PEP 604 signatures, Google docstrings.
- `sdd/traces/_schema.yml` and `sdd/traces/bk-167a-*.yml` — trace mandatory and
  must ship in the same PR; the schema is the authoring contract.
- `CONTRIBUTING.md :: Authoritative Document Format` — needed only to confirm
  spec 047 / ADR-0027 are outside that format's scope; low-priority escape.

## BK-171 run 1

- `sdd/AUTHORING.md :: Rule 3 + Rule 4 + Classification markers` — Rule 3's text
  is what carved out `docs-src/`; it must be reworded to a universal on-disk
  rule, and the marker/directory-default table is only *condensed* in RULEBOOK
  (**which is explicitly non-authoritative and hand-compiled**), so the exact
  normative wording cannot be edited from the digest.
- `sdd/traces/_schema.yml :: whole file` — trace authoring is mandatory for a
  backlog item and the trace must be created from the schema example before work
  starts; forbidden as answer key, so the trace cannot be authored to spec.
- `sdd/DOCUMENTATION.md :: Rule 4 Cross-linking requirements` — rewriting every
  docs-src link into on-disk repo paths changes what a rendered page links to;
  RULEBOOK § 4b condenses this rule and drops the table, so I cannot verify the
  migration keeps guide→API-reference/example links compliant.

## BK-171 run 2

- `sdd/AUTHORING.md :: Rules 3 and 4` — R3 is the normative rule whose docs-src
  carve-out BK-167b introduced; its wording is an edit target and I cannot
  confirm the exact current text from RULEBOOK's condensed copy (**RULEBOOK is
  explicitly non-authoritative and hand-compiled**).
- `sdd/AUTHORING.md :: Classification markers` — needed to confirm `docs-only` is
  still a live class after the carve-out is removed, and that removing the
  exemption does not orphan the class.
- `sdd/DOCUMENTATION.md :: § 4 Cross-linking requirements` — the 76 rewritten
  links change which presentation hosts each target; the table states whether a
  given target must point at ReadTheDocs `/stable/` or GitHub, and RULEBOOK
  condenses the table away.
- `sdd/TESTING.md :: Test Subpackage Placement` — new/changed tests land under
  `tests/scripts/`; the placement table is condensed out of RULEBOOK and
  `check-test-placement` is CI-enforced.
- `sdd/000-process.md :: Feature-type Definition of Done` — BK-171 is a
  contract-expanding gate change; the exit-criteria checklist is referenced but
  not reproduced in RULEBOOK.
- `sdd/CI-OPERATIONS.md :: rule 2` — if the collapsed `check-links` interface is
  referenced by a workflow header or runbook entry, all three layers must move
  together; I cannot verify which layers mention it.
- `sdd/traces/_schema.yml` and two `sdd/traces/*.yml` — trace mandatory; excluded
  as answer key.

## BK-167 run 1

- `sdd/AUTHORING.md :: Intent & Scope + Rules 1–2 + Classification markers` —
  need the placement rules and the marker/directory-default table to classify the
  entry-point doc and to state its scope boundary against the other two;
  **RULEBOOK § 4a is condensed and explicitly non-authoritative**.
- `sdd/DOCUMENTATION.md :: Intent & Scope + Rule 2 Content homes` — need the
  authoritative content-home table to decide whether an entry point is a new file
  or a section of an existing one.
- `sdd/CONTENT-RULES.md :: Rules 2 and 4` — an entry point that restates the
  three docs' rules is exactly the "reproduce an exhaustive list inline" / "one
  copy per fact" violation; need the verbatim rules before choosing pointer-only
  vs summary.
- `CONTRIBUTING.md :: Authoritative Document Format` — any new `sdd/` process doc
  must follow the fixed structure and the exclusions list; the ripple row names
  this section directly.
- `sdd/000-process.md :: Rules + Workflows` — confirm this is an operational item
  that skips the spec step, and whether a spec section ID is required.
- `sdd/DRIFT-RULES.md :: Rules 1, 4, 8` — the entry point becomes an Nth
  description of the same ordering; rules 1/4/8 govern whether that needs a check
  and which side is authoritative.
- `sdd/traces/_schema.yml :: schema + example` — trace mandatory and must be
  created before work starts; cannot open anything under `sdd/traces/`.

## BK-167 run 2

- `CONTRIBUTING.md :: Authoritative Document Format` — an entry-point doc in
  `sdd/` must obey the fixed Intent & Scope / Rules / Guides shape and the "no
  meta-commentary" exclusion; cannot confirm the skeleton without it.
- `sdd/AUTHORING.md :: Rules 1–3, Classification markers` — need the marker form
  and directory default to know whether the entry point is dual/repo-only and
  what `dest=` it takes (G-01).
- `sdd/DOCUMENTATION.md :: Content homes, Cross-linking requirements` — need the
  authoritative content-home row to decide whether the entry point is a new file
  or a section, and the minimum cross-links it owes.
- `sdd/CONTENT-RULES.md :: Rules 2, 4` — the whole risk of an ordered entry point
  is restating the three docs' rules; need the exact "one copy per fact" wording
  to bound what it may contain.
- `sdd/000-process.md :: Rules, Workflows` — confirm a docs/operational item
  skips SPEC→TEST and whether spec 047 needs a DOCFRAME clause.
- `sdd/DRIFT-RULES.md :: Rules 1, 4, 8` — the new index duplicates ordering held
  in CLAUDE.md, RULEBOOK § 4, and the agent FOUNDATION list; need the
  authority-declaration and derivation-path rules before adding it.
- `sdd/traces/_schema.yml :: example, audience` — trace authoring is mandatory
  for this item; the whole `sdd/traces/` tree is off-limits.
- `sdd/CI-OPERATIONS.md :: Rules 1–3` — only if the item adds or changes a
  gate/guard around the entry point; not needed if it stays editorial.

## BUG-199 run 1

- `sdd/000-process.md :: Rules 2/3/6 + Feature-type Definition of Done` —
  **RULEBOOK section 1 is a hand-compiled, self-declared non-authoritative
  digest**; the bug-fix pipeline and the "update the spec if the bug contradicts
  an invariant" clause are load-bearing here because AZ-024 already asserts the
  fixed behavior, so the spec is a candidate for correction.
- `sdd/TESTING.md :: Test Subpackage Placement + rules 4, 5, 6, 13` — RULEBOOK
  explicitly condenses placement to "a lookup table plus three
  `check-test-placement` lint rules" without the table; I need it to decide
  whether the failing test belongs in `test_live_hns.py`, `test_config.py`, or
  `conformance/`.
- `sdd/traces/_schema.yml` plus the BUG-198/199/213 lineage traces — trace
  authoring is mandatory before starting a backlog item, and the prior HNS marker
  bugs' traces would show which ripples that family already hit.

## BUG-199 run 2

- `sdd/000-process.md :: Rule 6 Workflows` — canonical BACKLOG → CHANGELOG →
  failing TEST → FIX → COMMIT ordering; **substituted `sdd/RULEBOOK.md` § 0,
  which self-declares non-authoritative and hand-compiled**.
- `sdd/TESTING.md :: Rules + Test Subpackage Placement` — needed to decide where
  a new regression test file/class belongs (the placement lookup table is
  condensed out of RULEBOOK § 3, so the digest cannot answer placement).
- `sdd/traces/_schema.yml :: schema + example` — trace authoring is mandatory
  once implementation starts; `sdd/traces/` is off-limits for this task.
- `sdd/traces/bug-199-*.yml :: whole file` — the prior trace is the natural
  duplicate-triage evidence and fix-shape reference; excluded as answer key.
- `sdd/DESIGN.md :: rules 4, 7, 11` — applies if code or tests change;
  **substituted RULEBOOK § 2, which is marked *(condensed)***.
