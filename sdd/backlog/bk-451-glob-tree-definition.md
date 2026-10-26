# BK-451 — `glob` has no definition in tree terms and no single pattern dialect
<!-- doc: repo-only -->

The index entry holds the current diagnosis; this file is evidence and
advisory prescription ([§ Item authority](../BACKLOG.md#how-this-file-works)).

**Where this comes from.** [Audit 023](../audits/audit-023-kernel-migration-readiness.md),
findings T7 and T8, proposal P2 and its open question on T7, at `52448e0`.

**The gap.** `glob` is the one folder read that names no key, so BE-032 A.5 can
only approximate it ("over its pattern's literal prefix"). The kernel's `glob`
catches only `NotFound`, so a refusal through an item propagates where every
listing answers empty, and `test_condition_space.py` asserts that (T7). The
shared `pattern_to_regex`, called at 7 sites including `ext/glob.py`'s fallback,
lets a trailing `**` and a character class cross `/`, reads `[^x]` as negation,
and raises `re.PatternError` on a malformed class; fallback and native Local
disagree on one tree (T8).

**What it decides** (audit-023 P2, advisory): a defining clause, `glob(p)` as
the files of the tree whose path matches `p`, with the kernel's prefix listing
and probes judged against it, which settles T7's open question (kernel follows
A.5/A.8, or A.5 narrows); then one dialect: classes and `/`, `^`, `**` as a
whole segment only, the malformed-pattern error type, and `\`.

- **(was BK-447, absorbed here)** A glob pattern reads `\` unlike a path:
  `exists("d\\a.csv")` is `True`, `glob("d\\*.csv")` is `[]`. PATH-002 turns `\`
  into `/` in a path, but GLOB-007's normalisation keeps it, so both tiers answer
  `[]` (measured on Local and Memory), and a kernel `GLOB` driver would raise
  `InvalidPath` (BE-030's pattern rule). In a glob `\` is also a natural escape.
  Its open decision, convert, refuse or escape, is one row of this dialect.

**Overlaps:** BK-439 (the flat rules of kernel `glob`: an ordering obligation or a
buffered omission) is a separate decision; BK-446 gives Memory `SupportsGlob`,
which then runs this definition.

**Due:** before RFC-0017 D3 step 2: `S3Boto3Backend` declares `GLOB`
(`_s3_boto3.py:88`) and globs through `pattern_to_regex` (`:809`).

*Re-scoped 2026-10-25 ([RFC-0025](../rfcs/rfc-0025-freeze-kernel-line.md)): the kernel and
BE-032 left master, so T7 (the kernel's `glob` raising where listings answer empty) and the
kernel `GLOB` driver's `InvalidPath` above are frozen with them, as are the D3-step due date
and the BK-439 and BK-446 overlaps (both absorbed into BK-489). What stays is the shared
`pattern_to_regex` against native Local glob (T8) and a defining clause for `glob` over the
tree.*
