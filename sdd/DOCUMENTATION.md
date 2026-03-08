# Documentation Master

Authoritative guide for writing, organizing, and maintaining documentation
for `remote-store`. All docs work -- new pages, restructuring, reviews -- is
governed by this document.

Supersedes ad-hoc decisions. When in doubt, consult this file.

---

## 1. Goals

Documentation is successful when:

1. A **new user** installs the package and runs a working example in under
   10 minutes.
2. A **returning user** finds the answer to "how do I do X?" in one click.
3. An **advanced user** looks up exact API behavior (params, types, errors,
   defaults) without reading source code.
4. A **contributor** understands design decisions and knows where to put
   new content.
5. Everything is **accurate at every commit** -- docs match the code that
   ships with them.

---

## 2. Structure -- Diataxis adapted to remote-store

All user-facing documentation falls into exactly one of four categories.
Every page in the docs site belongs to one category. Pages that try to be
two things at once must be split.

### 2.1 Tutorial (learning-oriented)

**Goal:** guided first success, not completeness.

| What to include | What to avoid |
|---|---|
| Installation | Exhaustive option lists |
| Minimal working example with expected output | Backend-specific setup |
| One short walkthrough (write, read, list) | Design rationale |
| Link to next steps | Edge cases |

**Where it lives:** `README.md` (Quick Start) + `docs-src/getting-started.md`
+ tutorial notebooks in `examples/notebooks/`.

### 2.2 How-To Guides (task-oriented)

**Goal:** answer "how do I accomplish X?" for a user who already knows the
basics.

Each guide:

- Starts with a one-sentence statement of what the reader will accomplish.
- Assumes the reader has completed the tutorial.
- Shows working code, not pseudo-code.
- Links to the API reference for every class/function it uses.
- Links to the relevant example script where one exists.
- Ends with next steps or related topics.

**Where they live:** `guides/` (standalone Markdown, readable on GitHub).
Wrapped into the site via `docs-src/` include directives.

**Required guides** (minimum set for a complete docs site):

- One guide per backend (configuration, credentials, connection)
- One guide per extension module (usage, options, error handling)
- Troubleshooting / FAQ (common errors, installation issues, platform quirks)
- Migration guide (breaking changes between versions, upgrade paths)
- Choosing a backend (decision tree, trade-offs, feature comparison)

### 2.3 Reference (information-oriented)

**Goal:** precise, complete, lookup-optimized. Not narrative.

Reference pages document every public symbol with:

- Parameters (name, type, default)
- Return type
- Exceptions raised (which ones, when)
- Side effects
- Thread safety notes (where relevant)
- Code example (short, realistic, runnable)

**Where it lives:** Python docstrings in `src/` extracted by mkdocstrings
into `docs-src/api/` pages.

**What belongs in Reference:**

- Every public class, method, function, property, and constant
- Every public enum and its values (e.g., Capability enum)
- Every error class (when raised, by which methods)
- Every extension module's public API
- A capabilities matrix (backends x capabilities)

### 2.4 Explanation (understanding-oriented)

**Goal:** help the reader understand *why*, not *how*.

Typical topics:

- Architecture (Store / Registry / Backend layering)
- Design decisions and trade-offs (distilled from ADRs)
- Performance characteristics and benchmarks
- Concurrency model and thread safety
- Security model and credential handling
- Limitations and scope boundaries
- How it compares to alternatives

**Where it lives:** `docs-src/` for user-facing explanation pages that
synthesize content from multiple ADRs/specs. `sdd/adrs/` for the formal
decision records themselves.

---

## 3. Navigation Structure

The docs site navigation must reflect the four Diataxis categories.
Users should be able to identify which section they need from the top-level
nav without scanning individual page titles.

### Target layout

```yaml
- Home: index.md
- Getting Started:
    - Tutorial: getting-started.md
    - Examples: examples/
- Guides:
    - Backends: backends/
    - Extensions and feature guides (one entry per guide)
    - Troubleshooting: troubleshooting.md
    - Migration: migration.md
- Reference:
    - API: api/            # core + extensions
    - Capabilities Matrix: capabilities-matrix.md
    - Changelog: changelog.md
- Explanation:
    - Architecture Overview: architecture.md
    - Performance: performance.md
    - Concurrency: concurrency.md
    - Security Model: security-model.md
    - Design: design/      # specs, ADRs, RFCs
    - Research: research/  # exploratory studies
- Contributing: contributing.md
- Further Reading: further-reading.md
```

### Placement rules

1. "The reader wants to **learn**" --> Tutorial.
2. "The reader wants to **accomplish a task**" --> Guides.
3. "The reader wants to **look something up**" --> Reference.
4. "The reader wants to **understand why**" --> Explanation.
5. If unsure, it is probably a Guide.

