# Research: Bug Prevention Beyond Testing

**Date:** 2026-04-03
**Status:** Complete
**Scope:** Systematic analysis of 0.21.1 bug root causes and evaluation of
prevention strategies beyond testing (DbC, PBT, extended conformance,
resource safety, static analysis).
**Related:** BK-139, BUG-159,
[TESTING.md](../TESTING.md),
[research-testing-best-practices.md](research-testing-best-practices.md).

**Context:** The 0.21.1 patch release fixed 22 bugs despite strong SDD
practices, spec-driven development, 95% coverage, mutation testing, and
review-enforced test quality rules. This document analyzes root causes,
evaluates prevention strategies beyond testing, and recommends
concrete actions.

---

## 1. Bug Taxonomy (0.21.1)

Categorizing the 22 bugs fixed in 0.21.1 by root cause pattern reveals
seven clusters:

| Pattern | Bugs | Count |
|---------|------|-------|
| Cross-backend behavioral inconsistency | BUG-150, 151, 152, 155 | 4 |
| Resource leak on error path | BUG-142, 144, 156, 158 | 4 |
| Error swallowing / wrong error mapping | BUG-145, 146, 147 | 3 |
| Edge-case inputs not rejected | BUG-136, 139, 140, 141 | 4 |
| Cache coherency | BUG-137, 138 | 2 |
| Mutation of caller data | BUG-148 | 1 |
| Edge-case behavior on unexpected input | BUG-143, 153, 154, 157 | 4 |

**Key observation:** Most bugs are NOT logic errors in core algorithms. They
are **behavioral gaps at boundaries** — parameter combinations the conformance
suite didn't cover, error paths where native exceptions leaked or were
swallowed, resource lifecycle edges, and input values nobody expected.

Testing alone cannot efficiently prevent these. The conformance suite tests
each method's primary contract, but the bug surface is in the *cross-product*
of methods, parameters, backends, and failure modes.

---

## 2. Strategies Evaluated

Six strategies were evaluated for fit with remote-store's design principles
(zero runtime deps, SDD/spec-driven, mypy strict, minimal complexity).

### 2.1 Design-by-Contract (DbC)

**Libraries evaluated:** icontract (mature, ABC inheritance via `DBCMeta`),
deal (static linter, weaker ABC story), dpcontracts/PyContracts (dead).

**Verdict: Targeted `assert` only — no library.**

Rationale:
- Adding icontract breaks the zero-runtime-dependency guarantee.
- The conformance suite already IS the DbC system — it tests pre/post
  conditions for every BE-xxx spec across all backends.
- The 0.21.1 bugs were not caused by missing contract infrastructure;
  they were caused by missing test cases.
- icontract's strongest feature (contract inheritance on ABC) overlaps
  entirely with what the parameterized conformance suite does.
- No major Python storage library (fsspec, smart_open, SQLAlchemy, PyArrow)
  uses a DbC library. The industry pattern is: explicit validation for
  external input, `assert` for internal invariants, conformance tests for
  behavioral contracts.

**What to do instead:**
- Bare `assert` for internal invariants in complex methods (e.g., after
  stream wrapping: `assert not stream.closed`). Stripped by `python -O`.
- Explicit `raise TypeError/ValueError` for external input validation
  (config parsing, constructor args) — ordinary validation, not DbC.

### 2.2 Property-Based Testing (PBT)

**Tool:** Hypothesis (dev dependency only, zero runtime impact).

**Verdict: Adopt — high value for 4 specific targets.**

PBT excels where the input space is combinatorial and there is a clear
oracle (roundtrip property, "no silent corruption" invariant, dict-model
equivalence). The 0.21.1 parsing/config bugs (BUG-136, 139, 140, 141) are
textbook PBT targets.

**Priority targets:**

| # | Target | Property | Bugs caught |
|---|--------|----------|-------------|
| P1 | Partition roundtrip | `parse(build(k,v)) == (k,v)` | BUG-141 |
| P2 | Config `from_dict` | Never silently corrupts (no `"None"` strings) | BUG-139, 140 |
| P3 | Path normalization | Idempotent; hostile input normalizes or raises | BUG-136 |
| P4 | Stateful backend model | MemoryBackend matches dict under random ops | BUG-152, 155 |

