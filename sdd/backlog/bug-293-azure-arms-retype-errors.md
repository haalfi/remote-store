# BUG-293 — Sixteen Azure `except Exception` arms re-type an already-typed error, so a closed store reports the base class
<!-- doc: repo-only -->

Moved verbatim from [`BACKLOG.md` § 1](../BACKLOG.md#predictable-failure) by the ADR-0040 § 1
pilot, links re-based to this directory. The index entry holds the current
diagnosis; this file is evidence and advisory prescription
([§ Item authority](../BACKLOG.md#how-this-file-works)).

`classify_azure_error` has no `RemoteStoreError` pass-through arm: it falls
through every `isinstance` check to `return RemoteStoreError(str(exc), ...)`.
So any `except Exception` that routes through it **downgrades an error the
library already typed**, and the first thing inside several of those `try`
blocks is a lazy client accessor whose `_raise_if_closed()` raises
`BackendUnavailable`. Measured on BUG-254's branch before its own two sites
were fixed: `AzureBackend(hns=True).close()` then `get_folder_info("")`
returned `RemoteStoreError: Azure backend is closed` where the flat arm, whose
catch is narrowed to `ResourceNotFoundError`, returned `BackendUnavailable`.
Both Azure classes, sync and async.
**BUG-254 fixed its own two sites and this is the rest of the class.**
Derivation — an AST pass over the two Azure backend files selecting every bare
`except Exception` whose handler *calls* `_classify` or `classify_azure_error`,
then excluding the two `get_folder_info` arms BUG-254 closed and the two
`_errors` context managers, which are the mappers themselves and correctly
re-raise `RemoteStoreError` first. **Sixteen: seven sync, nine async.**
`_azure.py` in `delete`, `delete_folder`, `list_files`, `list_folders`,
`iter_children`, `detect_hns`, `adetect_hns`; and `aio/backends/_azure.py` in
`read`, `delete`, `delete_folder`, `list_files` (two arms), `list_folders`
(two), `iter_children` (two).
**The pass has to read the handler body rather than a window around it.** A
grep for the classifier name near an `except Exception` also matches
`_azure.py`'s `readinto`, whose handler re-raises `OSError(str(exc))` and only
*mentions* the classifier in a comment explaining that `_ErrorMappingStream`
does the classifying later. That site is not in the class and is not in the
sixteen — and that grep spelling is how this item was first filed at nine.
**Not every arm is reachable with a typed error in hand**, which is the work:
each one needs its own answer to "what already-typed error can arrive here",
and the listing arms are the ones whose `try` opens on a guarded accessor the
way `get_folder_info`'s did. The fix shape is `except RemoteStoreError: raise`
ahead of the broad arm, matching `_errors`; the question is which arms need it
and what pins each.
**Why the class is worth closing rather than the instances.** BE-021's
never-leak invariant is about native errors escaping; this is the mirror —
a mapped error being re-mapped to something weaker — and no gate sees it,
because the result is still a `RemoteStoreError`. It sits beside BUG-276,
which owns the other half of error-class fidelity on this surface (a mapped
error reaching the caller with an empty message).

## Correction, 2026-09-26

The count of sixteen above includes four arms that already re-raise
`RemoteStoreError` ahead of the broad arm, so they cannot downgrade:
`aio/backends/_azure.py`'s `read`, and the outer arms of its `list_files`,
`list_folders` and `iter_children` (the `try` each listing opens with).
Their pass-through arms date from `165bd00` (BK-356, 2026-08-29), before
this item was filed, so the count was high when written. **Twelve** arms lack
one: the seven sync arms listed above, and the async `delete`,
`delete_folder` and the inner arms of `list_files`, `list_folders` and
`iter_children` (the `try` around the HNS `get_paths` loop, under
`if self._hns:  # pragma: no cover`). Derivation: the same AST pass, also
printing each `try`'s sibling handlers; an arm whose `try` catches
`RemoteStoreError` first is excluded. Found by the ADR-0040 § 1 pilot, which
re-derived the figure before writing the index diagnosis.
