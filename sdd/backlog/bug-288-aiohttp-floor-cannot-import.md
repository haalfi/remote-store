# BUG-288 — `[azure]`'s `aiohttp` floor names a release no supported interpreter can import
<!-- doc: repo-only -->

Moved verbatim from [`BACKLOG.md` § 5](../BACKLOG.md#no-release-surprises) by the ADR-0040 § 5
conversion, links re-based to this directory. The index entry holds the current
diagnosis; this file is evidence and advisory prescription
([§ Item authority](../BACKLOG.md#how-this-file-works)).

`azure = [..., "aiohttp>=3.0"]`. `aiohttp==3.0.0` builds and installs from
sdist on the oldest supported interpreter and then raises
`ImportError: cannot import name 'Mapping' from 'collections'` — the 3.3
collections-ABC move, which predates every Python this package supports. The
floor therefore admits a range whose bottom cannot run anywhere.
**Measured** by resolving `[azure]` at `--resolution lowest-direct` on the
oldest supported interpreter and importing. The same shape as BUG-284's
tenacity floor: a bound copied from a plausible source and never exercised.
**Where the number came from**, per the comment above the declaration: it is
`azure-core`'s own `aiohttp>=3.0; extra == "aio"`. Inheriting an upstream's
floor inherits the interpreters it was written for, and azure-core's has not
moved since. The fix is to declare the oldest `aiohttp` that imports on the
oldest interpreter we support, then delete the row from
`infra/drift-locks/KNOWN-FINDINGS.md`.
**Not** a finding about `[azure]`'s declared *set*: the extra installs alone
and the declaration is complete — BUG-286 fixed that half.

## Re-measured, 2026-09-28

Holds. `pyproject.toml` still declares `"aiohttp>=3.0"` in `azure` with the
azure-core comment above it, and azure-core 1.41.0's metadata still reads
`aiohttp>=3.0; extra == "aio"` (`importlib.metadata.requires('azure-core')`).
Not named above: both conda recipes also pin `aiohttp >=3.0`
(`rg -n aiohttp packaging/conda-forge/`), so a fix touches them too. The
`aiohttp==3.0.0` import failure needs a floor install and was not re-run.
Found by the ADR-0040 § 5 conversion.
