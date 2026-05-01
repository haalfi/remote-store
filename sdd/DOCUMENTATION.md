# Documentation Standards

## Intent & Scope

Authoritative source for documentation structure and standards. Governs the shape and quality of all docs work: new pages, restructuring, and reviews.

Part of the documentation framework (see `CLAUDE.md` § Documentation framework): placement → `sdd/AUTHORING.md`; longevity → `sdd/CONTENT-RULES.md`.

## Rules

### 1. Diataxis placement

Every user-facing documentation page belongs to exactly one category:

1. "The reader wants to **learn**" --> Tutorial.
2. "The reader wants to **accomplish a task**" --> Guides.
3. "The reader wants to **look something up**" --> Reference.
4. "The reader wants to **understand why**" --> Explanation.
5. If unsure, it is probably a Guide.

Pages that try to be two things at once must be split.

### 2. Content homes

| Content type | Source location | Readable on GitHub? |
|---|---|---|
| Project intro, install, quick start | `README.md` | Yes |
| How-to guides | `docs-src/how-to/` | Yes |
| Explanation pages | `docs-src/explanation/` | Yes |
| Reference pages | `docs-src/reference/` | Yes |
| Further reading | `docs-src/further/` | Yes |
| Runnable examples | `examples/` | Yes |
| API docstrings | `src/` (Python source) | Yes |
| Specs, ADRs, RFCs, research, audits | `sdd/` | Yes |
| Contributor workflow | `CONTRIBUTING.md` | Yes |
| Release history | `CHANGELOG.md` | Yes |
| Development narrative | `DEVELOPMENT_STORY.md` | Yes |
| Site-specific pages, nav, templates | `docs-src/` | Yes |

**Decision rule:** If it makes sense on GitHub without MkDocs, it goes in a source directory. If it only makes sense on the docs site, it goes in `docs-src/`. All user-facing prose now lives directly in `docs-src/` Diátaxis buckets.

New user-facing prose pages follow the Diátaxis bucket structure under `docs-src/`:
- How-to guides go in `docs-src/how-to/` (backend-specific guides in `docs-src/how-to/backends/`).
- Explanation pages go in `docs-src/explanation/`.
- Reference pages go in `docs-src/reference/`.

Site-only artefacts (nav files, MkDocs-only includes) stay in `docs-src/` alongside the prose.

### 3. Docstring completeness

Format and style rules are in `sdd/DESIGN.md` § 4. This section covers what mkdocstrings requires per symbol type:

| Symbol | `Args` | `Returns` | `Raises` | Example |
|---|---|---|---|---|
| Public method | Yes | Yes | Yes | Yes (short) |
| Property | — | Yes (in summary) | If applicable | Optional |
| Class | Yes (`__init__` params) | — | — | Yes |
| Function | Yes | Yes | Yes | Yes |
| Enum | — | — | — | — |
| Error class | — | — | — | — |

Supplementary context that does not fit Args/Returns/Raises goes in a `Notes:` block, not scattered inline or appended to the summary line.

