# BUG-289 — Two floors are clean for a user and red for the suite, because the suite rejects warnings
<!-- doc: repo-only -->

Moved verbatim from [`BACKLOG.md` § 5](../BACKLOG.md#no-release-surprises) by the ADR-0040 § 5
conversion, links re-based to this directory. The index entry holds the current
diagnosis; this file is evidence and advisory prescription
([§ Item authority](../BACKLOG.md#how-this-file-works)).

The floor lane runs each extra's existing pytest target, and that target
inherits this repo's `filterwarnings = error`. Two floors therefore fail on
warnings rather than on breakage, which a user at the same versions would
never see as a failure:
- **`[sftp]`, `paramiko==3.1.0`.** `paramiko/pkey.py` reads
  `algorithms.TripleDES`, which current `cryptography` answers with
  `CryptographyDeprecationWarning: TripleDES has been moved to
  cryptography.hazmat.decrepit.ciphers.algorithms.TripleDES and will be
  removed … in 48.0.0`. Collection of `tests/e2e/conftest.py` dies on it.
- **`[s3]`, `s3fs==2024.2.0`.** 1 failed, 272 passed, 16 errors, every error
  `exceptiongroup.ExceptionGroup: multiple unraisable exception warnings`
  from pytest's unraisable plugin against the old aiobotocore session
  teardown.
**Measured** by the floor lane's own fourth dry run on the oldest supported
interpreter; both are registered in `infra/drift-locks/KNOWN-FINDINGS.md` so
they read as known rather than new.
**The strictness is deliberate and is not the defect.** A floor whose
combination with current transitives emits deprecation warnings is a floor
about to break, and the lane holding it to the same bar as every other run of
those tests is what makes that visible early — which is the whole point of
watching the bottom of a range. Relaxing the warning policy for this lane
only would make the floor smoke weaker than the suite it borrows, and would
retire the signal a year before the removal lands.
**So the question this item answers is which floor to raise, not whether to
quieten the lane.** For `[sftp]`: the first paramiko that stopped reaching
the deprecated alias. For `[s3]`: the first `s3fs` whose teardown does not
leave unraisable exceptions under a current `aiobotocore`. Both need the same
install-and-run measurement per candidate release that BUG-283 through
BUG-285 used; neither number should be guessed from a changelog.
**Not** a request to change `filterwarnings`, and not the same class as
BUG-287 / BUG-288, whose floors fail at `import` with no test involved.
