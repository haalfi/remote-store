# Documentation Standards

## Intent & Scope

Authoritative source for documentation structure, standards, and placement rules for `remote-store`. Governs all docs work: new pages, restructuring, and reviews.

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
| User-facing guides | `guides/` | Yes |
| Runnable examples | `examples/` | Yes |
| API docstrings | `src/` (Python source) | Yes |
| Specs, ADRs, RFCs | `sdd/` | Yes |
| Research documents | `sdd/research/` | Yes |
| Contributor workflow | `CONTRIBUTING.md` | Yes |
| Release history | `CHANGELOG.md` | Yes |
| Development narrative | `DEVELOPMENT_STORY.md` | Yes |
| Site-specific pages, nav, templates | `docs-src/` | No (site only) |

**Decision rule:** If it makes sense on GitHub without MkDocs, it goes in a source directory. If it only makes sense on the docs site, it goes in `docs-src/`.

New how-to guides always go in `guides/`. New explanation pages that synthesize content from multiple sources go in `docs-src/`.

### 3. Docstring completeness

Format and style rules are in `sdd/DESIGN.md` § 4. This section covers what mkdocstrings requires per symbol type:

| Symbol | `:param:` | `:returns:` | `:raises:` | Example |
|---|---|---|---|---|
| Public method | Yes | Yes | Yes | Yes (short) |
| Property | -- | Yes (in summary) | If applicable | Optional |
| Class | Yes (`__init__` params) | -- | -- | Yes |
| Function | Yes | Yes | Yes | Yes |
| Enum | -- | -- | -- | -- |
| Error class | -- | -- | -- | -- |

No TODOs or placeholders in published docstrings.

### 4. Cross-linking requirements

Two published sites exist. Use the right one depending on what you link to:

- **Documentation** (guides, API reference, explanation pages): link to ReadTheDocs (`https://docs.remotestore.dev/`).
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

Minimum per page:

- Every how-to guide links to at least one API reference page.
- Every how-to guide links to its matching example script (if one exists).
- Every API class page links to its primary guide.

### 5. PR documentation review

The SDD workflow includes a DOCS step (see `sdd/000-process.md` rule 6). When reviewing PRs, check:

- Docstrings meet rule 3 for all new/changed public symbols
- Relevant guide updated (if behavior changed)
- Example updated or added (if user-facing)
- CHANGELOG entry present
- No orphaned cross-links (renamed/removed APIs)

### 6. README requirements

The README must contain:

- Project description (what it does, one paragraph)
- Who it is for (audience list)
- When NOT to use it (scope boundaries)
- Installation instructions (base + extras)
- Minimal working example with expected output
- Store API overview (method table or summary)
- Supported backends table
- Link to full documentation site, CHANGELOG, and CONTRIBUTING
- License, supported Python versions, project status badge

### 7. Research document rules

- Research docs live in `sdd/research/` and are named `research-<topic>.md`.
- They are not edited after the related feature ships -- they are historical records.
- They may be surfaced on the docs site under Explanation > Research.
- They do not need to follow the docstring or guide quality checklists.

## Guides

### Diataxis categories

| Category | Orientation | Goal | Where it lives |
|---|---|---|---|
| Tutorial | Learning | Guided first success | `README.md` Quick Start, `docs-src/getting-started.md`, notebooks |
| How-To Guides | Tasks | Answer "how do I X?" | `guides/` (readable on GitHub, wrapped into site via `docs-src/`) |
| Reference | Information | Precise lookup | Python docstrings in `src/`, extracted into `docs-src/api/` |
| Explanation | Understanding | Help understand *why* | `docs-src/` for user-facing pages, `sdd/adrs/` for formal decisions |

### Content drift prevention

Each Diataxis category excludes specific content types. When a page accumulates excluded content, split it.

| Category | Must exclude |
|---|---|
| Tutorial | Exhaustive option lists, edge cases, design rationale |
| How-To Guide | Design rationale, install steps, API signatures |
| Reference | Narrative explanation, step-by-step instructions |
| Explanation | How-to instructions, API signatures, install steps |

Cross-references replace duplication, but actionable checklists should be co-located with the rules they support. When condensing, keep lookup tables near the decision point.

### Cross-link example

| From | To | Link pattern |
|---|---|---|
| `guides/cache.md` | `ext.cache` API | `[CachedStore](../api/ext/cache.md)` |
| `Store.read` docstring | Streaming guide | `See the [Streaming Guide](../guides/streaming.md)` |
| `guides/backends/s3.md` | Capabilities matrix | `[Capabilities](../capabilities-matrix.md)` |
