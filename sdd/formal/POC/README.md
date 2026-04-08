# DafnyOracle POC (Proof of Concept)

## Overview

This directory contains a **proof-of-concept implementation** of a reference oracle derived from the formal Dafny specification (`MemoryBackend.dfy`). It bridges formal verification and runtime testing.

## Contents

- **`oracle.py`** — Handwritten Python implementation of `MemoryBackend.dfy`
  - Faithful mirror of all postconditions and error-ordering guarantees
  - 680 lines; no external dependencies beyond Python stdlib
  - Serves as ground truth for conformance testing

- **`test_oracle.py`** — Self-contained conformance test suite
  - 25 oracle self-tests validating spec correctness
  - 7 backend comparison tests (skipped in this POC directory)
  - **Intentionally not discoverable by CI** — run explicitly only

## Why Isolated?

The oracle is **experimental** and not yet integrated into the main test suite:

1. **Test Infrastructure Gap**: Backend comparison tests require the `backend` fixture from `tests/backends/conftest.py`. Copying fixtures into POC creates duplication.

2. **Integration Not Ready**: The unified oracle bridge (BK-139c remaining work) needs:
   - Adapter layer for Dafny types (Seq, Map, CodePoint ↔ Python)
   - Differential conformance test suite
   - CI integration strategy

3. **Not Part of Regular CI**: Test file in `sdd/formal/POC/` won't be discovered by:
   - `pytest tests/` (main test suite)
   - `ruff check tests/` (linting gates)
   - GitHub Actions CI workflow

## Running Tests

**Self-tests only** (no backend fixture dependency):
```bash
cd sdd/formal/POC
python -m pytest test_oracle.py::TestOracleBasics -v
python -m pytest test_oracle.py::TestOracleSelfOperations -v
python -m pytest test_oracle.py::TestOracleErrorOrdering -v
python -m pytest test_oracle.py::TestOracleDepthFiltering -v
python -m pytest test_oracle.py::TestOracleDeleteFolder -v
```

**Full test suite** (requires moving to main suite; see below):
```bash
# Not runnable from POC — requires backend fixtures
python -m pytest test_oracle.py::TestBackendVsOracle -v
```

## Next Steps (BK-139c)

To move oracle into production:

1. **Create unified oracle**:
   - Wrapper around `MemoryBackend-py/` (compiled Dafny output)
   - Type marshaling for Seq ↔ list, Map ↔ dict, CodePoint ↔ int

2. **Integrate into main suite**:
   - Move `test_oracle.py` to `tests/backends/`
   - Create `conftest.py` fixture providing compiled oracle alongside handwritten
   - Differential conformance test: "oracle1 result == oracle2 result"

3. **Update CI**:
   - Mark oracle comparison tests with `@pytest.mark.oracle_conformance`
   - Add CI gate: "Fail if compiled oracle ≠ handwritten oracle"
   - Use oracle for daily conformance, compiled oracle for spec verification

## Architecture

**Two-tier oracle strategy**:

| Layer | Implementation | Use Case | Verification |
|-------|---|---|---|
| **Handwritten** | `oracle.py` (Python) | Daily CI, fast feedback | 25 self-tests pass |
| **Compiled** | `MemoryBackend-py/module_.py` (from Dafny) | Authoritative spec | 41 verified proofs |

Both should eventually agree (differential testing). If they diverge, code is wrong.

## References

- `sdd/formal/POC-DAFNY-ORACLE.md` — Architecture overview and design decisions
- `sdd/BACKLOG.md` (BK-139c) — Integration roadmap
- `sdd/formal/MemoryBackend.dfy` — Formal specification source