P1–P3 are pure functions — microsecond execution, ~80 lines total.
P4 uses Hypothesis `RuleBasedStateMachine` — model the backend as a Python
dict, generate random write/read/delete/list sequences, verify the real
backend matches. ~60 lines. **P4 is the highest-value target**: it catches
cross-backend behavioral inconsistency, the hardest bug class to find
manually and the one that caused the most 0.21.1 bugs.

**CI setup:** Three profiles (`dev`=50 examples, `ci`=100, `nightly`=1000).
Total CI impact: ~10 seconds. Add `.hypothesis/` to `.gitignore`.
Hypothesis must be strictly a dev dependency (in `[tool.hatch.envs.default]`
dependencies, never in `[project.dependencies]`) to maintain the
zero-runtime-dep guarantee.

**Concrete example — would have caught BUG-141:**

```python
@given(
    keys=st.lists(partition_key, min_size=1, max_size=4, unique=True),
    values=st.lists(partition_value, min_size=1, max_size=4),
    filename=st.text(alphabet=..., min_size=1, max_size=30),
)
def test_partition_roundtrip(keys, values, filename):
    pairs = dict(zip(keys, values[:len(keys)]))
    path = partition_path(filename, **pairs)
    parsed = parse_partition(path)
    assert parsed.partitions == pairs
    assert parsed.filename == filename
```

**Concrete example — would have caught BUG-139, BUG-140:**

```python
@given(data=config_strategy)
@settings(max_examples=200)
def test_config_from_dict_no_silent_corruption(data):
    try:
        rc = RegistryConfig.from_dict(data)
    except (TypeError, ValueError, KeyError):
        return  # valid rejection
    for bc in rc.backends.values():
        assert bc.type != "None"       # BUG-140
        assert isinstance(bc.options, dict)  # BUG-139
```

### 2.3 Cross-Backend Extended Conformance Suite

**Verdict: Adopt — ~58 new tests in 6 categories.**

The existing conformance suite tests each method's primary contract but not
parameter combinations, edge-case inputs, error fidelity, metadata fields,
or resource cleanup. Every 0.21.1 bug class maps to one of these gaps.

**Structure:** New file `tests/backends/test_conformance_extended.py` with
`@pytest.mark.extended_conformance`. Reuses existing `backend` fixture —
zero new infrastructure.

| Category | Priority | Tests | Bugs caught |
|----------|----------|-------|-------------|
| Parameter combinations | CRITICAL | ~15 | BUG-152, 155 |
| Edge-case inputs | HIGH | ~12 | BUG-143, 153, 154 |
| Error fidelity | HIGH | ~10 | BUG-145, 146, 147 |
| Metadata consistency | MEDIUM | ~8 | BUG-150, 151 |
| Resource cleanup | MEDIUM | ~6 | BUG-142, 144, 156, 158 |
| Operational consistency | MEDIUM | ~7 | General regression |

**Key design decisions:**
- Edge-case tests assert on `RemoteStoreError` (base class), not specific
  subclasses. The contract is "no native exceptions leak."
- ETag test uses a `_BACKENDS_WITH_ETAG` set documenting the per-backend
  contract. S3PyArrow would have been in the set and failed (BUG-150/151).
- Resource cleanup tests verify the observable contract cross-backend;
  deep monkeypatch tests (wrapper failure injection) stay backend-specific.

**CI impact risk:** 58 tests x 7 backends = ~400 parameterized cases. Tests
against mocked backends (moto, Azurite, in-memory SFTP) are fast, but
watch for bloat. Use `@pytest.mark.extended_conformance` so these can be
separated into integration/nightly CI if they slow the default run. Keep
the extended suite focused — test dangerous parameter combinations, not
exhaustive permutations.

**Concrete example — would have caught BUG-152, BUG-155:**

```python
@pytest.mark.parametrize(
    ("recursive", "max_depth", "expected_names"),
    [
        pytest.param(True, 0, {"a.txt"}, id="depth0"),
        pytest.param(True, 1, {"a.txt", "b.txt", "c.txt"}, id="depth1"),
        pytest.param(True, 2, {"a.txt", "b.txt", "c.txt", "d.txt"}, id="depth2"),
        pytest.param(True, None, {"a.txt", "b.txt", "c.txt", "d.txt", "e.txt"}, id="unlimited"),
    ],
)
def test_list_files_recursive_max_depth(self, backend, recursive, max_depth, expected_names):
    _require(backend, Capability.LIST, Capability.WRITE)
    _seed(backend, self.DEPTH_TREE)
    files = list(backend.list_files("pc", recursive=recursive, max_depth=max_depth))
    assert {f.name for f in files} == expected_names
```

