# BK-346 — The ripple-check table answers questions adjacent to the ones asked
<!-- doc: repo-only -->

Moved verbatim from [`BACKLOG.md` § 6](../BACKLOG.md#repo-does-not-mislead) by the ADR-0040 § 6
conversion, links re-based to this directory. The index entry holds the current
diagnosis; this file is evidence and advisory prescription
([§ Item authority](../BACKLOG.md#how-this-file-works)).

One class with **six** measured instances, not six items — counted from the
numbered list below, which is the only derivation this figure has. Each is a
reader who consulted the
[Pre-work index](../CLAUDE-REFERENCE.md#pre-work-index), got an answer, and acted
on it — and the answer was to a neighbouring question. Any row change lands in
**both** presentations; `check_ripple_parity.py` enforces trigger-parity, so a
row added to one and not the other fails `lint`.
**The open question is the shape of the fix**, not whether there is a defect:
N rows, N widened rows, or a note about the table's granularity. That question
is shared by instances **1 to 4**, which want a row and differ only in trigger.
**Instances 5 and 6 each carry a second disposition of their own**, stated in
place: 5's is deleting the restating copies rather than adding a row, and 6's
is that a gate over "an assertion went stale" is harder than it looks. So this
is one class with one shared question and two members that may not answer it
the same way — and instance 5's choice sets the effort for the group: S if it
goes one way, M the other, and `effort:` states the upper bound.
1. **New test file** asks whether the file needs an `os_sensitive` mark and is
   silent on placement, so nothing routes an author to TEST-003 when adding
   one. `check_test_placement.py` enforces three other rules and not this one.
   Two files landed mixing sync and async in one module; a round-1 reviewer
   caught it.
2. **Public method signature** answers for signatures. A spec clause can change
   what an operation *tolerates* without touching a signature, and then no row
   points from the clause to the ABC docstrings that define it — four of them
   said nothing about the new rule for seven rounds.
3. **CHANGELOG entry** says where a new entry goes and stops. It does not ask
   whether an *unreleased sibling* entry has been invalidated by the new one.
   One had been, by the same item, in the same section.
4. **Adding a `hatch` script alias** (was BK-334, absorbed here). No trigger covers adding an
   entry to `pyproject.toml`'s `[tool.hatch.envs.default.scripts]`. That edit
   decides whether a new `scripts/*.py` is reachable by anything — whether it
   joins `lint` / `preflight` / `docs-gate` / `all`, or is deliberately left
   out. It fires on every new script in `scripts/`, of which the repo has
   dozens and every one carries an alias. BK-330 reasoned to the right answer
   only via the adjacent cross-artifact row, which now covers drift reports and
   still says nothing about a `gen_*` or a `bench-*`.
5. **Widening an authority doc's scope** (was BK-337, absorbed here). There is a row for a
   **new** authoritative process doc, and one for an authority **direction**
   amended. Neither fires on the commonest amendment: an existing doc's scope
   or subject sentence widening, after which nothing finds the copies that
   restate that scope. Measured target set at filing — six live restating
   copies of one direction: `CLAUDE.md` § Drift checks, `sdd/CI-OPERATIONS.md`,
   `sdd/CLAUDE-REFERENCE.md` in both ripple presentations,
   `.claude/agents/sdd-expert.md` and `documentation-expert.md`, and
   `.claude/skills/rvw-pr/SKILL.md` and `audit/SKILL.md`. PR #944 widened
   `DRIFT-RULES.md`'s scope sentence and took four review rounds to find them
   all, being one copy short in three of those rounds. `check_ripple_parity.py`
   structurally cannot help — it enforces parity between the two ripple
   presentations, not between them and copies scattered through `.claude/**`.
   **This instance has a better second disposition:** delete the restatements
   and let each reader link to the doc that states its own scope, as
   `CLAUDE.md` § Drift checks already half-does. A row keeps N copies
   synchronised; deletion removes the synchronisation problem. The obstacle is
   that agent-facing files are read cold by a process that may not follow a
   link, which is the reasoning BK-329 recorded when it accepted the copies.
   **Choosing between the two is the first half of this item**, and it decides
   the effort for the whole group.
6. **Closing a backlog item** (was ID-248, absorbed here). The **Backlog item touched** row
   names the trace, the schema and the CHANGELOG-audience rule. It does not
   name the **inbound** references: other items, section preambles, and
   `BACKLOG-DONE.md` entries that cite the closing item by ID and assert
   something about its state. Measured from closing ID-238 in one PR — four
   instances, each carrying a claim the close falsified rather than a bare
   cross-reference; two caught by the author's grep, **two more only by
   review**, which is itself the measurement. The asserting kind is what makes
   this more than link rot: [principle 3](../../CLAUDE.md#principles) is violated
   the moment the item closes, and the stale sentence reads as current. One
   instance is a **distinct sub-shape**: not a stale assertion *about* the
   closed item, but a live citation *of* it whose referent the close destroyed
   — the rewrite into `BACKLOG-DONE.md` dropped the paragraph, so the ID
   resolved and the sentence around it pointed at nothing. That sub-shape sits
   between this row and ID-235's inbound-citation pass, because the ID keeps
   resolving while the target is gone; **decide which owns it when either is
   picked up.** Note a gate is harder than it looks: the defect is an assertion
   going stale, not a reference dangling, so ID-235's mechanism does not reach
   it, and the open question is whether the row can say anything more useful
   than "grep the ID and read every hit".
