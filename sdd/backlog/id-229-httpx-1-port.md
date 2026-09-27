# ID-229 — Evaluate porting to httpx 1.0 (lift the `<1.0` cap)
<!-- doc: repo-only -->

Moved verbatim from [`BACKLOG.md` § 5](../BACKLOG.md#no-release-surprises) by the ADR-0040 § 5
conversion, links re-based to this directory. The index entry holds the current
diagnosis; this file is evidence and advisory prescription
([§ Item authority](../BACKLOG.md#how-this-file-works)).

BUG-225 capped the `graph` and `httpx` extras at `httpx>=0.24.0,<1.0`
after the drift guard's `--pre` re-resolution pulled `httpx==1.0.dev3`
and the async graph backend failed to import. That pre-release turned
out to be a **wholesale API rewrite**, not the exception-hierarchy
reorg the BUG-225 diagnosis first assumed: `1.0.dev3` drops
`httpx.AsyncClient`, `httpx.TransportError`, `httpx.DecodingError`,
`httpx.HTTPStatusError`, `Timeout`, `Limits` — essentially the entire
client surface the graph backend (`AsyncClient` in ~30 sites) and the
`[httpx]` HTTP adapter are built on. Coding around a single missing
symbol would only convert an honest import failure into a falsely-green
import that then explodes at runtime on `httpx.AsyncClient(...)`, so the
cap is the honest interim posture. The cap constrains every dependency
set a user resolves, so it needs a watch rather than silent drift.
**Upstream context:** the cap matches the maintainers' own guidance.
httpx 0.28.x is still a pre-1.0 line; the "1.0.dev" / "httpx2" threads
are about the project's next major API *direction*, not a released
stable 1.x series. In the late-2024 V1 discussion the maintainers said
httpx was not yet at a 1.0 SemVer release and recommended **pinning to
0.28 while reviewing deprecations** — which is exactly what `<1.0` does.
Ref: [encode/httpx#3344](https://github.com/encode/httpx/discussions/3344).
**When picked up:** real httpx 1.0 stable is out and pins install
cleanly against it. Diff the actual 1.0 public API against 0.28
(`AsyncClient`, `Response`, `Timeout`/`Limits`, the transport-error and
decoding-error bases, `respx` compatibility); decide port-vs-hold; if
porting, update `_graph/*.py` + the `[httpx]` backend, raise the cap,
and refresh the `graph` / `httpx` drift baselines.
**Why ID, not BK:** unevaluated migration against an upstream whose 1.0
shape is not yet stable. Mirrors the revisit discipline of ID-150.
