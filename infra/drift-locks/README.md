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

**If that download is blocked** — artifacts are served from a storage host
separate from `api.github.com`, so an egress policy scoped to the GitHub API
denies the fetch even though every other `gh` call works. The symptom is a 403 on
CONNECT from `gh run download` alone; that is a policy denial, not a transient
failure, so retrying will not clear it. Reconstruct the freeze from the rolling
issue instead:
it is the committed baseline with the issue body's rows applied, because the
report diffs over the *union* of baseline and resolved packages — so every
difference is enumerated, and a package absent from those tables is unchanged.
Apply the **stable** and **pre-release** tables both; they describe one
resolution, split only for presentation. A `—` in either column is a value, not a
blank: `—` under Baseline means the package is new (add the line), `—` under
Resolved means it is gone (drop the line). The result is byte-identical to the
artifact, so the guarantee below still holds. Verify by re-deriving: the new lock
must differ from the baseline in exactly the issue's rows, and in nothing else.

Either way, commit the changed `infra/drift-locks/<extra>.txt` and
`docs-src/reference/tested-versions.md` in the same PR as whatever
deliberate change motivated the refresh (e.g. a floor bump).

> **A green smoke means the committed pins were the ones tested.** The workflow
> resolves each extra once and pins the smoke to that exact set with a pip
> constraints file (`-c`), so the report, the smoke, and this candidate baseline
> all describe the same resolution. A test plugin that cannot coexist with the
> candidate set fails the install loudly (red smoke) rather than silently moving
> a shared dependency off its pin.

This guarantee is unconditional on the candidate-artifact and reconstruction
paths, where the committed lock is byte-identical to the smoked freeze. On the
local-resolve path, `refresh-baseline` re-resolves with `--pre` at commit time,
which can be later than the run that produced the drift report; a package that
moved between the two resolves lands in the new lock without ever being smoked —
including packages absent from the issue body entirely, so nothing in the drift
report flags them. The gap does not self-heal: the workflow only smokes packages
whose `status` is `drift` against the committed baseline, so once the later
version becomes that baseline, a clean run reports `ok` and skips the smoke for
it going forward.

**Pin such packages back to the run's snapshot** rather than only disclosing
them. Disclosure in the PR description was the earlier mitigation and it is not
enough: the unqualified claim still ships to the generated
`docs-src/reference/tested-versions.md`, whose preamble tells readers "Tested up
to" is "what CI was last green against", and by the non-self-healing property
above it stays there indefinitely. Pinning back costs one more weekly cycle —
the next run flags those packages, smokes them, and they are accepted on
evidence. Keep a higher pin only when you have evidence for it, and name the
smoke that produced it in the PR.
