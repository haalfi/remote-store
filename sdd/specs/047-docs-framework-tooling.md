# Spec 047 — Documentation Framework Tooling

**Scope:** Build & CI tooling. Specifies the bridge, gate, and pipeline
that enforce the documentation framework. Not library source code; the
contracts here govern `scripts/docs/` and `scripts/check_docs_framework.py`.

**Prefix:** `DOCFRAME`

**Author-facing surface:** [`AUTHORING.md`](../AUTHORING.md). Authors do
not need to read this spec to write or classify documents. Marker
syntax, classification rules, directory defaults, and per-class
semantics live in AUTHORING.md and are normative there. This spec
defers to AUTHORING.md for those rules and only specifies the
tooling that enforces them.

**Related decisions:** [ADR-0027](../adrs/0027-docs-bridge-single-mechanism.md)
selects the single-bridge architecture and inline-marker classification.
[ADR-0007](../adrs/0007-docs-src-literate-nav.md) established the
three-tier `docs-src/` + gen-files + source-dirs split; this spec
narrows ADR-0007's "build hook" tier to one bridge mechanism.

**Tracks:** [BK-167a](../BACKLOG.md). [BK-167b](../BACKLOG.md)
applies the framework and closes the remaining audit-012 findings.

---

## DOCFRAME-001: Single Bridge Mechanism

**Invariant:** Exactly one mechanism in `scripts/docs/` discovers the
source→virtual-dest mapping for dual files. Every dual file reaches the
docs site through that mechanism.

**Postcondition:** No `include-markdown` Jinja directive is present in
any `docs-src/**/*.md` file. No `_link_map.yml` is present. No
mechanism other than the one defined here writes virtual pages for
dual content.

**Mechanism:** `scripts/docs/scan.py:scan_dual_files(repo_root)` returns
an iterable of `DualEntry` records. `scripts/docs/render.py:render_dual_pages`
emits one virtual page per entry using the existing
[`LinkResolver`](../../scripts/docs/link.py).

**Rationale:** [AUTHORING.md](../AUTHORING.md) Rule 4. See
[ADR-0027](../adrs/0027-docs-bridge-single-mechanism.md) for the
selection rationale and the three legacy mechanisms it supersedes.

---

## DOCFRAME-002: Classification Parser Contract

**Invariant:** The marker parser implements the syntax and semantics
defined in [`AUTHORING.md`](../AUTHORING.md) Rule 1 and its "Classification
markers" guide. This spec adds only the parsing contract:

- The parser scans the first 5 non-blank lines of each `.md` file.
- The parser is regex-based; no Markdown AST is constructed.
- A malformed marker (unrecognised class, `dest=` on a non-dual class,
  missing `dest=` on a dual marker, multiple markers in one file) is a
  parse error reported by the gate as G-01.
- Marker absence falls back to the directory-default table in
  AUTHORING.md. Files matching no default and carrying no marker are a
  G-01 failure.

**Postcondition:** Every `.md` in the repository resolves to exactly
one class, derivable from the file plus the AUTHORING.md default
table; no separate manifest is consulted.

**Rationale:** AUTHORING.md owns the rules; this spec owns the parser
that enforces them. Splitting prevents author-facing content (syntax,
examples) from drifting into a tooling spec authors do not read.

---

## DOCFRAME-003: DualEntry Record

**Invariant:** `scripts/docs/scan.py:DualEntry` is a frozen dataclass
with shape:

```python
@dataclass(frozen=True)
class DualEntry:
    source: Path        # absolute repo path
    dest: str           # virtual dest, e.g. "explanation/design/authoring.md"
```

`DualEntry` carries no class field: by construction, only dual entries
reach render input. Repo-only and docs-only files are observed by the
gate's classification audit (G-01) on a separate code path that does
not produce `DualEntry` records.

---

## DOCFRAME-004: PR-Time Gate

**Invariant:** `scripts/check_docs_framework.py` exits 0 if and only if
every framework rule listed below holds. Wired into `hatch run all` via
a `docs-check` script in `pyproject.toml`. CI runs `hatch run all` on
every PR.

**Checks (each is a separate failure mode):**

| Check ID | Rule | What it asserts |
|---|---|---|
| G-01 | AUTHORING R1 | Every `.md` resolves to exactly one class via marker or default rule. Ambiguous, missing, and conflicting markers fail. |
| G-02 | AUTHORING R2 | The source→dest map is injective: no two dual sources point to the same dest, no source has two dests. |
| G-03 | AUTHORING R3 | Dual files contain no `{% ... %}` Jinja directive and no MkDocs macro syntax. The `--8<--` snippet form is permitted. |
| G-04 | AUTHORING R4 | No `include-markdown` directive in any `docs-src/**/*.md`. No `_link_map.yml` exists. |
| G-05 | AUTHORING R3 (link safety) | Every relative `](path)` link in every dual file resolves on disk in the repo. |
| G-06 | DOCUMENTATION R7 | For every page reachable through `docs-src/_nav.yml` and its child `_nav.yml` files, the URL prefix matches the nav-section prefix (Reference → `/reference/`, Explanation → `/explanation/`, etc.). The check parses the nav source files directly; it does not rely on the generated `SUMMARY.md` (which is a build-time artifact, not a source). |
| G-07 | DOCUMENTATION R8 | `mkdocs build --strict` succeeds. (`--strict` promotes all warnings to failures; MkDocs 1.x does not accept `error` as a literal value for `validation.links.not_found`.) |

