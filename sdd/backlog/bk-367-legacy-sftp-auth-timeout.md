# BK-367 — The drift guard's only legacy-sftp authentication runs on a 5 s budget after a deliberately failed connection
<!-- doc: repo-only -->

Moved verbatim from [`BACKLOG.md` § 5](../BACKLOG.md#no-release-surprises) by the ADR-0040 § 5
conversion, links re-based to this directory. The index entry holds the current
diagnosis; this file is evidence and advisory prescription
([§ Item authority](../BACKLOG.md#how-this-file-works)).

`tests/e2e/test_sftp_legacy_recovery.py::TestSFTPLegacyRecovery::test_S4_helper_recovers_after_clear`
is the one test in CI that authenticates against the `legacy-sftp` container:
S1b and S3 assert the key exchange *fails*, the BK-200 scan test reads the
banner only, and `ci.yml`'s `e2e` job never builds that container (its
`start-backends` step brings up the modern sftp service only), so S4 runs
solely in `drift-guard.yml`'s `[sftp]` smoke. `_try_connect` gives it
`auth_timeout=5` (line 73), and S4 issues it as the second connection to the
server, immediately after the first was refused at kex.
Measured: drift-guard run 34127228028 (`check-sftp` job 101758669627) failed S4
with `AuthenticationException: Authentication timeout` after the helper had
re-added ssh-rsa and the key exchange had succeeded; the same pins passed S4 in
run 33405694982 (2026-08-31) and in the re-run 34163916944 the same day. One
red weekly guard cost a full-matrix re-run (BUG-282 explains why it could not
be a single-extra one).
Shape: a bounded retry on the auth phase, or a wider `auth_timeout` for this
probe, with the legacy `sshd` config in `infra/legacy-sftp/Dockerfile` checked
for reverse-DNS or PAM delay that a runner could pay. Not a change to
`SFTPUtils.enable_ssh_rsa_compat()`, which the run shows working.
