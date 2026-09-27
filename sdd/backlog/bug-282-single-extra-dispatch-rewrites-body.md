# BUG-282 — A single-extra drift-guard dispatch rewrites the rolling issue body to that extra alone
<!-- doc: repo-only -->

Moved verbatim from [`BACKLOG.md` § 5](../BACKLOG.md#no-release-surprises) by the ADR-0040 § 5
conversion, links re-based to this directory. The index entry holds the current
diagnosis; this file is evidence and advisory prescription
([§ Item authority](../BACKLOG.md#how-this-file-works)).

`scripts/drift_report.py` composes the issue body from whichever reports the
run produced (`_load_reports` at line 33, `_render_body` at line 46) and, when
any of them carries a signal, replaces the open issue's body wholesale with
`gh issue edit --body-file -` (lines 200 to 210). `drift-guard.yml` accepts a
single extra on `workflow_dispatch`, and that path emits one report. So a
dispatch with `extra=sftp` rewrites the rolling issue to an sftp-only body, and
the other extras' rows are gone until the next scheduled run.
Those rows are load-bearing: `infra/drift-locks/README.md` § Refreshing route 1
reconstructs each lock from them, and a sandboxed session has no other route
(trace finding #30). The 2026-09-07 firing hit this while deciding how to
re-run a red `check-sftp`: the only safe re-run was the full matrix, which
re-resolves every extra and moved two packages (aiobotocore, botocore in
`[s3]` / `[s3-pyarrow]`) between the scheduled run and the re-run.
`mutation.yml` already carves this out — `sdd/CI-OPERATIONS.md` § mutation:
"a single-scope dispatch never closes it or rewrites its body (its findings
land as comments)". drift-guard is the reference guard for the rolling-issue
pattern and lacks the same rule. Fix shape: on a partial matrix, comment the
per-extra result on the issue rather than editing the body, or merge the new
report into the existing body's other sections; either must keep the
"regenerated every run, auto-closes on clear" contract for the full matrix.
