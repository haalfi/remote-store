# Cross-artifact gate inventory

<!-- doc: repo-only -->

Derived from 34 declared mechanism(s) by `scripts/gen_gate_inventory.py`. Do not edit by hand; run `hatch run gen-gate-inventory`.

Which artifact pairs this repo checks, which single-artifact rules it
asserts, and what its reports surface. *Kind*, the subject column and
*Domain* come from each mechanism's `Drift-gate::` docstring block; *Runs
in* and *Enforcement* are derived from `pyproject.toml` and
`.github/workflows/`, so no column is maintained here. The generator's
module docstring states what this inventory does not catch.

## Pair gates (23)

| Mechanism | Compares | Domain | Runs in | Enforcement |
|---|---|---|---|---|
| `scripts/check_api_docs.py` | the graph IR in docs-src/_data/graph/graph.json ↔ the API reference pages under docs-src/reference/api/ | realization ↔ explanation | `all`, `preflight` | gating |
| `scripts/check_backend_order.py` | the canonical order in this script's own _BACKENDS constant ↔ every backend enumeration in the scanned surfaces, CONTRIBUTING.md and README.md among them | cross-surface | `all`, `docs-gate`, `lint` | gating |
| `scripts/check_capability_parity.py` | the Capability enum in src/remote_store/_capabilities.py ↔ the Capability datatype and CapabilityName arms in sdd/formal/BackendContract.dfy | realization ↔ intent-formalized | `all`, `ci.yml:verify-formal`, `lint` | gating |
| `scripts/check_ci_full_matrix.py` | ci.yml's ALL_PYTHONS interpreter list ↔ ci-full.yml's test-full matrix | process | `all`, `lint` | gating |
| `scripts/check_ci_inventory.py` | the scheduled-family workflows under .github/workflows/ ↔ the workflow inventory in sdd/CI-OPERATIONS.md | process | `all`, `lint` | gating |
| `scripts/check_custom_backend_guide.py` | docs-src/guides/custom-backend-guide.md ↔ Backend.__abstractmethods__, the conformance suite files and the fixture loader's closed vocabularies | explanation ↔ realization | `all`, `docs-gate`, `lint` | gating |
| `scripts/check_dafny_twin_parity.py` | the MemoryBackend and MemoryBackendMinimal twin classes in sdd/formal/ | intent-formalized | `all`, `ci.yml:verify-formal`, `lint` | gating |
| `scripts/check_docstring_parity.py` | the sync API docstrings in src/remote_store/ ↔ their hand-mirrored twins in src/remote_store/aio/ | realization | `all`, `preflight` | gating |
| `scripts/check_formal_trace.py` | spec IDs declared in sdd/specs/ ↔ Dafny @spec tags in sdd/formal/ and conformance pytest.mark.spec markers | intent ↔ intent-formalized ↔ verification | `all`, `ci.yml:verify-formal`, `lint` | gating |
| `scripts/check_infra_settings.py` | infra/.env ↔ infra/_settings.py, the compose file and the port and credential references in CI workflows | process | `all`, `lint` | gating |
| `scripts/check_readthedocs_python.py` | .python-version ↔ .readthedocs.yaml's build.tools.python | process | `all`, `lint` | gating |
| `scripts/check_ripple_parity.py` | the ripple-check Pre-work index ↔ the Detailed checklist, both in sdd/CLAUDE-REFERENCE.md | process | `all`, `docs-gate`, `lint` | gating |
| `scripts/check_spec_marks.py` | spec IDs declared in sdd/specs/ ↔ spec IDs cited by pytest.mark.spec markers under tests/ | intent ↔ verification | `all`, `ci.yml:verify-formal`, `lint` | gating |
| `scripts/check_traces.py` | every trace under sdd/traces/ ↔ the schema in sdd/traces/_schema.yml | process | `all`, `docs-gate`, `lint` | gating |
| `scripts/docs/check_links.py` | every Markdown link and context7 manifest path ↔ the on-disk files and built docs-site pages they name | explanation | `all`, `docs-gate` | gating |
| `scripts/drift_check.py diff` | the freshly resolved dependency set for each extra ↔ the committed baseline in infra/drift-locks/ | process | `drift-guard.yml:check` | scheduled |
| `scripts/drift_check.py render-docs` | the lock files in infra/drift-locks/ ↔ docs-src/reference/tested-versions.md | process ↔ explanation | `all`, `docs-gate`, `preflight` | gating |
| `scripts/gen_adr_digest.py` | the Status tables and Decision sections of sdd/adrs/*.md ↔ sdd/adrs/DIGEST.md | intent | `all`, `preflight` | gating |
| `scripts/gen_backlogid.py` | the max ID per prefix in sdd/BACKLOG-DONE.md ↔ sdd/backlogid.json, and the open IDs in sdd/BACKLOG.md against both | process | `all`, `docs-gate`, `lint` | gating |
| `scripts/gen_features.py` | docs-src/_data/graph/graph.json, pyproject.toml's extras and the backend order in src/remote_store/_registry.py ↔ the generated sections of FEATURES.md | realization ↔ explanation | `all`, `preflight` | gating |
| `scripts/gen_gate_inventory.py` | the Drift-gate declarations and gate wiring across scripts/, pyproject.toml and .github/workflows/ ↔ sdd/GATE-INVENTORY.md | process | `all`, `docs-gate`, `lint` | gating |
| `scripts/gen_graph.py` | the source tree under src/remote_store/ ↔ docs-src/_data/graph/graph.json | realization | `all`, `preflight` | gating |
| `scripts/gen_graph_viz.py` | docs-src/_data/graph/graph.json ↔ docs-src/explanation/graph_viz.html | explanation | `all`, `preflight` | gating |

## Rule checks, no pair (9)

Single-artifact checks. They guard no pair, so a derivation over compared
artifacts alone would yield no row for them at all.

| Mechanism | Rule asserted | Domain | Runs in | Enforcement |
|---|---|---|---|---|
| `scripts/check_docs_framework.py` | every Markdown file resolves to exactly one documentation class and obeys the framework's placement, nav and bridge rules (G-01 through G-07) | explanation | `all`, `docs-gate`, `lint` | gating |
| `scripts/check_mock_spec.py` | every MagicMock or Mock call passes spec= or spec_set= (TESTING.md Rule 4) | verification | `all`, `lint` | gating |
| `scripts/check_no_tracker_refs.py` | no internal tracker ID appears in a surface that reaches users (CONTENT-RULES Rules 1 and 5) | explanation | `all`, `docs-gate`, `lint` | gating |
| `scripts/check_rst_roles.py` | no Python file uses RST inline-role syntax in a Google-style docstring | explanation | `all`, `lint` | gating |
| `scripts/check_test_assertions.py` | every test function contains at least one assert or pytest.raises (TESTING.md Rule 1) | verification | `all`, `lint` | gating |
| `scripts/check_test_placement.py` | every test file sits in the subpackage TESTING.md and spec 048 place it in | verification | `all`, `lint` | gating |
| `scripts/check_tla_no_emdash.py` | no TLA+ module under sdd/formal/tla/ contains an em dash, which TLC rejects | intent-formalized | `all`, `ci.yml:verify-tla`, `lint` | gating |
| `scripts/docs/check_links.py` | both context7 manifests stay within Context7's per-field list and rule-length maxima, which it silently rejects a manifest for exceeding | explanation | `all`, `docs-gate` | gating |
| `scripts/docs/check_links.py` | every <a id> anchor in a link target is unique within its file and adjacent to a heading | explanation | `all`, `docs-gate` | gating |

## Reports, no assertion (2)

These measure rather than assert. Nothing here is true or false of an
artifact, so neither of the columns above fits: putting a description in
a *Rule asserted* cell would claim a check that is not being made.

| Mechanism | Surfaces | Domain | Runs in | Enforcement |
|---|---|---|---|---|
| `scripts/drift_report.py` | the current per-extra dependency-drift state, as a rolling GitHub issue it opens, updates or closes; it acts on that state rather than asserting anything, and exits 0 either way | process | `drift-guard.yml:report` | scheduled |
| `scripts/report_trace_outcomes.py` | which documents readers recorded as unclear or misleading, ranked by tag rate over reads across the trace corpus | process | `report-trace-outcomes` | advisory |
