# `/rvw-pr`: the measuring pass

Read by a [`/rvw-pr`](SKILL.md) pass whose invoking prompt says **measuring**,
before its Step 1; every other rule of that file still binds. A pass without
that word does not read this file and runs none of it.

**Measuring pass.** If the invoking prompt says **measuring**, you reach your verdict by *executing*, not by reading, and Bash is opened to exactly this set:

- **Allowed, by name — this is an allowlist, not a pattern.** The composite gates `hatch run all` / `lint` / `preflight` / `docs-gate` / `typecheck` / `test*`; read-only `git` (`log`, `show`, `diff`, `status`, `rev-parse`, `blame`, and `worktree add`/`remove`/`prune` under `tmp/`); and `python` exercising the library — each prefixed with `-C <root>` (git) or `env -C <root>` (everything else, or its `python -c` equivalent where `env` lacks `-C`) when a review root is named ([`SKILL.md`](SKILL.md) § Review root), never a `cd`. Anything not on this list, do not run — "it looked read-only" is not a reason.
  **This bullet and the next two are the repo-wide safe set, not a `/rvw-pr` local rule.** They are facts about `pyproject.toml`, so [`/orchestrate`](../orchestrate/SKILL.md#reviewer-selection) binds its own measuring reviewer to them by reference even though that skill has no `measuring` keyword and no permission gate at all. Narrowing them is a change to both skills; the keyword above gates *when this file's reader may run things*, never *which commands are safe*.
- **The alias name does not tell you whether it writes**, which is why the list above is enumerated rather than derived. Two counterexamples, both live in `pyproject.toml`: `drift-check` carries the `-check` suffix but takes free-form args and reaches `refresh-baseline` (overwrites the committed `infra/drift-locks/<extra>.txt`) and `render-docs` without `--check` (overwrites a tracked docs page); `format` takes no args at all and rewrites source. A suffix rule and an args-shape rule are each false against one of these.
- **Write only under `tmp/`.** Not "only tracked files" — `/ship` requires a clean `git status --porcelain`, which reports an untracked file as `??` just as loudly. Exercising a *storage* library means writing files, so point every root, temp dir and worktree at the gitignored `tmp/` and the stated bound matches the enforced check. The bound binds under `/orchestrate` too, for a different reason stated there: its tree is uncommitted, so a stray write destroys the only copy rather than dirtying a pushed one. Same rule, two reasons — do not narrow it on the strength of either alone.
- **Never change the checked-out revision.** No `checkout`, `switch`, `stash`, `reset`, or `rebase`: `/ship` verifies an unchanged `HEAD` and a clean `git status --porcelain` before it trusts your pass, and moving either invalidates the whole round. To measure the **base** branch, use a worktree — and tear it down, because `worktree add` is not idempotent and the next round's measuring member runs the same command:

One Bash call per line — `&&`, `||` and `;` are forbidden by
[`CLAUDE.md` § Dev commands](../../../CLAUDE.md#dev-commands), and `$$` would
differ between calls because each is a new shell, so the path is a literal:

```bash
git worktree add tmp/base <base-ref>
```
```bash
# ... measure in tmp/base ...
```
```bash
git worktree remove tmp/base
```

If `worktree remove` fails on a stale entry, `git worktree prune` then retry.
Tear down even when the measurement failed. Without a root, one reviewer runs
at a time and a surviving `tmp/base` is what breaks the next round's
`worktree add`; under a root the path carries its commit and the next round
collides with nothing, but a leftover nested entry is what makes `/ship`'s
round-close `worktree remove` need its following `prune`, and a pass
re-spawned for the same commit would fail its own `worktree add` on it.
[`/orchestrate`](../orchestrate/SKILL.md#reviewer-selection) carries the same
three commands for a different reason — its reviewers run against *uncommitted*
work, so moving the revision would destroy what is under review rather than
invalidate a certified state. Edit both when the commands change.

Under a review root the recipe takes the same prefix on each of its commands,
and lands at `<path>/tmp/base`, gitignored there as here (measured: added from
inside a review worktree, it appeared at that path):

```bash
git -C <path> worktree add tmp/base <base-ref>
```
```bash
git -C <path> worktree remove tmp/base
```

Without a root, the three commands above stand as written.

**Running the gate is safe for `/ship`'s clean-tree check, and that was measured rather than assumed.** Two consecutive full `hatch run all` runs left `git status --porcelain` empty. **The invariant is that every output of `all` lands on a gitignored path** — not that its targets are check-only, which is false: `docs-build` writes the whole site, `examples` and `notebooks` execute scripts, `test-cov-s1` writes coverage data. Apply the gitignored-output test, not a check-only test, when asking whether a newly added `all` member is still safe to run here. This paragraph is the single home for that claim; `/ship` and ADR-0035 cite it rather than restating it.

Report what you **ran** and what came back, not what you concluded from reading. A finding you could not reproduce is reported as unreproduced.
