<!-- doc: repo-only -->
# Drift-guard baselines (ID-182)

One file per extra in `pyproject.toml`'s `[project.optional-dependencies]`,
excluding the developer aggregates (`dev`, `docs`, `bench`) and the
marker-gated `toml` extra. Each file pins the full transitive resolution
captured when `remote-store[<extra>]` was last known-good.

`.github/workflows/drift-guard.yml` re-resolves each extra weekly with
`pip install --upgrade --pre`, diffs against the file here, and opens a
single rolling issue if a package drifts.

## File format

```
# extra: <name>
# python: <X.Y>
# captured: <YYYY-MM-DD>
# Regenerate with: hatch run drift-check refresh-baseline <name>

package-a==1.2.3
package-b==4.5.6
...
```

`==` lines are the parsed-and-compared payload; the header is metadata.

## Stub files

A baseline with no `==` lines (only the header / explanatory comment) is a
stub. The drift script treats stubs as "needs refresh" rather than "every
package drifted" — the workflow surfaces this as an advisory in the rolling
issue rather than a flood of false drift entries.

## Refreshing

A lock is **Python- and OS-specific**. The workflow resolves on Linux with
Python 3.13, and a resolve on another platform picks up platform-conditional
dependencies that resolution never sees (`colorama` via click/tqdm, `pywin32`,
etc.). Commit those and the next weekly run diffs its Linux resolution against
your lock, reports the extra packages as drift, and the rolling issue never
clears. The header records `# python:` but not the platform, so a
Windows-resolved lock is indistinguishable from a Linux one on inspection —
match the host deliberately.

**On Linux with Python 3.13** — resolve locally:

```
hatch run drift-check refresh-baseline <extra>
hatch run drift-check render-docs
```

`refresh-baseline all` regenerates every extra at once.

**On any other host** — take the resolution from the drift-guard run instead of
resolving locally. Each run uploads a Linux-resolved freeze per extra for
exactly this purpose:

```
gh run download <run-id> --repo haalfi/remote-store \
  --pattern 'candidate-baseline-*' --dir <tmp>
```

Write `infra/drift-locks/<extra>.txt` as the header above followed by the
artifact's freeze sorted by package name, matching `write_lock` in
`scripts/drift_check.py`, then run `hatch run drift-check render-docs`.

Either way, commit the changed `infra/drift-locks/<extra>.txt` and
`docs-src/reference/tested-versions.md` in the same PR as whatever
deliberate change motivated the refresh (e.g. a floor bump).

> **A green smoke is not proof the committed pins were tested.** The workflow
> resolves three times per extra (report, smoke, candidate baseline) and the
> smoke shares its environment with the test plugins, so it can run against a
> mixed version set. See ID-231.