**Failure output:** one line per violation, formatted
`<check-id> <path>: <reason>`. Lines are stable across runs (sorted by
path) so diffs in CI logs are minimal.

**Performance:** scan + checks G-01 through G-05 run in under 5 seconds
on the full tree; G-06 and G-07 invoke MkDocs, bounded by docs build
time.

**Rationale:** [AUTHORING.md](../AUTHORING.md) Rule 5.

---

## DOCFRAME-005: Bridge Replaces, Not Augments

**Invariant:** When this spec is implemented, the following functions
and files are removed:

- `scripts/docs/scan.py:load_link_map`
- `scripts/docs/scan.py:scan_include_wrappers`
- `scripts/docs/render.py:render_link_rewritten`
- `docs-src/_link_map.yml`
- `docs-src/design/authoring.md`
- `docs-src/design/content-rules.md`
- `docs-src/design/design.md`
- `docs-src/design/documentation.md`
- `docs-src/design/testing.md`

**Postcondition:** `git grep -n "include-markdown" docs-src/` returns
no matches. `git ls-files docs-src/_link_map.yml` returns no matches.

**Rationale:** AUTHORING Rule 4 forbids parallel mechanisms. Renaming
without removing is not compliance.

---

## DOCFRAME-006: Strict Build, Strict Links

**Invariant:** CI invokes `mkdocs build --strict`. A broken internal link
is a build failure, not a warning. MkDocs 1.x does not accept `error` as a
literal value for `validation.links.not_found`; `--strict` promotes all
warnings (including link warnings) to failures, achieving the same effect.

**Postcondition:** Audit-012 F-03 and W-01 are closed.

**Implementation note:** This step lands AFTER DOCFRAME-005 because
several existing wrapper-routed links break under `--strict` until the
bridge unifies the source→dest map.

---

## DOCFRAME-007: Nav and URL Alignment

**Invariant:** Each top-level nav section maps to a URL prefix matching
its label (lowercased, hyphenated). The top-level nav structure follows
[DOCUMENTATION.md](../DOCUMENTATION.md) Rule 9 (Tutorial, Guides,
Reference, Explanation as the only content sections; `Home:` permitted
as the index entry).

**Required `docs-src/_nav.yml` shape after this spec lands:**

```yaml
- Home: index.md
- Tutorial:
    - Getting Started: getting-started.md
    - Examples: examples/
- Guides: ...
- Reference: ...
- Explanation:
    - ...
    - Design: explanation/design/
```

Examples nest under Tutorial (the learn-by-doing quadrant). Changelog
nests under Reference at the URL `/reference/changelog/` (closes F-10).
"Further Reading" is removed; its prior contents (Development Story,
Contributing) move under Explanation or Reference per their content
type.

**Closes:** F-05 (Tutorial top-level), F-06 (Changelog out of
Reference), F-07 (Further Reading out of Diataxis), F-08 (Design URL
prefix), F-10 (Changelog URL).

**Implementation note:** Folded into BK-167a per the user-confirmed
scope. Each finding's nav/URL fix is a one-line `_nav.yml` edit plus
matching directory move under `docs-src/`. The G-06 gate verifies the
result.

---

## Tests

`tests/scripts/test_docs_framework.py`:

| Test | Spec ref | Note |
|---|---|---|
| `test_marker_parses_dual_with_dest` | DOCFRAME-002 | |
| `test_marker_parses_repo_only_no_dest` | DOCFRAME-002 | |
| `test_marker_absent_defaults_to_dual_in_sdd_subdir` | DOCFRAME-002 | |
| `test_marker_absent_in_repo_root_is_an_error` | DOCFRAME-002, G-01 | |
| `test_classify_file_templates_dir_is_repo_only` | DOCFRAME-002 | |
| `test_scan_dual_files_yields_only_dual_class` | DOCFRAME-001, DOCFRAME-003 | |
| `test_render_dual_pages_uses_link_resolver` | DOCFRAME-001 | DOCFRAME-004 gate (later step) |
| `test_dest_collision_fails` | G-02 | DOCFRAME-004 gate (later step) |
| `test_jinja_in_dual_file_fails` | G-03 | DOCFRAME-004 gate (later step) |
| `test_include_markdown_in_docs_src_fails` | G-04 | DOCFRAME-004 gate (later step) |
| `test_broken_repo_link_in_dual_fails` | G-05 | DOCFRAME-004 gate (later step) |
| `test_url_nav_misalignment_fails` | G-06 | DOCFRAME-004 gate (later step) |
| `test_mkdocs_strict_passes_after_bridge` | G-07 | DOCFRAME-004 gate (later step) |

Each test traces back via `@pytest.mark.spec("DOCFRAME-NNN")` per
[`000-process.md`](../000-process.md) Rule 2.
