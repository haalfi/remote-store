# Updating the conda-forge recipe
<!-- doc: repo-only -->

## Intent & Scope

Scope: how a packaging change in this repo reaches conda-forge users, for
whoever performs a release. Governed by [`CONTRIBUTING.md` § Authoritative
Document Format](../CONTRIBUTING.md#authoritative-document-format).

conda-forge serves `remote-store` from **`conda-forge/remote-store-feedstock`**,
a repository this project does not own, whose `recipe/recipe.yaml` is a copy of
`packaging/conda-forge/recipe.yaml`. Nothing here reads that copy and no gate
compares the two, so every rule below is a step no mechanism performs.

[`CONTRIBUTING.md` § Release](../CONTRIBUTING.md#release) Phase 5 links here for
the routes, the rules and the walkthrough. Why these rules exist, and what their
absence already cost, is recorded in ID-018 and BK-370
([`BACKLOG-DONE.md`](BACKLOG-DONE.md), [`BACKLOG.md`](BACKLOG.md)).

Upstream sources, which govern where they disagree with this page:
[maintainer guide](https://conda-forge.org/docs/maintainer/updating_pkgs/),
[org CONTRIBUTING](https://github.com/conda-forge/.github/blob/main/CONTRIBUTING),
[org PR template](https://github.com/conda-forge/.github/blob/main/.github/PULL_REQUEST_TEMPLATE.md).

## Rules

1. <a id="upstream-is-the-source"></a>**Edit `packaging/conda-forge/recipe.yaml`
   first and copy it outward.** Never edit the feedstock's copy directly, and
   never back-port from it. A hand-edit on the far side is invisible to every
   check this repo runs.

2. **Never push a branch to the feedstock**, though a maintainer can. conda-forge
   publishes feedstock branches automatically, so a branch push uploads a package
   before review — and conda-forge packages are immutable, so a bad upload cannot
   be edited or deleted, only marked broken (see [Rule 9](#marking-broken)). Work
   from a personal fork, or from the branch `regro-cf-autotick-bot` opens.

3. <a id="diff-the-copies"></a>**Diff the two copies before pushing to the branch
   the PR builds from** — on the fork route that is before the PR exists, on the
   bot route it is not. Every difference must be a comment you changed
   deliberately, or `build.number` ([Rule 4](#build-number)). Nothing else may
   differ, and no gate checks this: see [Rule 7](#what-the-gates-do-not-cover).

4. <a id="build-number"></a>**`build.number` belongs to the feedstock.** It is
   the one field the far copy owns and the one sanctioned non-comment difference,
   because conda-forge increments it for rebuilds and migrations this repo never
   sees. Set it there to `0` when the version changes, and `+1` when the version
   is unchanged and only recipe metadata moves — a metadata-only fix shipped
   without the increment does not reach users. Leave our copy's value alone.

5. <a id="rerender"></a>**Rerender whenever a rendered artifact's input changes.** The feedstock's
   `README.md` is generated from the recipe and carries its `about` summary and
   description, so an `about` edit leaves the two disagreeing until a rerender.
   Comment `@conda-forge-admin, please rerender` on the PR; do not hand-edit a
   generated file. The observable is a `@conda-forge-admin` commit on the branch
   touching `README.md`.

6. <a id="no-tracker-ids"></a>**No internal coordinate reaches the feedstock copy** — not only backlog
   IDs, but spec section IDs, ADR numbers and PR references, all of which point
   somewhere a conda-forge reader cannot follow. Carry the claim in prose
   instead. Check the far copy against the structural shape
   `check_no_tracker_refs` uses (`_TRACKER_RE` in that script, plus its `spec
   NNN` and `PR #NNN` forms), expecting no match; an enumerated prefix list is
   the wrong instrument here, because it passes the next `BE-008` or `GR-033`
   somebody cites. That gate cannot run this itself: it reads no YAML, and
   `packaging/` is outside every root it scans.

7. <a id="what-the-gates-do-not-cover"></a>**Know what each mechanism proves.**
   - `check_conda_recipe_pins` compares **this repo's** recipe with
     `pyproject.toml`; its full pair-set is the row in
     [`GATE-INVENTORY.md`](GATE-INVENTORY.md). It never reads the feedstock.
   - `check_backend_order` **ignores any enumeration naming fewer than six
     distinct backends** (`_MIN_BACKENDS`): both scanners discard it as prose
     before ordering is tested. A four-backend `about` block is invisible to it
     whether ordered or not — and our own `about` summary is in that blind spot
     today.
   - `.github/workflows/conda-recipe.yml` runs `rattler-build --render-only` on
     any PR touching `packaging/conda-forge/**`, so structural validity is
     machine-checked before the recipe leaves this repo. It says nothing about
     content.
   - Nothing compares the two copies. That is [Rule 3](#diff-the-copies), and it
     is a human step.

8. **Fill conda-forge's PR template.** It ships from their organisation defaults,
   so it appears on the PR without living in the feedstock. Remove the checks it
   says are irrelevant rather than leaving them unticked.

9. <a id="marking-broken"></a>**A bad published build is marked broken, never
   deleted.** Open a PR against
   [`conda-forge/admin-requests`](https://github.com/conda-forge/admin-requests)
   adding the appropriate `broken` request, then ship a corrected build with
   `build.number` incremented. There is no other remedy.

## Guides

### Which route to use

Both routes end in a PR against the feedstock from a branch this project
controls; pick by what the bot has already done.

| Situation | Route |
|---|---|
| No bot PR open | Fork the feedstock, branch, PR from the fork |
| Bot PR already open | Push the recipe change onto the bot's branch, so version and constraints land in one review |
| Bot has not fired and the release is waiting | Comment `@conda-forge-admin, please update version` on the feedstock, or take the fork route |
| Bot fires after the fork route was taken | Keep the fork PR and close the bot's — two open PRs against a third-party repo is the thing to avoid |

The bot updates the source section and version only. Merging its PR untouched
ships the new release carrying the previous release's constraints.

**Pushing to the bot's branch.** The branch name is generated (e.g.
`0.32.0_h<hash>`); read it off the bot's PR. Maintainers can write to the bot's
fork, so no setting on the PR needs changing:

```bash
git remote add regro-cf-autotick-bot \
  https://github.com/regro-cf-autotick-bot/remote-store-feedstock.git
git fetch regro-cf-autotick-bot
git push regro-cf-autotick-bot HEAD:<branch>
```

`gh pr checkout <N>` inside a feedstock clone sets the same remote up. The
observable is the commit appearing on the bot's PR with its CI re-running.

### Walkthrough

1. Set `context.version` and `source.sha256` in
   `packaging/conda-forge/recipe.yaml` and land that here via a PR — the
   checklist's two preceding bullets carry the `sha256` command. `hatch run lint`
   checks the pins and the `Conda Recipe` workflow renders it.
2. Fork `conda-forge/remote-store-feedstock` to a personal account, or add the
   bot's remote per the table above.
3. Copy our recipe into the feedstock's **`recipe/recipe.yaml`**. Replace the
   header comment block above `context:` — it describes this repo's workflow and
   does not ship. Below `context:` the copy is verbatim except the comments
   [Rule 6](#no-tracker-ids) requires stripping.
4. Diff the two copies ([Rule 3](#diff-the-copies)) and run
   [Rule 6](#no-tracker-ids)'s grep on the far copy.
5. Commit from a local clone, not through the GitHub API, whose commits are
   unverified. Push to the fork, or to the bot's branch.
6. Open the PR against `conda-forge/remote-store-feedstock` and fill the
   template. On the fork route, leave "Allow edits by maintainers" enabled so
   maintainers and the rerender can push to your branch; on the bot route the PR
   is not yours and there is nothing to set.
7. Comment `@conda-forge-admin, please rerender` when [Rule 5](#rerender)
   applies, and wait for its commit.
8. Merge once feedstock CI is green and the rerender has landed. If CI is red,
   it is this change's to fix — the recipe is the only thing the PR touches.
9. **Confirm users can get it**: `conda search -c conda-forge remote-store`
   lists the new version once the post-merge build uploads. Until that shows the
   release, the channel has not received it, whatever the PR says.
