# Updating the conda-forge recipe
<!-- doc: repo-only -->

## Intent & Scope

Scope: how a packaging change in this repo reaches conda-forge users, for
whoever performs a release. Governed by [`CONTRIBUTING.md` § Authoritative
Document Format](../CONTRIBUTING.md#authoritative-document-format).

conda-forge serves `remote-store` from **`conda-forge/remote-store-feedstock`**,
a repository this project does not own, whose `recipe/recipe.yaml` is a copy of
`packaging/conda-forge/recipe.yaml`. Two mechanisms now stand behind that copy:
`scripts/gen_conda_feedstock.py` **produces** it, so the copy-out is one file
rather than a hand edit, and `scripts/drift_feedstock.py` **fetches the
published one weekly** and compares it against the generated copy this repo
committed at the tag its version names. What remains below is what those two
cannot do: choosing a route, opening the pull request, and everything the
feedstock owns.

[`CONTRIBUTING.md` § Release](../CONTRIBUTING.md#release) Phase 5 links here for
the routes, the rules and the walkthrough. Why these rules exist, and what their
absence already cost, is recorded in ID-018 and BK-370
([`BACKLOG-DONE.md`](BACKLOG-DONE.md)).

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

3. <a id="diff-the-copies"></a>**Copy `packaging/conda-forge/feedstock/recipe.yaml`
   across whole; never assemble the far copy by hand.** That file is generated
   from our recipe and `hatch run lint` fails when it is stale, so it is already
   what the feedstock should carry — the only edit on the far side is
   `build.number` ([Rule 4](#build-number)). Before pushing to the branch the PR
   builds from, check that is all that differs, against the file itself rather
   than by eye:

   ```bash
   diff <feedstock-clone>/recipe/recipe.yaml packaging/conda-forge/feedstock/recipe.yaml
   ```

   Expect one hunk, `build.number`. Anything else means the copy was assembled
   rather than copied.

   **`drift_feedstock` does not answer this question**, because it reads the
   feedstock's `main` branch: before the merge that is still the previous
   release's file. It is what confirms the result afterwards
   ([Walkthrough](#walkthrough) step 9), and what re-checks it every week. See
   [Rule 7](#what-the-gates-do-not-cover) for what it does not reach.

4. <a id="build-number"></a>**`build.number` belongs to the feedstock.** It is
   the one field the far copy owns and the one sanctioned non-comment difference,
   because conda-forge increments it for rebuilds and migrations this repo never
   sees. Set it there to `0` when the version changes, and `+1` when the version
   is unchanged and only recipe metadata moves — a metadata-only fix shipped
   without the increment does not reach users. Leave our copy's value alone.

5. <a id="rerender"></a>**Rerender after an `about` change.** The feedstock's
   `README.md` is generated from the recipe and carries its `about` summary and
   description, so an `about` edit leaves the two disagreeing until a rerender.
   Comment `@conda-forge-admin, please rerender` on the PR; do not hand-edit a
   generated file. The observable is a `@conda-forge-admin` commit on the branch
   touching `README.md`.
   This case is **ours, not upstream's**: conda-forge's
   [rerender how-to](https://conda-forge.org/docs/how-to/basics/rerender/) lists
   when a rerender is needed for the *build* — platform skips,
   `conda-forge.yml`, build matrix, pinning — and does not mention `about`. The
   basis here is direct observation at v0.32.0, where the rerender regenerated
   `README.md` with the new summary and changed nothing else. Requesting one
   costs nothing either way, and the PR template asks about it regardless.

6. <a id="no-tracker-ids"></a>**No internal coordinate reaches the feedstock
   copy**, and this is no longer your job. Backlog IDs, spec section IDs, ADR
   numbers and PR references all point somewhere a conda-forge reader cannot
   follow, so `check_no_tracker_refs` scans
   `packaging/conda-forge/recipe.yaml` **below `context:`** and fails `hatch run
   lint` on any of them. The claim stays in the recipe, in prose; the coordinate
   goes, at the source, in the pull request that would have introduced it.

   The header block above `context:` is exempt because
   [Rule 3](#diff-the-copies)'s generator replaces it. `CEP-13` is not a
   coordinate at all: it names a Conda Enhancement Proposal, so it sits in that
   gate's external-prefix set beside `PEP` and `ISO` and is free to appear
   anywhere, including the shipped header — which is where it does appear.

   This inverts what this rule used to ask. Stripping by hand at copy-out time
   meant the one artefact that leaves this repository was checked by the person
   least able to check it, once, against a pattern reproduced from memory.

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
     **both** recipes for any PR touching `packaging/conda-forge/**`, so
     structural validity is machine-checked for the shipped copy as well as the
     source. It says nothing about content.
   - `gen_conda_feedstock` compares **this repo's two copies**:
     `packaging/conda-forge/feedstock/recipe.yaml` against a fresh render of the
     source. `hatch run lint` fails when they disagree, so the shipped file
     cannot fall behind the recipe it is taken from. It never reads the
     feedstock.
   - `check_no_tracker_refs` holds the source recipe's body free of internal
     coordinates ([Rule 6](#no-tracker-ids)), which is what makes those bytes
     publishable without an edit.
   - `drift_feedstock` compares **the published copy** against the generated one
     this repo committed at the tag its `context.version` names, weekly, and
     reports on the drift-guard rolling issue. Its own docstring owns the
     vocabulary and the bounds; the ones worth knowing here are that
     `build.number` and `source.sha256` are excluded and therefore unwatched,
     that it reads one file on one branch and none of the feedstock's other
     files, and that a version this repo published no generated copy for reports
     `no-baseline` rather than a comparison — which is every tag cut before the
     generator existed.

8. **Fill [conda-forge's PR
   template](https://github.com/conda-forge/.github/blob/main/.github/PULL_REQUEST_TEMPLATE.md).**
   It ships from their organisation defaults, so it appears on the PR without
   living in the feedstock — which is why looking for one in the feedstock finds
   nothing. Remove the checks it says are irrelevant rather than leaving them
   unticked.

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
   `packaging/conda-forge/recipe.yaml`, run `hatch run gen-conda-feedstock`, and
   land **both** files here via a PR — the checklist's two preceding bullets
   carry the `sha256` command. Every edit to the recipe is a two-file edit now:
   `hatch run lint` fails on a stale generated copy, as well as checking the
   pins, and the `Conda Recipe` workflow renders both.
2. Fork `conda-forge/remote-store-feedstock` to a personal account, or add the
   bot's remote per the table above.
3. Copy `packaging/conda-forge/feedstock/recipe.yaml` onto the feedstock's
   **`recipe/recipe.yaml`**, whole. Nothing is stripped, replaced or reflowed:
   the generator already did the one transformation there is, and `hatch run
   lint` has already checked that file is current. Then set `build.number`
   there ([Rule 4](#build-number)).
4. Diff the far copy against ours ([Rule 3](#diff-the-copies)), expecting
   `build.number` and nothing else.
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
10. **Confirm the channel carries what we published**: once the PR is merged,
    `python scripts/drift_feedstock.py` reads the feedstock's `main` and should
    report `match`. This is the first moment it can — see
    [Rule 3](#diff-the-copies) — and it is the same check that then runs weekly,
    so a `drift` here is one you would otherwise meet on the rolling issue days
    later, with the release already out.
