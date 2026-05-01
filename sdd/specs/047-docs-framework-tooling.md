# Spec 047 — Documentation Framework Tooling

Tooling layer that enforces the documentation framework defined by
[`AUTHORING.md`](../AUTHORING.md), [`DOCUMENTATION.md`](../DOCUMENTATION.md),
and [`CONTENT-RULES.md`](../CONTENT-RULES.md). Three deliverables: bridge,
classification storage, PR-time gate.

**Prefix:** `DOCFRAME`

**Related decisions:** [ADR-0027](../adrs/0027-docs-bridge-single-mechanism.md)
selects the single-bridge architecture and inline-marker classification.
[ADR-0007](../adrs/0007-docs-src-literate-nav.md) established the
three-tier `docs-src/` + gen-files + source-dirs split; this spec
narrows ADR-0007's "build hook" tier to one bridge mechanism.

**Tracks:** [BK-167a](../BACKLOG.md#bk-167a). [BK-167b](../BACKLOG.md#bk-167b)
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

## DOCFRAME-002: Inline Classification Marker

**Invariant:** Every `.md` file in the repository has a class — one of
`dual`, `repo-only`, `docs-only` — derivable without reading any file
other than the file itself and the directory-default table below.

**Marker syntax (normative):**

```markdown
<!-- doc: dual dest=<virtual-dest> -->
<!-- doc: repo-only -->
<!-- doc: docs-only -->
```

The marker MUST appear within the first 5 non-blank lines of the file.
The marker MAY follow a `# Title` line. Whitespace inside the comment
is normalised; the parser accepts one or more spaces between tokens.

**Class semantics:**

- **`dual`** — file appears unchanged at its repo path AND at the
  virtual `dest` on the docs site. `dest=` is required.
- **`repo-only`** — file appears only at its repo path. The bridge does
  not emit a virtual page. `dest=` MUST be absent.
- **`docs-only`** — file is authored under `docs-src/` and consumed by
  MkDocs. The bridge does not act on it. `dest=` MUST be absent.

**Default rules (apply when no marker is present):**

| Source pattern | Default class | Default dest |
|---|---|---|
| `sdd/adrs/*.md` (matching kind glob, not `skip_stems`) | dual | `design/adrs/<slug>.md` |
| `sdd/specs/*.md` | dual | `design/specs/<slug>.md` |
| `sdd/rfcs/rfc-*.md` (not `rfc-template`) | dual | `design/rfcs/<slug>.md` |
| `sdd/audits/audit-*.md` | dual | `design/audits/<slug>.md` |
| `sdd/research/research-*.md` | dual | `design/research/<slug>.md` |
| `docs-src/**/*.md` | docs-only | — |
| `examples/**/README.md` | dual | (per existing render rule, e.g. `examples/medallion-dagster.md`) |
| anything else | requires explicit marker | — |

**Required explicit markers (no default):** `sdd/*.md` top-level files,
all repo-root `.md` files, anything else not matching a default rule.

**Postcondition:** The classification system is auditable from one input
(the file plus this table); no separate manifest is consulted.

**Rationale:** [AUTHORING.md](../AUTHORING.md) Rule 1. See
[ADR-0027](../adrs/0027-docs-bridge-single-mechanism.md) for the choice
of inline markers over a central manifest.

---

## DOCFRAME-003: DualEntry Record

**Invariant:** `scripts/docs/scan.py:DualEntry` is a frozen dataclass
with shape:

```python
@dataclass(frozen=True)
class DualEntry:
    source: Path        # absolute repo path
    dest: str           # virtual dest, e.g. "design/authoring.md"
    klass: str          # "dual" (only dual entries reach render)
```

`scan_dual_files` returns only entries with `klass == "dual"`. Repo-only
and docs-only files appear in the gate's classification audit but never
in the bridge's render input.

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
| G-06 | DOCUMENTATION R7 | For every page in `SUMMARY.md`, the URL prefix matches the nav-section prefix (Reference → `/reference/`, Explanation → `/explanation/`, etc.). |
| G-07 | DOCUMENTATION R8 | `mkdocs build --strict` succeeds with `validation.links.not_found: error`. |

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

**Invariant:** `mkdocs.yml` declares `validation.links.not_found: error`
and CI invokes `mkdocs build --strict`. A broken internal link is a
build failure, not a warning.

**Postcondition:** Audit-012 F-03 and W-01 are closed.

**Implementation note:** This step lands AFTER DOCFRAME-005 because
several existing wrapper-routed links break under `--strict` until the
bridge unifies the source→dest map.

---

## DOCFRAME-007: Nav and URL Alignment

**Invariant:** Each top-level nav section maps to a URL prefix matching
its label (lowercased, hyphenated). The four Diataxis quadrants are the
only top-level sections (per [DOCUMENTATION.md](../DOCUMENTATION.md)
Rule 1).

**Required `docs-src/_nav.yml` shape after this spec lands:**

```yaml
- Home: index.md
- Tutorial: getting-started.md
- Guides: ...
- Reference: ...
- Explanation:
    - ...
    - Design: explanation/design/
- Examples: examples/
```

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

| Test | Spec ref |
|---|---|
| `test_marker_parses_dual_with_dest` | DOCFRAME-002 |
| `test_marker_parses_repo_only_no_dest` | DOCFRAME-002 |
| `test_marker_absent_defaults_to_dual_in_sdd_subdir` | DOCFRAME-002 |
| `test_marker_absent_in_repo_root_is_an_error` | DOCFRAME-002, G-01 |
| `test_scan_dual_files_yields_only_dual_class` | DOCFRAME-001, DOCFRAME-003 |
| `test_render_dual_pages_uses_link_resolver` | DOCFRAME-001 |
| `test_dest_collision_fails` | G-02 |
| `test_jinja_in_dual_file_fails` | G-03 |
| `test_include_markdown_in_docs_src_fails` | G-04 |
| `test_broken_repo_link_in_dual_fails` | G-05 |
| `test_url_nav_misalignment_fails` | G-06 |
| `test_mkdocs_strict_passes_after_bridge` | G-07 |

Each test traces back via `@pytest.mark.spec("DOCFRAME-NNN")` per
[`000-process.md`](../000-process.md) Rule 2.
