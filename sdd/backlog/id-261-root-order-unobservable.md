# ID-261 — BE-029's order is unobservable to conformance wherever a present root already answers correctly
<!-- doc: repo-only -->

The index entry holds the current diagnosis; this file is evidence and
advisory prescription ([§ Item authority](../BACKLOG.md#how-this-file-works)).

**Evidence (2026-10-01, PR #1050 rounds 5 and 6).** BE-029 said a wrong order
is "observable as exactly the wrong error class or a spurious success". Measured
by removing every key-decided root check in-session, through a pytest plugin,
never a source edit:

- `_flat_ns._reject_root_as_file` made a no-op;
- `LocalBackend.exists`, `is_file` and `is_folder` answering by observation only;
- `S3Backend.exists` and `is_folder` likewise, with the closed guard kept.

Selection: `test_file_operation_on_root_raises_invalid_path`,
`test_delete_root_with_missing_ok_still_raises` and `test_root_is_a_folder*` in
`tests/backends/conformance/test_io.py` and `test_async_extended.py`, on the
`local`, `local_async_adapted` and `s3_moto` lanes. Result: 16 failed, 42
passed; all 16 failures are file-shaped cells on `s3_moto`. Every file-shaped
cell on `local` and `local_async_adapted`, and every probe cell on all three
lanes, stayed green: a present root answers right by observation, so the order
is not what the cells see. The per-backend absent-container modules
(`tests/backends/local/test_absent_root.py` under the same plugin: 19 failed,
59 passed) are what catch it.

**Prescription (advisory).** Either an absent-root conformance fixture, which
BK-345 also needs, or a per-backend pin for every backend whose root can vanish.