**Concrete example — would have caught BUG-153, BUG-154:**

```python
def test_read_on_directory(self, backend):
    _require(backend, Capability.WRITE)
    backend.write("dir_r/file.txt", b"x")
    with pytest.raises(RemoteStoreError):
        backend.read("dir_r")
```

### 2.4 Resource Safety Patterns

**Verdict: Adopt `_safe_wrap` helper — also found a latent bug.**

The 4 resource-leak bugs (BUG-142, 144, 156, 158) share a single pattern:
backend `read()` acquires a low-level resource (file handle, paramiko
channel, Azure downloader), then wraps it in `_ErrorMappingStream` /
`BufferedReader`. If wrapping fails, the raw resource leaks.

**Latent bug found during research (filed as BUG-159):** Both S3 backends
have unprotected acquire-then-wrap in `read()`. `S3Backend.read()`
(`_s3.py:130-134`) wraps an s3fs handle in `_ErrorMappingStream` →
`BufferedReader` (double-layer, same as BUG-142/158). `S3PyArrowBackend`
(`_s3_pyarrow.py:196-200`) wraps a PyArrow `NativeFile` in
`_PyArrowBinaryIO` → `_ErrorMappingStream` (single-layer, different
resource type). If any wrapping constructor raises, the raw handle leaks.

**Recommended deliverables:**

| Action | Value | Effort |
|--------|-------|--------|
| `_safe_wrap()` helper in `_stream.py` | HIGH | ~10 lines |
| Fix S3Backend.read() using the helper | BUG FIX | Uses helper |
| `ResourceWarning` in `__del__` for SFTP/Azure backends | LOW-MED | ~5 lines each |

The helper:

```python
def _safe_wrap(raw: BinaryIO, wrapper: Callable[[BinaryIO], BinaryIO]) -> BinaryIO:
    """Wrap a stream, closing the raw handle if wrapping fails."""
    try:
        return wrapper(raw)
    except BaseException:
        with contextlib.suppress(Exception):
            raw.close()
        raise
```

**What was ruled out:**
- `ExitStack` in `__init__` — over-engineering for lazy properties. "Store
  as `self._X`, close in `close()`" is what every comparable library does.
- `ExitStack` in `read()` — heavier than `_safe_wrap` for the common case.
- Async backends — different architecture (async generators). No equivalent
  leak pattern exists.
- Linter rules — no ruff/pylint rule can detect acquire-then-wrap without
  protection. The helper eliminates the pattern structurally.

### 2.5 Static Analysis for Error Handling

**Verdict: One custom AST script + enable ruff `BLE` rules.**

The SFTP error-swallowing bugs (BUG-145, 146, 147) are **semantic** — ruff
can flag `except Exception:` but not `except IOError:` that should check
`errno`. This requires a custom AST checker.

**Ruff gap analysis:**

| Rule | Enabled? | Catches SFTP bugs? |
|------|----------|-------------------|
| `E722` (bare `except:`) | Yes | No |
| `BLE001` (`except Exception`) | **No** | No — only flags `Exception`/`BaseException`, not `IOError` |
| `TRY*` (tryceratops) | Not enabled | No — TRY rules cover raise style, logging, else clauses. None flag silent returns. |
| `PGH*` (pygrep-hooks) | Not enabled | No — PGH rules cover noqa/type:ignore annotations, not error handling. |
| `S110` (try/except/pass) | Not enabled | Partially — catches `pass` but not `return False` or `return []` |

**Deliverable 1 — `scripts/check_error_handling.py` (~80 lines):**

Scans `src/remote_store/backends/*.py`. Flags `except` handlers where:
- The caught type is broad (`IOError`, `OSError`, `Exception`, `BaseException`)
- The body silently returns (`pass`, `return []`, `return False`, `return None`)
- The handler does NOT check `errno`

Supports `# noqa: RSE001` suppression for intentional broad catches
(~3–5 in current code: `exists()`, `is_file()`, `is_folder()`).

Would have caught BUG-145, BUG-146, BUG-147 directly.

