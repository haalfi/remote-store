# Pre-registration — rulebook usefulness replay
<!-- doc: repo-only -->

Written before any agent was launched. Results must be read against this, not
against a story assembled afterwards.

## Question

Does `sdd/RULEBOOK.md` let an agent identify the gates a real item needed,
without opening the source process docs?

## Method

Trace replay. Each agent gets only the `trigger` field of a completed item's
trace and must output the ordered gate list it would satisfy. Scored against
that trace's recorded `read_type: gate` steps. Agents are forbidden from reading
`sdd/traces/` (that is the answer key).

Items: BK-167a (9/9 gates in rulebook scope), BK-171 (9/10), BK-167 (8/8),
BUG-199 (6/26, the ceiling case).

- **Arm A**: may read `sdd/RULEBOOK.md`; may not open the eight compiled `sdd/`
  process docs or `CONTRIBUTING.md`. Wanting one is recorded as an *escape*.
- **Arm B**: may read the source docs; may not open `sdd/RULEBOOK.md`.

Both arms may read specs, code, tests, and `BACKLOG.md`.

2 runs per arm per item = 16 agents. Deviation from the 3 runs proposed
earlier, for cost; noted so the variance claim stays honest.

### Known confound

`CLAUDE.md` is auto-injected into every subagent as project instructions and
cannot be withheld. Both arms therefore have it free. The experiment measures
what `RULEBOOK.md` adds *on top of* `CLAUDE.md` versus following `CLAUDE.md`'s
pointers to the sources. That is the real-world question, but it means section 0
of the rulebook is not under test.

## Hypotheses

- **H1** Arm A recall on in-scope gates >= Arm B.
- **H2** Arm A escapes concentrate in the `*(condensed)*` sections (DESIGN,
  DOCUMENTATION) and table-bodied rules.
- **H3** The 20% in-scope ceiling is hard: Arm A cannot reach out-of-scope gates.
  Predicted FALSE. The rulebook's pointer lines should route agents to
  `BACKLOG.md`, specs, and the ripple-check without carrying those rules. If so,
  its value is **routing, not substitution**, and the next version should carry
  more pointers and fewer copied rules.
- **H4** (added after reading ground truth, before launch) Recall will be
  depressed by gates citing `## Guides` sections. BK-167a cites `000-process.md
  :: Spec format`, `:: Document types`, `:: Test traceability` and `TESTING.md ::
  Test Subpackage Placement` as gates; all are Guides content, dropped from the
  rulebook by the compilation convention. If this dominates the misses, the
  "rules only" premise of the digest is itself wrong: gates live in Guides too.

## Decision rule

- H1 false + high escape rate -> the rulebook is overhead; abandon.
- H1 true + low escape rate -> substitution works; build the generator.
- H3 false -> reframe as an index; next version is pointers, not copied rules.
- H4 true -> compile `## Guides` gate-bearing sections too, or stop calling it a
  rulebook.
