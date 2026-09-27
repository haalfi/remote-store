# BK-325 — Custom-backend guide: registry-integration and remaining contract-topic gaps
<!-- doc: repo-only -->

Moved verbatim from [`BACKLOG.md` § 3](../BACKLOG.md#users-succeed-unaided) by the ADR-0040 § 3
conversion, links re-based to this directory. The index entry holds the current
diagnosis; this file is evidence and advisory prescription
([§ Item authority](../BACKLOG.md#how-this-file-works)).

Guide content the PR #932 walkthrough showed a real backend needed but
the guide never teaches:
- Registry integration: credential-named YAML options arrive wrapped in
  `Secret` (constructors need `str | Secret` and `.reveal()`), and a
  `retry:` block injects a `retry=` kwarg. Step 13 says only "names
  must match". Reference shape: `S3Boto3Backend.__init__`.
- Stream-time error mapping for `LAZY_READ` backends: the cardinal rule
  covers call time only; lazy streams surface native errors during
  `read()` and `test_streaming.py` enforces no-leak there.
- The file-ancestor lane: `rejects_write_under_file_ancestor`,
  `strict_only` fixtures, and their `_MODULE_FOR` wiring are
  undocumented; skipping them silently drops ~25 conformance cells.
- Small fixes: error-mapping checklist lacks a base-`RemoteStoreError`
  fallback row; `from exc` guidance omits the deliberate `from None`
  pattern; the `SEEKABLE_READ` note contradicts shipped range-readers.

## Correction, 2026-09-27

`_MODULE_FOR` is no longer undocumented: `docs-src/guides/custom-backend-guide.md`
teaches it at lines 599-601 and 671-675. `rejects_write_under_file_ancestor`
and `strict_only` still have no hit in the guide (`rg` over the page). The
"~25 conformance cells" re-derives as a strict fixture's footprint:
`pytest tests/backends/conformance --collect-only -q -k "s3_moto_strict or
sqlblob_strict or azurite_async_strict" --stage=3` collects 70, which is 26 for
each of the two sync strict fixtures and 18 for the async one. How many of those
a default fixture does not already run was not re-derived. Found by the
ADR-0040 § 3 conversion.
