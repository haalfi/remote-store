# Audit 009 — Backend-Specifics Visibility in Reference

**Date:** 2026-04-21
**Scope:** All API reference pages under `docs-src/api/` and the docstrings
they render from in `src/remote_store/`. Excludes guides and explanation
pages — they are surveyed only when the reference is the source.
**Method:** Walked every reference page section by section, then
cross-checked each rendered symbol against its source for capability gates,
backend-specific behaviour, or backend-shaped data. The reference template
is `Store.unwrap` (`docs-src/api/store.md:211-241`): a dedicated section
(`## Interop (Backend-Specific)`) opened with a `!!! warning` admonition.
The audit asks: *for every other place a user can stumble into
backend-specific behaviour, is the signal as visible as it is for
`unwrap`?*

---

## Premise

Backend-specifics appear in the reference at five granularities, not just
methods:

| Granularity | Example | Visibility today |
|-------------|---------|------------------|
| Whole method | `Store.unwrap` | ✅ section + warning admonition |
| Whole class / module | `SFTPUtils`, `backends/*` | ❌ inferred from page name only |
| Public field / property | `WriteResult.etag`, `FileInfo.extra`, `ResolutionPlan.details` | ❌ buried in attribute description |
| Method argument | `Store.write(metadata=…)`, `Store.list_files(max_depth=…)` | ❌ mentioned in prose only |
| Capability-gated method as a whole | `Store.glob`, `Store.write_atomic`, `Store.head` | ❌ "Requires Capability.X" line in docstring only |

The reader who scans the reference for the same `!!! warning` styling that
`unwrap` carries will not find these. They have to read every docstring
to discover what couples them to a specific backend or capability.

---

## Summary

| Category | Count | Severity |
|----------|-------|----------|
| A — Interop methods missing the warning admonition (parity with `Store.unwrap`) | 6 | High |
| B — Capability-gated whole methods, gate buried in docstring prose | 5 | Medium |
| C — Capability-gated arguments, gate buried in argument prose | 2 | Medium |
| D — Public fields whose value/presence is backend-conditional | 4 | Medium |
| E — Whole classes / modules that are backend-specific by nature, no top-of-page admonition | 3 | Low |
| **Total** | **20** | |

Pattern: the reference *describes* backend-specifics in prose almost
everywhere, but the visual signal that calls out *"this is the place to
slow down"* exists in exactly one location. The fix is consistent visual
flagging (admonitions, badges, dedicated sections) at every granularity
above.

---

## Findings

### Category A — Interop methods missing the warning admonition

`store.md:211-241` groups three backend-coupling methods (`unwrap`,
`native_path`, `to_key`) under a single `!!! warning` admonition, then
documents `supports()` in the same section with a distinguishing `!!!
note` clarifying that **`supports()` is portable** — it works on every
backend; only the capability-gated methods it guards are backend-
specific. Category A is about the three-method coupling trio; where
`supports()` appears, the fix is to carry over the portable-method note,
not the backend-specific warning.

**Source-level region tag inconsistency (applies to all findings in
this category):** both `src/remote_store/_store.py:812` and
`src/remote_store/aio/_async_store.py:785` mark the same block
`# region: interop (backend-specific)` and include `supports()` inside
that block. The source label directly contradicts the `store.md:238-241`
portable-method note. Closing any Category A finding entails deciding
whether to extract `supports()` from the region tag, or to rename the
tag (e.g. `# region: interop`). The audit does not prescribe which — it
flags the inconsistency so the implementer resolves it once, not three
times.

#### A-1 — `aio.md` AsyncStore — interop methods entirely hidden

**File:** `docs-src/api/aio.md:11-13`
**Severity:** High

`AsyncStore` is rendered with `members: false`. The interop block at
`src/remote_store/aio/_async_store.py:787-869` is not in the rendered
reference at all. Async users get *less* visibility than sync users, not
the same. Two distinct visibility gaps nested in this one finding:

- The **coupling trio** (`unwrap`, `native_path`, `to_key`) needs the
  same `!!! warning "Backend-specific methods"` admonition that
  `store.md:211-241` carries.