Use ``Example:`` (not ``Usage:``) for code snippets in docstrings. In class/function
docstrings, mkdocstrings renders ``Example:`` as a collapsible box. For module-level
docstrings, use MkDocs admonition syntax: ``!!! example`` with indented code blocks
(Google sections don't parse in module docstrings).

No TODOs or placeholders in published docstrings.

### 4. Cross-linking requirements

Two published sites exist. Use the right one depending on what you link to:

- **Documentation** (guides, API reference, explanation pages): link to ReadTheDocs (`https://docs.remotestore.dev/stable/`). Use `/stable/` (not `/latest/`) so links always point to the most recent release, not unreleased master. The `/en/` language prefix is omitted (single-language project, configured in RTD URL scheme).
- **Source files** (specs, ADRs, examples, source code, CHANGELOG): link to the GitHub repository (`https://github.com/haalfi/remote-store/`).

Within the docs site, always use relative links.

Required cross-links:

| From | To | How |
|---|---|---|
| Guide --> API method it uses | API reference page | `[Store.read()](../api/store.md#remote_store.Store.read)` |
| Guide --> example script | Examples page | `[example](../examples/file-operations.md)` |
| API method --> guide that explains it | Guide page | In docstring: `See the [Streaming Guide](...)` |
| Error class --> methods that raise it | API reference | In error docstring "Raised by" section |
| Backend guide --> capabilities | Capabilities matrix | Link to matrix row |
| Example page --> guide for deeper reading | Guide page | Footer link |
| Table header/key-column --> documented entity | Guide or API reference page | `[Local](backends/local.md)` |

Minimum per page:

- Every how-to guide links to at least one API reference page.
- Every how-to guide links to its matching example script (if one exists).
- Every API class page links to its primary guide.

### 5. PR documentation review

The SDD workflow includes a DOCS step (see `sdd/000-process.md` rule 6). When reviewing PRs, check:

- Docstrings meet rule 3 for all new/changed public symbols
- Relevant guide updated (if behavior changed)
- Example updated or added (if user-facing)
- CHANGELOG stub present (one line per completed item — see ripple-check table **CHANGELOG entry**)
- No orphaned cross-links (renamed/removed APIs)

### 6. README requirements

The README must contain:

- Project description (what it does, one paragraph)
- Who it is for (audience list)
- When NOT to use it (scope boundaries)
- Installation instructions (base + extras)
- Minimal working example with expected output
- Store API overview — a short summary with a link to the API reference; not a
  method table (that belongs in the reference docs)
- Supported backends — backend name, install extra, and underlying library;
  capability detail links to `FEATURES.md` and the capabilities matrix
- Link to full documentation site, CHANGELOG, and CONTRIBUTING
- License, supported Python versions, project status badge

### 7. Research document rules

- Research docs live in `sdd/research/` and are named `research-<topic>.md`.
- They are not edited after the related feature ships — they are historical records.
- They may be surfaced on the docs site under Explanation > Research.
- They do not need to follow the docstring or guide quality checklists.

### 8. Typography

- **Prose dashes:** Use `—` (U+2014) sparingly as a parenthetical aside. Default to periods, colons, or commas. Never use `--` as an em dash substitute in documentation prose.
- **Table N/A value:** `—` (U+2014) for any "not applicable / not supported / none" cell. Never `--` or `No`.
- **Preserve `--`:** Only in shell flag syntax inside code blocks, spec-ID ranges (`BATCH-020 -- BATCH-025`), Mermaid edge syntax, `--8<--` snippet includes, and code/SQL comments inside fenced blocks.

### 9. URL alignment

URL paths must correspond to navigation position. A page nested under nav section X has its URL prefix matching X (e.g., a page under Reference > API renders at `/reference/api/...`, not `/api/...`).

## Guides

### Diataxis categories

| Category | Orientation | Goal | Where it lives |
|---|---|---|---|
| Tutorial | Learning | Guided first success | `README.md` Quick Start, `docs-src/getting-started.md`, notebooks |
| How-To Guides | Tasks | Answer "how do I X?" | `docs-src/how-to/` |
| Reference | Information | Precise lookup | Python docstrings in `src/`, extracted into `docs-src/api/`; prose reference pages in `docs-src/reference/` |
| Explanation | Understanding | Help understand *why* | `docs-src/explanation/` for user-facing pages, `sdd/adrs/` for formal decisions |

### Content drift prevention

Each Diataxis category excludes specific content types. When a page accumulates excluded content, split it.

| Category | Must exclude |
|---|---|
| Tutorial | Exhaustive option lists, edge cases, design rationale |
| How-To Guide | Design rationale, conceptual background, exhaustive option tables |
| Reference | Narrative explanation, step-by-step instructions |
| Explanation | How-to instructions, API signatures, install steps |

Cross-references replace duplication, but actionable checklists should be co-located with the rules they support. When condensing, keep lookup tables near the decision point.

### Cross-link example

| From | To | Link pattern |
|---|---|---|
| `docs-src/how-to/cache.md` | `ext.cache` API | `[CachedStore](../api/ext/cache.md)` |
| `Store.read` docstring | Streaming guide | `See the [Streaming Guide](...)` |
| `docs-src/how-to/backends/s3.md` | Capabilities matrix | `[Capabilities](../../reference/capabilities-matrix.md)` |

### API page building blocks

Reusable structural blocks for `docs-src/api/` pages. `store.md` is the
canonical example. Apply the appropriate page-type template (see below) and
compose from these blocks.

#### Admonition vocabulary

Three levels, applied consistently across all `docs-src/api/` pages:

| Level | When to use | Title pattern |
|-------|-------------|---------------|
| `!!! info` | Pure context — helpful to know, no runtime consequence | Free-form (e.g. "Thread safety", "Ordering and laziness") |
| `!!! note` | Be aware — raises `CapabilityNotSupported` or behavior varies predictably | `Requires Capability.X` · `Backend-conditional argument: param=` |
| `!!! warning` | Backend coupling — ties code irrevocably to a specific backend | `Backend-specific methods` (section header only) |

Rules:
- `Requires Capability.X` and `Backend-conditional argument: param=` are both `!!! note` — both result in predictable `CapabilityNotSupported` when the capability is absent.
- `!!! warning "Backend-specific methods"` is used only as a section/group header, not on individual methods.
- Title fragment must be identical for the same pattern across all files (colon, no em dash, backtick-quoted param names).

#### Blocks

**Class header** — renders the class summary only; methods follow in explicit
sections.

```markdown
::: remote_store.ClassName
    options:
      members: false

!!! info "Key behavioral fact"
    One-sentence callout for a fact that callers must know before reading
    any method (e.g. thread safety, context-manager usage, immutability).
```

**Method section** — groups related methods under a heading; each method gets
its own directive so admonitions can be inserted between them.

```markdown
## Section Name

::: remote_store.ClassName.method_one
    options:
      show_root_heading: true
      heading_level: 3

!!! note "Requires `Capability.X`"
    Raises `CapabilityNotSupported` on backends that do not declare this capability.

::: remote_store.ClassName.method_two
    options:
      show_root_heading: true
      heading_level: 3
```

**Info note** — pure context; helpful to know, no runtime consequence.

```markdown
!!! info "Ordering and laziness"
    Short, concrete statement. One or two sentences max.
```

**Constraint note** — capability gate or argument that changes capability requirements.

```markdown
!!! note "Requires `Capability.X`"
    Raises `CapabilityNotSupported` on backends that do not declare this capability.
```

```markdown
!!! note "Backend-conditional argument: `param=`"
    Passing `param` raises `CapabilityNotSupported` on backends that do not
    declare `Capability.X`. Passing `None` or the default is safe on all backends.
```

**Warning block** — backend coupling: ties code irrevocably to a specific backend.

```markdown
!!! warning "Backend-specific methods"
    Methods in this section expose backend internals. Using them ties your
    code to a specific backend. For portable alternatives, use the methods
    above.
```

**Backend behavior matrix** — cross-backend comparison table; only include
when behavioral variation is significant enough to warrant a lookup table.

```markdown
## Backend Behavior Matrix

| Behavior | [Local](../backends/local.md) | [S3](../backends/s3.md) | ... |
|----------|-------------------------------|-------------------------|-----|
| Row description | value | value | ... |

Verify against actual code before relying on these in production.
```

**Related types** — inline footer line linking to companion types.

```markdown
**Related types:** [`TypeA`](models.md), [`TypeB`](capabilities.md).
```

**See also** — footer section; every API page requires at least one entry
(its primary guide or a matching example).

```markdown
## See also

- [Guide name](../guide-path.md) — one-line description
- [Example name](../examples/example-path.md) — one-line description
```

#### Page-type templates

| Page type | Required blocks | Optional blocks |
|---|---|---|
| **Rich class** (Store, AsyncStore) | Class header, Method sections, See also | Info notes, Constraint notes, Warning block, Behavior matrix, Related types |
| **Protocol / ABC** (Backend) | Class header, Method sections, See also | Info notes, Constraint notes |
| **Support class** (ProxyStore, Registry, Config, Models, RemotePath, Info, SFTPUtils) | Intro prose or class header, `:::` (all members), See also | Info notes, Constraint notes |
| **Enum / flags** (Capability, CapabilitySet) | `:::` per type, See also | — |
| **Error hierarchy** (Errors) | Flat `:::` per error class, See also | — |

**Intro prose** (support classes) — one short paragraph before the `:::`
directive when the class needs orientation that does not fit in the docstring
(e.g. design rationale, relationship to other classes). Keep it under 4
sentences; link to an ADR for deeper background.
