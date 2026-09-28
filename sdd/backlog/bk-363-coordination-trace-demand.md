# BK-363 — Two coordination artefacts demand a trace the authority does not owe
<!-- doc: repo-only -->

Moved verbatim from [`BACKLOG.md` § 6](../BACKLOG.md#repo-does-not-mislead) by the ADR-0040 § 6
conversion, links re-based to this directory. The index entry holds the current
diagnosis; this file is evidence and advisory prescription
([§ Item authority](../BACKLOG.md#how-this-file-works)).

[`CLAUDE.md` § Trace authoring](../../CLAUDE.md#trace-authoring) owes a trace when
work *implements* an item or closes it by implementing it, and carves out an
item decided against, one absorbed, and a pure advisory annotation. Two
artefacts that route on the same rule are stricter than it.
- `.claude/skills/pr/SKILL.md` step 3 extracts `^([A-Z]+-\d+[a-z]?)[:\s]` from
  every commit subject and stops when any ID lacks `sdd/traces/<id>-*.yml`,
  with no exemption for an item that is *filed* rather than implemented. The
  commit filing BK-361 is subject-prefixed `BK-361:` per
  [§ Backlog](../../CLAUDE.md#backlog), so the gate would block a PR the authority
  says owes nothing.
- [`CLAUDE-REFERENCE.md`](../CLAUDE-REFERENCE.md) "Backlog item touched" carries
  the narrower form: it exempts only an item decided against or absorbed, and
  omits both the filed-without-implementation case and the advisory annotation.
**Same promise as BK-361, opposite polarity.** BK-361 is an authority asserting
what no mechanism checks; this is a mechanism enforcing more than the authority
asserts. Both make a coordination artefact say something untrue, which is what
this section is for.
**What it does not decide.** Whether the fix is an exemption in the gate keyed
on the diff containing no implementation, a convention that a filing commit
carries no ID prefix — which would contradict § Backlog — or an accepted
divergence registered under [`DRIFT-RULES.md` Rule 6](../DRIFT-RULES.md#tolerated).
The first is the only one that leaves both artefacts true.

## Correction, 2026-09-28

`/pr`'s step 3 no longer uses the quoted regex: `.claude/skills/pr/SKILL.md:27-46`
runs `check_backlog_ids_vs_base.py --print-subject-ids` and quotes the old
pattern only as the retired grammar. The demand holds and is wider: the gate
stops on any claimed ID with no `find sdd/traces -iname '<id>-*.yml'` match,
exempting nothing. The dependants are three, not two: both "Backlog item
touched" rows of `sdd/CLAUDE-REFERENCE.md` and `.claude/skills/fix-pr/SKILL.md`,
which relies on "The /pr trace gate guarantees it exists"
(`git grep -n -i -E 'find sdd/traces|trace gate' -- .claude sdd/CLAUDE-REFERENCE.md`).
Found by the ADR-0040 § 6 conversion.