- `supports()` needs the same `!!! note` clarifying that *it* is
  portable — mirroring `store.md:238-241`. Without this, an implementer
  working off BK-153's exit criteria might apply the warning to
  `supports()` and contradict the sync-Store docs.

The source-level region tag inconsistency noted above must also be
resolved as part of the fix.

#### A-2 — `aio.md` AsyncBackend — no Interop section, no admonition

**File:** `docs-src/api/aio.md:19-20`
**Severity:** High

`AsyncBackend` renders all members. `unwrap`, `native_path`, `to_key` at
`_async_backend.py:335-402` appear in the rendered output ungrouped and
unflagged. Mirrors A-3 below.

#### A-3 — `backend.md` — `unwrap` under "Lifecycle"; `to_key`/`native_path` under "Introspection"

**File:** `docs-src/api/backend.md:171-179, 195-198`
**Severity:** High

`unwrap` is listed next to `close()` and `check_health()`. `to_key` and
`native_path` are filed under "Introspection" with the portable
`resolve()`. No admonition warns that `unwrap` returns a backend-native
client with no stability guarantees from `remote-store`, or that
`to_key`/`native_path` produce backend-shaped strings.

#### A-4 — `proxy.md` — `ProxyStore` re-exposes interop methods unflagged

**File:** `docs-src/api/proxy.md:13`; source `src/remote_store/_proxy.py:237-250`
**Severity:** Medium

`ProxyStore` redeclares `unwrap`, `native_path`, `to_key`, `supports` for
delegation and renders them with default `mkdocstrings` options. The
coupling trio (`unwrap`, `native_path`, `to_key`) renders without the
`!!! warning` admonition; `supports()` renders without the portable-
method note. Same distinction as A-1 applies.

#### A-5 — `backends/http.md` — `unwrap`, `native_path`, `to_key` render without the warning admonition

**File:** `docs-src/api/backends/http.md` (verified against local
`hatch run docs-build` output, 2026-04-21).
**Severity:** Low

Empirical check: of the nine concrete-backend reference pages, **only
`http.md` renders the interop methods as public members**. The other
eight pages render only the class-level signature and class docstring,
because mkdocstrings defaults to `inherited_members: false` and
`S3Backend` / `S3PyArrowBackend` / `SQLBlobBackend` / `SQLQueryBackend`
inherit their `unwrap` from intermediate private base classes
(`_S3Base`, `_SQLAlchemyBaseBackend`), while `LocalBackend`,
`MemoryBackend`, `SFTPBackend`, `AzureBackend` inherit the base
`Backend.unwrap` (a raise) without overriding. None of those overrides
or inherited methods surface in the rendered reference today.

`ReadOnlyHttpBackend` is the only concrete backend that subclasses
`Backend` directly *and* defines all its methods on the subclass — so
its page renders 13 methods including `unwrap`, `native_path`, `to_key`
without a warning admonition. A reader landing on this page from search
sees the interop methods mixed in with `read()`, `is_file()`, etc., with
no visual cue that three of them are escape hatches.

**Scope correction:** the earlier draft of this finding named seven
pages. That was wrong — the visibility gap exists on exactly one page
(`http.md`). The corollary question — whether the other eight pages
*should* render their interop methods with a warning — is a
reference-completeness question out of scope for audit-009 (it would
require enabling `inherited_members` or restructuring the backend class
hierarchy). If raised later, track separately.

#### A-6 — `sftp-utils.md` — SFTP-only module, no top-of-page admonition

**File:** `docs-src/api/sftp-utils.md`
**Severity:** Low

`SFTPUtils`, `load_private_key`, `HostKeyPolicy` all live exclusively in
the SFTP backend. The page title is neutral ("SFTPUtils"); a reader
landing here from a search result has no admonition saying "using these
ties your code to the SFTP backend".

---

### Category B — Capability-gated whole methods, gate buried in prose

These methods raise `CapabilityNotSupported` when the backend does not
declare the gating capability. Today the gate lives only inside the
docstring's `Raises:` block or a single line near the description. There
is no `!!! note "Requires Capability.X"` admonition at the top of the
method's reference entry.

