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

Run on the primary Python (3.13, matching the workflow's runner):

```
hatch run drift-check refresh-baseline <extra>
hatch run drift-check render-docs
```

…then commit the changed `infra/drift-locks/<extra>.txt` and
`docs-src/reference/tested-versions.md` in the same PR as whatever
deliberate change motivated the refresh (e.g. a floor bump).

`refresh-baseline all` regenerates every extra at once.