**Maintenance risk:** Custom AST scripts can become brittle as code
patterns evolve. The two existing scripts (`check_test_assertions.py`,
`check_mock_spec.py`) have been stable because they target narrow,
well-defined patterns. This script targets a similarly narrow pattern
(broad catch + silent return + no errno). Keep scope minimal — if it
grows beyond ~100 lines or requires frequent suppression updates,
reconsider in favor of review-enforced rules.

**Deliverable 2 — Enable ruff `BLE` rule set:**

One-line change in `pyproject.toml`. Flags `except Exception` without
re-raise. May need ~2–3 `# noqa: BLE001` suppressions.

**What was ruled out:**
- Pylint — ruff + custom scripts cover the gap better.
- Full native-exception-leak detection via AST — requires call-graph
  analysis. False-positive rate too high on LocalBackend.
- Error message format checking — low bug density.

### 2.6 Strategies Not Pursued

| Strategy | Reason |
|----------|--------|
| Fuzzing (AFL, python-afl) | Redundant with Hypothesis (§ 2.2) |
| Immutability enforcement | Narrow scope (1 bug). Fold into PBT mutation checks. |
| Type-level guarantees | Already at mypy strict. Incremental gains don't justify effort. |

---

## 3. Coverage Matrix

How each strategy maps to the 0.21.1 bug clusters:

| Bug cluster | PBT | Extended conformance | Resource safety | Static analysis |
|-------------|-----|---------------------|-----------------|-----------------|
| Cross-backend inconsistency | P4 (stateful) | Parameter combos | — | — |
| Resource leak on error path | — | Resource cleanup | `_safe_wrap` | — |
| Error swallowing | — | Error fidelity | — | `check_error_handling.py` |
| Edge-case inputs | P1–P3 | Edge-case matrix | — | — |
| Cache coherency | P4 (stateful) | Operational consistency | — | — |
| Mutation of caller data | P2 (config) | — | — | — |

All 22 bugs are covered by at least one strategy. Most are covered by two
(defense in depth).

---

## 4. Implementation Priority

Ordered by value-to-effort ratio:

| # | Deliverable | Effort | Prevents | Risk |
|---|-------------|--------|----------|------|
| 1 | `_safe_wrap` helper + S3 bug fix (BUG-159) | ~20 lines | Resource leaks (4 bugs) + latent S3 bug | Very low |
| 2 | Hypothesis P4 (stateful backend model) | ~60 lines | Cross-backend + emergent bugs | Low (flaky if non-deterministic — use fixed seeds in CI) |
| 3 | Hypothesis P1–P3 (partition, config, path) | ~80 lines | Parsing/config bugs (4 bugs) | Low |
| 4 | Enable ruff `BLE` rules | 1-line config | Broad-except class | Very low |
| 5 | Extended conformance suite (6 categories) | ~300 lines | All 22 bug classes | Medium (CI duration — use marks to separate) |
| 6 | `check_error_handling.py` AST script | ~80 lines | Error swallowing (3 bugs) | Medium (maintenance burden — keep scope minimal) |
| 7 | `ResourceWarning` safety net for SFTP/Azure | ~10 lines | Debugging aid | Very low |

Items 1–4 are the highest-ROI investments (resource safety + PBT).
Item 5 has medium ROI but needs CI-time monitoring. Item 6 is deferred
until items 1–5 prove insufficient — the extended conformance error
fidelity tests (item 5, category 3) may cover the same bug class with
less maintenance overhead. Item 7 is a nice-to-have.

---

## 5. Relationship to Existing Infrastructure

| Existing | New strategy | Relationship |
|----------|-------------|--------------|
| Conformance suite (`test_conformance.py`) | Extended conformance | Complement — same fixture, new edge cases |
| Conformance suite | PBT stateful model | Complement — conformance tests known scenarios, PBT explores random sequences |
| `check_test_assertions.py` | `check_error_handling.py` | Same pattern — AST script in CI lint job |
| `check_mock_spec.py` | `check_error_handling.py` | Same pattern |
| ruff rules | Enable `BLE` | Extension of existing config |
| `_ErrorMappingStream` | `_safe_wrap` | Same module (`_stream.py`) |
| Mutation testing (pytest-gremlins) | PBT | Complement — mutation tests kill mutants in existing code, PBT generates new inputs |
| mypy strict | (no change) | PBT and conformance tests catch what types cannot |