#### B-1 — `Store.glob` requires `Capability.GLOB`

**File:** `docs-src/api/store.md:105-117`; source `_store.py:515-533`
**Severity:** Medium

The docstring contains "Requires `Capability.GLOB`" inline. The rendered
reference shows it only as part of the description text. There is a
`!!! note "Ordering and laziness"` *below* the method but no admonition
*above* it announcing the capability gate.

Sibling pages affected: `backend.md:125-133` (note exists, but only
about being "non-abstract"), `aio.md` (AsyncStore.glob hidden by
`members: false`).

#### B-2 — `Store.write_atomic` and `Store.open_atomic` require `Capability.ATOMIC_WRITE`

**File:** `docs-src/api/store.md:58-71`; source `_store.py:234-323`
**Severity:** Medium

Capability gate appears only in the `Raises:` block. The page-level note
under `write_atomic` ("Most backends implement this as temp-file +
rename") describes mechanism, not the gate. Same pattern on
`backend.md:78-86`.

#### B-3 — `Store.head` requires `Capability.METADATA`

**File:** `docs-src/api/store.md:145-148`; source `_store.py:724-756`
**Severity:** Medium

Gate stated in the docstring's body ("Gated on `Capability.METADATA`
only"). No admonition. Adjacent `get_file_info`/`get_folder_info` are
also METADATA-gated (`_store.py:655, 694`) without admonitions.

#### B-4 — `Store.read`, `read_bytes`, `read_seekable` require `Capability.READ`

**File:** `docs-src/api/store.md:24-42`; source `_store.py:51-119`
**Severity:** Low

The gate is consistent across the read family but never surfaced visually.
Most backends declare `READ`, so users rarely hit it — but read-only
gate awareness matters when mixing in restricted backends.

#### B-5 — `Store.move` / `Store.copy` require `MOVE` / `COPY`; `delete*` require `DELETE`; `list_*` require `LIST`

**File:** `docs-src/api/store.md:76-117, 122-139`; source `_store.py:329-381, 387-533, 539-599`
**Severity:** Low

Same pattern. Existing notes under `move` and `copy` describe atomicity
and metadata behaviour but not the capability gate.

---

### Category C — Capability-gated arguments

Arguments that change the capability requirement of an otherwise-portable
method. Visibility today: the gate is one sentence inside the argument's
description.

#### C-1 — `metadata=` on `Store.write`, `write_text`, `write_atomic` requires `Capability.USER_METADATA`

**File:** `docs-src/api/store.md:46-71`; source `_store.py:154-279`
**Severity:** Medium

The argument is portable when `None` or `{}`, and capability-gated
otherwise. Today the docstring says "Requires `Capability.USER_METADATA`"
inside the `metadata` parameter description; users have to read the
parameter docs in full to find it. There is no per-argument badge or
admonition to flag the conditional gate.

Same on `Backend.write`/`write_atomic` (`_backend.py:179-231`) and the
async equivalents (`aio/_async_store.py`).

#### C-2 — `max_depth=` on `list_files` / `list_folders` / `get_folder_info`: behaviour is backend-conditional

**File:** `docs-src/api/store.md:88-94, 95-98, 170-173`; source `_store.py:387-451, 451-491, 659-722`
**Severity:** Low

The Store-level docstring says the parameter is honoured uniformly, but
the underlying `Backend.list_files` docstring (`_backend.py:280-300`)
says "backends that support native depth limiting prune traversal early.
Backends that ignore this parameter still produce correct results — the
Store applies client-side filtering as a safety net." That backend
divergence (efficient pruning vs. client-side filter) is a quality
signal users may want to surface — currently invisible in the reference.

---

### Category D — Public fields whose value/presence is backend-conditional

Data-class fields documented in `models.md` and `info.md`. Reader sees
attribute names and types in the rendered reference; the
backend-conditional nature lives in attribute prose.

#### D-1 — `WriteResult` — every optional field is backend-conditional

**File:** `docs-src/api/models.md:11`; source `_models.py:105-143`
**Severity:** Medium

`WriteResult.source` is the discriminator (`"native"` / `"basic"` /
`"sidecar"`) that controls which other fields are reliable. `digest`,
`etag`, `version_id`, `last_modified`, `metadata` are all conditional on
`source` and on `Capability.WRITE_RESULT_NATIVE` /
`Capability.USER_METADATA`. The class docstring describes this in
prose. The rendered reference shows attributes as a flat list of
`Optional[X]` types with no visual cue that "if you do not check
`source`, only `path` and `size` are safe to read."

This is the single most user-impactful gap — `WriteResult` is the return
type of every `write*` call, so every `write` user encounters it.

#### D-2 — `FileInfo.etag`, `FileInfo.metadata`, `FileInfo.extra`

**File:** `docs-src/api/models.md:9`; source `_models.py:67-93`
**Severity:** Medium

- `etag` — "Opaque backend-provided tag for change detection." Whether
  it is populated and what it means varies per backend.
- `metadata` — populated only when the backend declares `USER_METADATA`
  and the file actually has metadata.
- `extra` — explicitly typed and documented as "Backend-specific
  metadata." A reader sees `dict[str, object]` without any signal that
  the keys depend on the backend.

#### D-3 — `FolderInfo.extra`, `FolderInfo.modified_at`

**File:** `docs-src/api/models.md:15`; source `_models.py:169-187`
**Severity:** Low

`extra` is "Backend-specific metadata." `modified_at` is `Optional`
because some backends do not track folder mtimes. Same visibility gap.

#### D-4 — `ResolutionPlan.details`, `BackendConfig.options`

**File:** `docs-src/api/models.md:17` and `docs-src/api/config.md:5`;
source `_resolution.py:48` and `_config.py:170`
**Severity:** Low

Both are explicitly documented as backend-specific in the attribute
description. No visual flag at the class or attribute level.

---

### Category E — Whole classes / modules that are backend-specific by nature

#### E-1 — `docs-src/api/sftp-utils.md` — see A-6

#### E-2 — `docs-src/api/backends/*.md` — see A-5

#### E-3 — `Capability` enum — quality flags vs. method gates not visually separated

**File:** `docs-src/api/capabilities.md:3`; source `_capabilities.py:14-121`
**Severity:** Low

The class docstring is well-organised by section ("Core I/O",
"Navigation", …, "Quality flags"). The rendered reference inherits the
section organisation, but the qualitative distinction — "quality flags do
not gate any method; they describe behaviour you must opt into checking"
— is buried mid-paragraph. Users querying `supports(SEEKABLE_READ)` vs.
`supports(GLOB)` may not realise the first is informational while the
second guards an actual call.

---

## Recommended pattern (for the follow-up backlog item)

Apply consistent admonition patterns across the reference. Suggested
vocabulary (to be confirmed at fix time):

| Situation | Pattern |
|-----------|---------|
| Whole method couples to a specific backend (interop) | `!!! warning "Backend-specific method"` — the existing `Store.unwrap` model |
| Method requires a capability the backend may not declare | `!!! note "Requires `Capability.X`"` directly under the method heading |
| Argument flips the method into a capability-gated mode | `!!! note "Capability-gated argument"` adjacent to the argument table, naming the gate and the no-op condition (e.g. `metadata=None`) |
| Field/attribute is backend-conditional | Inline marker in the attribute list (e.g. trailing badge) **plus** a class-level admonition explaining the discriminator (notably `WriteResult.source`) |
| Whole class/module is backend-specific | Top-of-page `!!! warning "Backend-specific module"` — model after `Store.unwrap`'s section warning |

---

## Out of scope

- Guides, examples, and `CHANGELOG`. This audit is reference-only.
- Renaming, restructuring, or moving symbols. Visibility is the goal,
  not API shape changes.
- Capability-matrix re-organisation (`docs-src/capabilities-matrix.md`):
  it is already a dedicated table and visually distinct.

---

## Tracking

Follow-up: see `BK-153` in [BACKLOG.md](../BACKLOG.md). Pairs with
`BK-152` (WriteResult/FileInfo consistency in code), which fixes the
contract this audit's D-1 finding flags as the highest-impact visibility
gap.