---

## 4. Content Homes (from ADR-0007)

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

**Decision rule:** If it makes sense on GitHub without MkDocs, it goes in a
source directory. If it only makes sense on the docs site, it goes in
`docs-src/`.

New how-to guides always go in `guides/`. New explanation pages that
synthesize content from multiple sources go in `docs-src/`.

---

## 5. Docstring Standard

Every public symbol (class, method, function, property) must have a
docstring that mkdocstrings can extract into useful reference docs.

### Format

Google-style docstrings (configured in mkdocstrings).

```python
def read(self, path: str) -> BinaryIO:
    """Read a file and return a binary stream.

    The caller is responsible for closing the returned stream.

    Args:
        path: Logical path relative to the store root.
            Must not be empty or contain path traversal (``..``).

    Returns:
        A readable binary stream positioned at the start.

    Raises:
        NotFound: If the file does not exist.
        InvalidPath: If *path* is empty or invalid.
        BackendUnavailable: If the backend cannot be reached.

    Example:
        ```python
        stream = store.read("data/report.csv")
        content = stream.read()
        stream.close()
        ```
    """
```

### Required sections by symbol type

| Symbol | Args | Returns | Raises | Example | Notes |
|---|---|---|---|---|---|
| Public method | Yes | Yes | Yes | Yes (short) | |
| Property | -- | Yes (in summary) | If applicable | Optional | |
| Class | Yes (`__init__` params) | -- | -- | Yes | Include Attributes section |
| Function | Yes | Yes | Yes | Yes | |
| Enum | -- | -- | -- | -- | Document each value |
| Error class | -- | -- | -- | -- | Document when raised and by which methods |

### Minimum quality bar

- Every parameter has a type annotation in the signature (enforced by mypy)
- Every parameter is described in Args
- Return type is annotated and described
- All exceptions that the method can raise are listed in Raises
- At least one example for methods users call directly
- No TODOs or placeholders in published docstrings

---

## 6. Cross-Linking Rules

Documentation pages must link to related content. Isolated pages force users
to search instead of navigate.

### Canonical URLs

Two published sites exist. Use the right one depending on what you link to:

- **Documentation** (guides, API reference, explanation pages):
  link to ReadTheDocs (`https://remote-store.readthedocs.io/`).
  RTD is the canonical documentation URL. GitHub Pages mirrors the same
  content but RTD is what PyPI, README badges, and external references
  should point to.
- **Source files** (specs, ADRs, examples, source code, CHANGELOG):
  link to the GitHub repository
  (`https://github.com/haalfi/remote-store/`).
  These files are readable on GitHub and the repo is their source of truth.

Within the docs site itself, always use relative links (they work on both
RTD and GitHub Pages). Canonical URLs only matter for links *from outside*
the docs site (README, PyPI, blog posts, external references).

### Required cross-links

| From | To | How |
|---|---|---|
| Guide --> API method it uses | API reference page | `[Store.read()](../api/store.md#remote_store.Store.read)` |
| Guide --> example script | Examples page | `[example](../examples/file-operations.md)` |
| API method --> guide that explains it | Guide page | In docstring: `See the [Streaming Guide](...)` |
| Error class --> methods that raise it | API reference | In error docstring "Raised by" section |
| Backend guide --> capabilities | Capabilities matrix | Link to matrix row |
| Example page --> guide for deeper reading | Guide page | Footer link |

### Minimum per page

- Every how-to guide links to at least one API reference page.
- Every how-to guide links to its matching example script (if one exists).
- Every API class page links to its primary guide.

---

## 7. Page Quality Checklist

Use this checklist when writing or reviewing any documentation page.

### All pages

- [ ] Title is clear and descriptive
- [ ] First paragraph states what the page covers and who it is for
- [ ] No broken links (internal or external)
- [ ] No references to removed or renamed APIs
- [ ] Code examples are complete and runnable (not pseudo-code)
- [ ] Code examples use current API (not deprecated patterns)
- [ ] Page is listed in the correct `_nav.yml` section

### Guides (how-to)

- [ ] Opens with a sentence stating what the reader will accomplish
- [ ] Assumes tutorial completion (no install instructions repeated)
- [ ] Working code examples (copy-paste-run)
- [ ] Links to API reference for every class/function used
- [ ] Links to matching example script
- [ ] Links to related guides ("See also")
- [ ] Ends with next steps or related topics

### API reference (docstrings)

- [ ] All parameters documented with types
- [ ] Return value documented
- [ ] Exceptions documented (which ones, when)
- [ ] At least one usage example
- [ ] Cross-link to relevant guide

