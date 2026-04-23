# Audit 007 — Test Behavior Assertions

**Date:** 2026-03-30
**Scope:** All test files in `tests/` — checked against "Assert behavior, not
type" (Rule 2) and "Never assert on private attributes" (Rule 3) from
`research-testing-best-practices.md` §4.1.
**Method:** Systematic grep + agent-assisted sampling of all 39 test files
(~1,045 test functions). Cross-referenced against anti-pattern counts in
`research-testing-best-practices.md` §2.

---

## Summary

| Anti-Pattern | Count | Status vs. Research Doc |
|---|---|---|
| No assertions | **0** | Fixed (was ~35) |
| Unconstrained `MagicMock()` | **0** | Fixed (was ~67) |
| `isinstance` as sole assertion | **12 tests** | Open |
| Private attribute assertions | **~75 assertions** across 22 locations | Open |

**Good news:** Two previously-identified anti-patterns are now clean:

- **No-assertion tests:** 0 found (was ~35). Every test has `assert` or
  `pytest.raises`.
- **Unconstrained MagicMock:** 0 found (was ~67). All 69 `MagicMock()` calls
  use `spec=`.

---

## Category A: `isinstance` as sole/primary assertion (Rule 2)

Tests that verify the *type* of the return value but never check that it
*behaves correctly* (has the right data, delegates properly, etc.). A
refactoring that returns the wrong subclass or a broken instance would pass.

| # | Location | Severity | Summary |
|---|----------|----------|---------|
| A-1 | `test_otel.py:82` | Medium | `test_hooks_unpack_into_observe` — only asserts `isinstance(observed, ObservedStore)`. Does not verify hooks are wired or any operation works. |
| A-2 | `test_otel.py:99-100` | Medium | `test_otel_observe_returns_observed_store` — two isinstance checks (`ObservedStore`, `Store`), no behavioral assertion. |
| A-3 | `test_otel.py:105` | Medium | `test_otel_observe_with_env` — same pattern, isinstance only. |
| A-4 | `test_arrow.py:105` | Medium | `test_pyarrow_fs_factory` — only asserts `isinstance(result, pafs.PyFileSystem)`. Never uses the filesystem object. |
| A-5 | `test_proxy.py:228` | Medium | `test_native_path` — only asserts `isinstance(path, str)`. Should assert the path value. |
| A-6 | `test_proxy.py:246` | Medium | `test_child_returns_proxy` — only asserts `isinstance(child, _TestProxy)`. Should also verify the child delegates correctly. |
| A-7 | `test_registry.py:50` | Medium | `test_returns_store` — only asserts `isinstance(reg.get_store("main"), Store)`. Should verify the store has correct root/backend. |
| A-8 | `test_backend_sqlblob.py:645` | Medium | `test_unwrap_engine` — only asserts `isinstance(engine, sa.Engine)`. |
| A-9 | `test_backend_sqlquery.py:557` | Medium | `test_unwrap_engine` — same pattern as A-8. |
| A-10 | `test_backend_sqlblob.py:755` | Medium | `test_empty_path_for_folder_op` — only asserts `isinstance(result, bool)`. Should assert the *value* for an empty-path root folder. |
| A-11 | `test_batch.py:104` | Medium | `test_signature_returns_type` — parametrized but each case only does `isinstance(func(store, args), expected_type)`. Never inspects result content. |
| A-12 | `test_cache.py:158` | Low | `test_returns_cache` — `isinstance(result, CachedStore)` + `isinstance(result, Store)`. Type-only, should verify caching behavior. |

---

## Category B: Assertions on private attributes (Rule 3)

Tests that will break if internals are renamed/refactored even when behavior
is unchanged. ~75 individual assertions across 22 locations.

