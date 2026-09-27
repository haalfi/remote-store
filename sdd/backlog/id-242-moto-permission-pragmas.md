# ID-242 — Four `moto doesn't raise PermissionError` pragmas are coverage holes, not exemptions
<!-- doc: repo-only -->

Moved verbatim from [`BACKLOG.md` § 2](../BACKLOG.md#correct-and-proven) by the ADR-0040 § 2
conversion, links re-based to this directory. The index entry holds the current
diagnosis; this file is evidence and advisory prescription
([§ Item authority](../BACKLOG.md#how-this-file-works)).

`_s3_base.py` 510/540/573 and `_s3_pyarrow.py:626` each carry
`# pragma: no cover -- moto doesn't raise PermissionError`. The mappings are
correct and the pragmas are accurate statements about the fixture, which is
exactly the problem: **BUG-242 was a defect living behind the fifth instance
of this same pragma**, on the one branch that mattered, invisible to a suite
of 7976 passing tests.
A true "the fixture cannot reach this" is a coverage hole wearing an
exemption's clothes. It is indistinguishable from a real exemption at read
time, so it never gets revisited.
**Now cheap to close:** `tests/backends/s3/test_denied_probe.py` established a
`pytest-httpserver` harness that serves real 403s at Stage 1, no Docker and no
credentials. Each remaining pragma is a few params on that harness. Ship it
independently of ID-244 — nothing here waits on the seeding decision.

## Correction, 2026-09-27

The line numbers above have moved. `rg -n "moto doesn't raise PermissionError" src`
finds the same four arms at `_s3_base.py` 581, 611, 644 and `_s3_pyarrow.py:654`.
Found by the ADR-0040 § 2 conversion.