### Explanation

- [ ] Explains *why*, not *how*
- [ ] Links to ADRs/specs for formal details
- [ ] No step-by-step instructions (those belong in guides)

---

## 8. Documentation in the Development Workflow

### When writing new features

1. **Spec** -- write the spec first (existing SDD process).
2. **Docstrings** -- write docstrings meeting section 5 standard as part of
   implementation. Not after. Not "later."
3. **Example** -- add or update an example script if the feature is
   user-facing.
4. **Guide** -- add or update a guide if the feature introduces a new
   workflow or changes an existing one.
5. **CHANGELOG** -- document the change under `[Unreleased]`.
6. **Cross-links** -- update related pages per section 6.

### When reviewing PRs

Check documentation alongside code:

- [ ] Docstrings meet section 5 standard for all new/changed public symbols
- [ ] Relevant guide updated (if behavior changed)
- [ ] Example updated or added (if user-facing)
- [ ] CHANGELOG entry present
- [ ] No orphaned cross-links (renamed/removed APIs)

Documentation-related ripple-check rows are maintained in the
[ripple-check table](CLAUDE-REFERENCE.md) alongside all other cross-file
dependency rules.

---

## 9. README Requirements

The README is the most important documentation page. It is the PyPI landing
page, the GitHub landing page, and the first thing every user sees.

### Must contain

- Project description (what it does, one paragraph)
- Who it is for (audience list)
- When NOT to use it (scope boundaries)
- Installation instructions (base + extras)
- Minimal working example with expected output
- Store API overview (method table or summary)
- Supported backends table
- Link to full documentation site
- Link to CHANGELOG
- Link to CONTRIBUTING
- License
- Supported Python versions
- Project status (Alpha/Beta/Stable + badge)
- Known limitations

---

## 10. Hosted Documentation Requirements

The published documentation site must meet these accessibility standards:

- Published at a stable URL
- Versioned (users can read docs for their installed version)
- Searchable
- Mobile-friendly
- No dead links

---

## 14. Definition of Done

Documentation is considered complete when:

- A new user can install and run a working example in under 10 minutes
- All four Diataxis sections exist in the navigation
- All public APIs have docstrings meeting section 5 standard
- All extension APIs have reference pages
- All how-to guides cross-link to API reference and examples
- A troubleshooting page exists with common errors and fixes
- A capabilities matrix exists
- No dead links in the published site
- README renders correctly on PyPI
- Documentation matches the current release

### Tracking

Track documentation work in `sdd/BACKLOG.md` under a `DOC-NNN` prefix.

---

## 12. Research Documents

Research documents in `sdd/research/` capture exploratory analysis done
before a feature is specified. They are not user-facing guides -- they are
working documents that record trade-off evaluations, library comparisons,
API design explorations, and feasibility studies.

Research documents are valuable on their own because they show *what was
considered and why alternatives were rejected*. They complement ADRs (which
record the decision) by preserving the investigation that led to it.

### Rules

- Research docs live in `sdd/research/` and are named
  `research-<topic>.md`.
- They are not edited after the related feature ships -- they are
  historical records.
- They may be surfaced on the docs site under Explanation > Research
  for readers who want full context on design choices.
- They do not need to follow the docstring or guide quality checklists.

---

## 13. Further Reading

The docs site should include a "Further Reading" page (or footer section)
for readers who want to understand the project beyond its API. This page
links to content that lives in the repository but is not part of the
four Diataxis sections:

- **Development Story** (`DEVELOPMENT_STORY.md`) -- how the project was
  built, the human + AI pair-programming approach, timeline, and lessons
  learned.
- **Spec-Driven Development process** (`sdd/000-process.md`) -- the
  methodology behind specs, ADRs, and RFCs.
- **Research documents** (`sdd/research/`) -- exploratory studies on
  specific topics (async API, retry policies, config design, observability,
  example testing, v1 communication).
- **Design document** (`sdd/DESIGN.md`) -- code style, conventions, and
  internal patterns.

This content is optional reading. It does not belong in the main navigation
flow but should be discoverable for contributors and curious users.

---

## References

- [ADR-0006: Documentation Architecture](adrs/0006-documentation-architecture.md)
- [ADR-0007: Three-Tier Content with docs-src/](adrs/0007-docs-src-literate-nav.md)
- [Diataxis framework](https://diataxis.fr/) -- the Tutorial / How-To /
  Reference / Explanation model this document adapts
- [CLAUDE-REFERENCE.md](CLAUDE-REFERENCE.md) -- ripple-check table,
  repo layout
