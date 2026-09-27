# BUG-253 — `GraphBackend.write` answers a file-ancestor path differently by payload size
<!-- doc: repo-only -->

Moved verbatim from [`BACKLOG.md` § 1](../BACKLOG.md#predictable-failure) by the ADR-0040 § 1
pilot, links re-based to this directory. The index entry holds the current
diagnosis; this file is evidence and advisory prescription
([§ Item authority](../BACKLOG.md#how-this-file-works)).

`write("blocker.txt/child.bin", …)` raises `InvalidPath` when the body takes
the small `PUT /content` path and `NotFound` when it takes the upload session,
for the identical path against the identical store — the answer depends on
whether the payload crosses `_SMALL_FILE_MAX_SIZE` (4 MiB), which is not
something a caller reasons about.
Cause: `_write_small` runs `_raise_if_file_ancestor(path)` before classifying
its `404` (ID-209/ID-211), and the large path calls `upload_session(...)`
directly with no such walk, so `_create_upload_session`'s `404` goes straight
to the classifier. `write`'s own docstring promises `InvalidPath` "if the path
… descends through a file ancestor" without qualifying by size, so the large
path contradicts it.
Predates BUG-248 — that change aligned the two halves on the absent-drive axis
and left this one — and was found by its round-3 panel while checking both
write halves. The fix is presumably to hoist the ancestor walk to `write`, or
to run it on the session-creation `404` as the small path does; measure which
before choosing, since the walk costs a round trip on a path that has already
failed.
