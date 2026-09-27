# BUG-260 — `SQLBlobBackend.list_files("./")` answers empty for a non-empty root
<!-- doc: repo-only -->

Moved verbatim from [`BACKLOG.md` § 2](../BACKLOG.md#correct-and-proven) by the ADR-0040 § 2
conversion, links re-based to this directory. The index entry holds the current
diagnosis; this file is evidence and advisory prescription
([§ Item authority](../BACKLOG.md#how-this-file-works)).

Measured on a root holding two files: `exists("./")` is `True`, `is_folder("./")`
is `True`, and `list_files("./", recursive=True)` returns **zero** entries —
where `""` and `"."` both return two. So the probes agree the folder is there
and the listing comes back empty, which is worse than either answering
consistently. `LocalBackend` and `MemoryBackend` answer `True / True / 2` under
all three spellings, so this is not the shared read-side behaviour.
The cause is the listing prefix: `is_root` recognises only `""` and `"."`, so
`"./"` falls through to the non-root branch and becomes the LIKE prefix
`'./%'`, which matches no stored key. The probes do not use that branch.
**Not fixed by widening `is_root`**, which has 52 call sites across 13 files
including `native_path` / `to_key` — BE-008's asymmetry paragraph explains why
that is a spec-amendment-class change rather than a local fix. The local fix is
in the prefix construction, and the general question — whether the read side
owes the wider predicate at all — is the one BE-008 currently answers "no" to
on the strength of the cost being an error class. This item is the
counterexample to that reasoning and should be read alongside it.
Found by the closing gate of BUG-259, which guarded the write side under the
wider predicate and left the read side stated but unmeasured.
