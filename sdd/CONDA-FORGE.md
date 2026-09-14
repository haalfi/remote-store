# Updating the conda-forge recipe
<!-- doc: dual dest=explanation/design/conda-forge.md -->

## Intent & Scope

Scope: how a change to this project's packaging reaches conda-forge users, and
the traps specific to that route.

conda-forge serves `remote-store` from a **feedstock repository this project
does not own**, whose recipe is a copy of `packaging/conda-forge/recipe.yaml`.
Nothing in this repo can read that copy, and no gate compares the two. Every
rule below exists because that gap has already cost something: one submission
diverged by hand and silently dropped a dependency constraint and the whole
`about` block, and neither was noticed until someone diffed the copies by eye.

This is the authoritative procedure. [`CONTRIBUTING.md` §
Release](../CONTRIBUTING.md#release) Phase 5 links here rather than restating it.

## Rules

1. <a id="upstream-is-the-source"></a>**The upstream copy is the source.**
   Edit `packaging/conda-forge/recipe.yaml` first and copy it outward. Never
   edit the feedstock's copy directly and never back-port from it. A
   hand-edit on the far side is invisible to every check this repo runs.

2. **Never push a branch to the feedstock.** Maintainers have push access, and
   using it is the one irreversible mistake available here: conda-forge
   publishes feedstock branches automatically, so a branch push uploads a
   package before anyone reviews it — and conda-forge packages are immutable,
   so a bad upload cannot be edited or deleted, only marked broken. Work from a
   personal fork, or from the version-bump branch `regro-cf-autotick-bot`
   opens.

3. **Diff the two copies before opening the PR.** This is the only thing that
   catches drift; see [Rule 6](#what-the-gates-do-not-cover) for why neither
   gate does. Every difference must be one you intended.

4. **Set the build number by what changed.** Reset it to zero when the version
   changes; increment it by one when the version is unchanged and only recipe
   metadata moves. A metadata-only fix shipped without the increment does not
   reach users.

5. **Rerender whenever a rendered artifact's input changes.** The feedstock's
   `README.md` is generated from the recipe and carries its summary and
   description, so an `about` edit leaves the two disagreeing until a rerender.
   Request one by commenting `@conda-forge-admin, please rerender` on the PR;
   do not hand-edit a generated file.

6. **No internal tracker ID reaches the feedstock copy.** IDs are meaningless
   to a conda-forge reader and point at a tracker they cannot open. Carry the
   claim in prose instead. `check_no_tracker_refs` does not enforce this: it
   reads no YAML at all, and `packaging/` is outside every root it does scan.

7. <a id="what-the-gates-do-not-cover"></a>**Know what the two gates prove.**
   `check_conda_recipe_pins` holds *this repo's* recipe to `pyproject.toml`'s
   extras — not the feedstock to this repo. `check_backend_order` proves
   ordering, not membership, so a backend enumeration that is correctly ordered
   and incomplete passes it. Anything outside those two is a human's to check.

8. **Fill conda-forge's PR template.** It ships from their organisation
   defaults, so it appears on the PR without living in the feedstock. Remove
   the checks it says are irrelevant rather than leaving them unticked.

## Guides

### Which route to use

Both routes end in a PR against the feedstock from a branch this project
controls; pick by whether the bot has already acted.

| Situation | Route |
|---|---|
| No bot PR open | Fork the feedstock, branch, PR from the fork |
| Bot PR already open | Push the recipe change onto the bot's branch, so version and constraints land in one review |

The bot updates the source section and version only. Merging its PR untouched
therefore ships the new release carrying the previous release's constraints —
which is how a corrected dependency floor silently fails to reach conda users
while every gate in this repo stays green. Verifying the bot's PR exists is not
the task; carrying the constraints is.

To push to the bot's branch, add its fork as a remote and push there — the bot
branches from its own fork, and maintainers can write to it:

```bash
git remote add regro-cf-autotick-bot \
  https://github.com/regro-cf-autotick-bot/remote-store-feedstock.git
git fetch regro-cf-autotick-bot
```

`hub pr checkout <N>` sets up the same remote in one step.

### Walkthrough

1. Update `packaging/conda-forge/recipe.yaml` in this repo and let `hatch run
   lint` check it against `pyproject.toml`.
2. Fork the feedstock to a personal account, or add the bot's remote per the
   table above.
3. Copy the recipe outward. The copy is verbatim below `context:`; only
   comments differ, because some of them describe this repo's workflow or cite
   a tracker and mean nothing on the far side.
4. Diff the two copies. Confirm every difference is a comment you meant to
   change.
5. Commit to a branch, open the PR against the feedstock, and fill the
   template.
6. Comment `@conda-forge-admin, please rerender` when Rule 5 applies. Leave
   "Allow edits by maintainers" enabled so the rerender can be pushed to the
   branch.
7. Merge once CI is green and the rerender has landed.

### Keeping the copies from drifting

Deriving the feedstock's file from this repo's by script, rather than by hand,
turns the copy-out into something reproducible: the comment edits become a
declared list, each asserted to apply exactly once, so a silently skipped edit
fails loudly instead of shipping. Mechanising the comparison itself — rather
than relying on Rule 3's human diff — is open work; the backlog carries the
options and what each costs.