| # | Location | Severity | Summary |
|---|----------|----------|---------|
| B-1 | `test_registry.py:61,63,70,76,78,85,139,156,178` | Medium | 9 assertions on `reg._backends` (length checks). Should test via public API (e.g., verify `get_store()` returns same backend identity, or `close()` makes stores unusable). |
| B-2 | `test_registry.py:94` | Medium | `reg.get_store("main")._owns_backend is False`. |
| B-3 | `test_store_child.py:57` | Medium | `parent.child(subpath)._root == expected`. Could verify via observable behavior (e.g., child reads from correct prefix). |
| B-4 | `test_store_child.py:82,90-91` | Medium | `._backend is backend` and `._root`/`._backend` identity checks. |
| B-5 | `test_store_child.py:116-117` | Medium | `._owns_backend` checks on parent and child. |
| B-6 | `test_cache.py:111` | Low | `len(mcache._data) == 2`. Tests internal data structure size instead of observable behavior. |
| B-7 | `test_cache.py:163` | Medium | `cache(store)._ttl == 300.0`. Tests internal TTL field. |
| B-8 | `test_cache.py:168` | Medium | `cache(store, cache_backend=backend)._cache is backend`. Tests internal field identity. |
| B-9 | `test_cache.py:406` | Low | `child._max_entries == 2`. Internal config field. |
| B-10 | `test_arrow.py:75,92-93,499-500,509-510,534` | Medium | 8 assertions on `._store`, `._materialization_threshold`, `._write_spill_threshold`, `._native_fs`, `._native_path_fn`. |
| B-11 | `test_proxy.py:50,53` | Medium | `proxy._backend is inner._backend` and `proxy._owns_backend is False`. |
| B-12 | `test_config.py:313,329,698-700,721,729,749` | Medium | 7 assertions on `._host_key_policy`, `._retry` across SFTP/S3/S3PyArrow backends. |
| B-13 | `test_depth_listing.py:330,338,345,352` | Low | `sftp_stub._sftp.listdir_attr.call_count`. Reaches through to mock internals of a private attribute. |
| B-14 | `backends/test_sftp.py:508-516,525,723,1189` | Medium | 8 assertions on `._sftp_path()`, `._resolved_host_keys`, `._host_key_policy`, `._tofu_keys_path`. |
| B-15 | `backends/test_azure.py:235,239,274,302,456,462` | Medium | 6 assertions on `._max_concurrency`, `._azure_path()`, `._hns`, `._resolve_credential()`. |
| B-16 | `backends/test_s3.py:136,170,203,767` | Medium | 4 assertions on `._endpoint_url`, `._tls_ca_bundle`, `._digest_from_head_response()`. |
| B-17 | `backends/test_s3_pyarrow.py:135,169,192` | Medium | 3 assertions on `._endpoint_url`, `._tls_ca_bundle`. |
| B-18 | `backends/test_http.py:449,749,771` | Low | `._context.check_hostname`, `._head_blocked`. Internal state checks. |
| B-19 | `test_coverage_gaps.py:102` | Low | `store._root == "a/b/c"`. Internal root field. |
| B-20 | `test_observe.py:423` | Low | `_store.log.name`. Semi-internal logger name check. |
| B-21 | `test_ping.py:212` | Low | `backend._base_path`. Reaches into private attribute inside mock call assertion. |
| B-22 | `test_backend_sqlblob.py:884` | Low | `SQLBlobBackend._glob_to_like(pattern)`. Tests a private static method directly. |

---

## Observations

1. **Mock spec cleanup is complete** — all 69 `MagicMock` calls use `spec=`.
2. **No-assertion tests are gone** — every test function has at least one
   `assert` or `pytest.raises`.
3. **`isinstance`-only tests are low-hanging fruit** — 12 tests could be
   strengthened by adding one behavioral assertion each.
4. **Private attribute assertions are the largest remaining debt** — ~75
   assertions across the codebase. Many test internals that arguably should
   have public observables (registry backend count, cache TTL, store root).
   Some (`._sftp_path()`, `._azure_path()`, `._glob_to_like()`) test private
   helper methods directly — these are the most fragile.
5. **Mutation testing showed no surviving mutants** — this suggests the
   behavioral coverage is decent despite the assertion style issues. The risk
   is refactoring fragility, not missed bugs.
