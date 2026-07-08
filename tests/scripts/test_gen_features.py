"""Tests for scripts/gen_features.py (ID-163)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPTS = ROOT / "scripts"


@pytest.fixture(scope="module")
def gen_features_module():
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    if str(ROOT / "src") not in sys.path:
        sys.path.insert(0, str(ROOT / "src"))
    import gen_features

    return gen_features


@pytest.fixture(scope="module")
def graph(gen_features_module):
    return gen_features_module._load_graph()


@pytest.fixture(scope="module")
def pyproject(gen_features_module):
    return gen_features_module._load_pyproject()


class TestRegistryOrder:
    def test_parses_at_least_one_entry(self, gen_features_module):
        order = gen_features_module._parse_registry_order()
        assert len(order) >= 1

    def test_local_and_memory_present(self, gen_features_module):
        types = [t for t, _ in gen_features_module._parse_registry_order()]
        assert "local" in types
        assert "memory" in types

    def test_returns_tuples(self, gen_features_module):
        for type_str, cls_name in gen_features_module._parse_registry_order():
            assert isinstance(type_str, str)
            assert isinstance(cls_name, str)
            assert type_str
            assert cls_name


class TestBaselineCaps:
    def test_excludes_flag_caps(self, gen_features_module, graph):
        baseline = gen_features_module._baseline_caps(graph)
        assert "USER_METADATA" not in baseline
        assert "WRITE_RESULT_NATIVE" not in baseline

    def test_includes_gate_caps(self, gen_features_module, graph):
        baseline = gen_features_module._baseline_caps(graph)
        for cap in ("READ", "WRITE", "DELETE", "LIST", "GLOB", "MOVE", "COPY"):
            assert cap in baseline

    def test_is_sorted_alphabetically(self, gen_features_module, graph):
        baseline = gen_features_module._baseline_caps(graph)
        assert baseline == sorted(baseline)


class TestFormatCaps:
    def test_all_when_nothing_missing(self, gen_features_module):
        baseline = ["A", "B", "C"]
        assert gen_features_module._format_caps(frozenset({"A", "B", "C"}), baseline) == "All"

    def test_all_except_when_majority_present(self, gen_features_module):
        baseline = ["A", "B", "C", "D", "E", "F", "G", "H"]
        declared = frozenset({"A", "B", "C", "D", "E", "F"})  # 6 of 8 present
        result = gen_features_module._format_caps(declared, baseline)
        assert result.startswith("All except")
        assert "`G`" in result
        assert "`H`" in result

    def test_explicit_list_when_minority_present(self, gen_features_module):
        baseline = ["A", "B", "C", "D", "E", "F", "G", "H"]
        declared = frozenset({"A", "B", "C"})  # 3 of 8 — minority
        result = gen_features_module._format_caps(declared, baseline)
        assert "All" not in result
        assert "`A`" in result

    def test_preserves_baseline_order_in_except_clause(self, gen_features_module):
        # Need majority present to trigger "All except" path.
        baseline = ["ATOMIC_MOVE", "COPY", "DELETE", "GLOB"]
        declared = frozenset({"COPY", "DELETE", "GLOB"})  # missing ATOMIC_MOVE (3 present > 1 missing)
        result = gen_features_module._format_caps(declared, baseline)
        # ATOMIC_MOVE appears first in baseline, so it should be listed first in "except".
        assert result == "All except `ATOMIC_MOVE`"


class TestBackendsMainTable:
    def test_header_row(self, gen_features_module, graph):
        table = gen_features_module.project_backends_main(graph)
        lines = table.splitlines()
        assert lines[0] == "| Type | Class | Extra | Capabilities |"
        assert lines[1] == "|---|---|---|---|"

    def test_backends_sorted_alphabetically(self, gen_features_module, graph):
        table = gen_features_module.project_backends_main(graph)
        type_strs = [row.split("|")[1].strip().strip("`") for row in table.splitlines()[2:] if row.startswith("| `")]
        assert type_strs == sorted(type_strs)

    def test_all_registered_backends_present(self, gen_features_module, graph):
        table = gen_features_module.project_backends_main(graph)
        for type_str, _ in gen_features_module._parse_registry_order():
            assert f"| `{type_str}` |" in table, f"Backend {type_str!r} missing"

    def test_local_renders_as_all(self, gen_features_module, graph):
        table = gen_features_module.project_backends_main(graph)
        local_row = next(row for row in table.splitlines() if row.startswith("| `local`"))
        assert local_row.endswith("| All |")

    def test_http_extra_has_stdlib_note(self, gen_features_module, graph):
        table = gen_features_module.project_backends_main(graph)
        http_row = next(row for row in table.splitlines() if row.startswith("| `http`"))
        assert "stdlib" in http_row

    def test_http_caps_explicit_list(self, gen_features_module, graph):
        table = gen_features_module.project_backends_main(graph)
        http_row = next(row for row in table.splitlines() if row.startswith("| `http`"))
        assert "All" not in http_row.split("|")[-2]

    def test_s3_missing_only_atomic_move(self, gen_features_module, graph):
        table = gen_features_module.project_backends_main(graph)
        s3_row = next(row for row in table.splitlines() if row.startswith("| `s3` |"))
        assert "ATOMIC_MOVE" in s3_row
        assert s3_row.endswith("All except `ATOMIC_MOVE` |")


class TestBackendsFlagsTable:
    def test_header_row(self, gen_features_module, graph):
        table = gen_features_module.project_backends_flags(graph)
        lines = table.splitlines()
        assert "WRITE_RESULT_NATIVE" in lines[0]
        assert "USER_METADATA" in lines[0]
        assert lines[1] == "|---|---|---|"

    def test_all_registered_backends_present(self, gen_features_module, graph):
        table = gen_features_module.project_backends_flags(graph)
        for type_str, _ in gen_features_module._parse_registry_order():
            assert f"| `{type_str}` |" in table

    def test_local_has_write_result_no_user_metadata(self, gen_features_module, graph):
        table = gen_features_module.project_backends_flags(graph)
        local_row = next(row for row in table.splitlines() if row.startswith("| `local`"))
        cols = [c.strip() for c in local_row.split("|")[1:-1]]
        assert cols[1] == "Yes"
        assert cols[2] == "—"

    def test_sql_blob_uses_notes(self, gen_features_module, graph):
        table = gen_features_module.project_backends_flags(graph)
        sql_row = next(row for row in table.splitlines() if row.startswith("| `sql-blob`"))
        assert "requires" in sql_row
        assert "modified_at" in sql_row
        assert "user_metadata" in sql_row

    def test_azure_has_both_flags(self, gen_features_module, graph):
        table = gen_features_module.project_backends_flags(graph)
        azure_row = next(row for row in table.splitlines() if row.startswith("| `azure`"))
        cols = [c.strip() for c in azure_row.split("|")[1:-1]]
        assert cols[1] == "Yes"
        assert cols[2] == "Yes"

    def test_backends_sorted_alphabetically(self, gen_features_module, graph):
        table = gen_features_module.project_backends_flags(graph)
        type_strs = [row.split("|")[1].strip().strip("`") for row in table.splitlines()[2:] if row.startswith("| `")]
        assert type_strs == sorted(type_strs)


class TestBackendsAsyncTable:
    def test_header_row(self, gen_features_module, graph):
        table = gen_features_module.project_backends_async(graph)
        lines = table.splitlines()
        assert lines[0] == "| Class | Extra | Capabilities |"
        assert lines[1] == "|---|---|---|"

    def test_native_async_backends_present(self, gen_features_module, graph):
        table = gen_features_module.project_backends_async(graph)
        for cls_name in ("AsyncMemoryBackend", "AsyncAzureBackend", "GraphBackend"):
            assert f"| `{cls_name}` |" in table, f"{cls_name!r} missing"

    def test_excludes_abc_and_adapter(self, gen_features_module, graph):
        """The AsyncBackend ABC and SyncBackendAdapter bridge are not native backends."""
        table = gen_features_module.project_backends_async(graph)
        assert "| `AsyncBackend` |" not in table  # the bare ABC row
        assert "SyncBackendAdapter" not in table
        assert "AsyncBackendSyncAdapter" not in table

    def test_graph_extra_and_caps(self, gen_features_module, graph):
        table = gen_features_module.project_backends_async(graph)
        graph_row = next(row for row in table.splitlines() if row.startswith("| `GraphBackend` |"))
        assert "`remote-store[graph]`" in graph_row
        # GR-003: Graph supports all except ATOMIC_MOVE, GLOB, SEEKABLE_READ.
        assert graph_row.endswith("All except `ATOMIC_MOVE`, `GLOB`, `SEEKABLE_READ` |")

    def test_memory_has_no_extra(self, gen_features_module, graph):
        table = gen_features_module.project_backends_async(graph)
        mem_row = next(row for row in table.splitlines() if row.startswith("| `AsyncMemoryBackend` |"))
        assert mem_row.split("|")[2].strip() == "—"

    def test_sorted_alphabetically(self, gen_features_module, graph):
        table = gen_features_module.project_backends_async(graph)
        names = [row.split("|")[1].strip().strip("`") for row in table.splitlines()[2:] if row.startswith("| `")]
        assert names == sorted(names)


class TestBackendsAsyncFlagsTable:
    def test_header_row(self, gen_features_module, graph):
        table = gen_features_module.project_backends_async_flags(graph)
        lines = table.splitlines()
        assert lines[0] == "| Class | `WRITE_RESULT_NATIVE` | `USER_METADATA` |"
        assert lines[1] == "|---|---|---|"

    def test_graph_native_write_no_user_metadata(self, gen_features_module, graph):
        table = gen_features_module.project_backends_async_flags(graph)
        graph_row = next(row for row in table.splitlines() if row.startswith("| `GraphBackend` |"))
        cols = [c.strip() for c in graph_row.split("|")[1:-1]]
        assert cols[1] == "Yes"
        assert cols[2] == "—"

    def test_async_azure_has_both_flags(self, gen_features_module, graph):
        table = gen_features_module.project_backends_async_flags(graph)
        azure_row = next(row for row in table.splitlines() if row.startswith("| `AsyncAzureBackend` |"))
        cols = [c.strip() for c in azure_row.split("|")[1:-1]]
        assert cols[1] == "Yes"
        assert cols[2] == "Yes"


class TestInstallExtras:
    def test_starts_and_ends_with_fence(self, gen_features_module, pyproject):
        block = gen_features_module.project_install_extras(pyproject)
        lines = block.splitlines()
        assert lines[0] == "```"
        assert lines[-1] == "```"

    def test_excludes_dev_tooling(self, gen_features_module, pyproject):
        block = gen_features_module.project_install_extras(pyproject)
        for excluded in ("dev", "bench", "docs"):
            assert f"remote-store[{excluded}]" not in block

    def test_includes_backend_extras(self, gen_features_module, pyproject):
        block = gen_features_module.project_install_extras(pyproject)
        for extra in ("s3", "azure", "sftp", "sql", "sql-query"):
            assert f"remote-store[{extra}]" in block

    def test_includes_extension_extras(self, gen_features_module, pyproject):
        block = gen_features_module.project_install_extras(pyproject)
        for extra in ("arrow", "otel", "yaml", "pydantic", "dagster"):
            assert f"remote-store[{extra}]" in block

    def test_has_comments(self, gen_features_module, pyproject):
        block = gen_features_module.project_install_extras(pyproject)
        assert "# S3 via s3fs" in block
        assert "# Azure ADLS Gen2" in block

    def test_columns_aligned(self, gen_features_module, pyproject):
        """All comment markers (#) must start at the same column."""
        block = gen_features_module.project_install_extras(pyproject)
        comment_cols = [line.index("#") for line in block.splitlines() if "#" in line and not line.startswith("```")]
        if comment_cols:
            assert len(set(comment_cols)) == 1, "Comment columns are not aligned"

    def test_extras_sorted_alphabetically(self, gen_features_module, pyproject):
        block = gen_features_module.project_install_extras(pyproject)
        extras = [
            line.split("[")[1].split("]")[0]
            for line in block.splitlines()
            if line.startswith("pip install remote-store[")
        ]
        assert extras == sorted(extras)


class TestStoreApiGated:
    def test_header_row(self, gen_features_module, graph):
        table = gen_features_module.project_store_api_gated(graph)
        lines = table.splitlines()
        assert lines[0] == "| Capability | Gated methods |"
        assert lines[1] == "|---|---|"

    def test_capabilities_sorted(self, gen_features_module, graph):
        table = gen_features_module.project_store_api_gated(graph)
        caps = [row.split("|")[1].strip().strip("`") for row in table.splitlines()[2:] if row.startswith("| `")]
        assert caps == sorted(caps)

    def test_read_lists_all_four_read_methods(self, gen_features_module, graph):
        table = gen_features_module.project_store_api_gated(graph)
        read_row = next(row for row in table.splitlines() if row.startswith("| `READ` |"))
        for method in ("read()", "read_bytes()", "read_seekable()", "read_text()"):
            assert f"`{method}`" in read_row

    def test_quality_flag_capabilities_absent(self, gen_features_module, graph):
        """Quality flags are not gates, so they have no gate-map row."""
        table = gen_features_module.project_store_api_gated(graph)
        for flag in ("SEEKABLE_READ", "LAZY_READ", "ATOMIC_MOVE", "WRITE_RESULT_NATIVE", "USER_METADATA"):
            assert f"| `{flag}` |" not in table

    def test_get_folder_info_dual_gate_footnote(self, gen_features_module, graph):
        table = gen_features_module.project_store_api_gated(graph)
        # Primary gate is METADATA; the method carries the footnote marker there.
        meta_row = next(row for row in table.splitlines() if row.startswith("| `METADATA` |"))
        assert r"`get_folder_info()`\*" in meta_row
        # The depth gate (LIST) does not add get_folder_info to the LIST row.
        list_row = next(row for row in table.splitlines() if row.startswith("| `LIST` |"))
        assert "get_folder_info" not in list_row
        # A note line documents the secondary LIST gate.
        assert r"\* `get_folder_info()` is additionally gated on `LIST`" in table


class TestStoreApiUngated:
    def test_header_row(self, gen_features_module, graph):
        table = gen_features_module.project_store_api_ungated(graph)
        lines = table.splitlines()
        assert lines[0] == "| Method | Returns | Description |"
        assert lines[1] == "|---|---|---|"

    def test_contains_representative_methods(self, gen_features_module, graph):
        table = gen_features_module.project_store_api_ungated(graph)
        for method in ("exists(path)", "child(subpath)", "supports(capability)", "close()"):
            assert f"| `{method}` |" in table

    def test_gated_methods_absent(self, gen_features_module, graph):
        table = gen_features_module.project_store_api_ungated(graph)
        for method in ("read(", "write(", "delete("):
            assert f"`{method}" not in table

    def test_drift_guard_raises_on_mismatch(self, gen_features_module):
        """A curated/graph mismatch must fail generation, not ship a stale table."""
        # A graph whose only ungated Store method is a name not in the curated map.
        fake_graph = {
            "nodes": [
                {"id": "mtd:remote_store._store.Store.brand_new", "kind": "method", "gated": False},
            ],
            "edges": [],
        }
        with pytest.raises(ValueError, match="drifted"):
            gen_features_module.project_store_api_ungated(fake_graph)

    def test_matches_graph_membership(self, gen_features_module, graph):
        """The rendered rows are exactly the graph's ungated Store method set."""
        table = gen_features_module.project_store_api_ungated(graph)
        graph_ungated = {
            n["id"].removeprefix("mtd:remote_store._store.Store.")
            for n in graph["nodes"]
            if n["kind"] == "method"
            and n["id"].startswith("mtd:remote_store._store.Store.")
            and n.get("gated") is False
        }
        rendered = {line.split("`")[1].split("(")[0] for line in table.splitlines() if line.startswith("| `")}
        assert rendered == graph_ungated


class TestAsyncBackendPairs:
    def test_header_row(self, gen_features_module, graph):
        table = gen_features_module.project_async_backend_pairs(graph)
        lines = table.splitlines()
        assert lines[0] == "| Sync backend | Async backend | Capability delta |"
        assert lines[1] == "|---|---|---|"

    def test_azure_pair_no_delta(self, gen_features_module, graph):
        table = gen_features_module.project_async_backend_pairs(graph)
        azure_row = next(row for row in table.splitlines() if row.startswith("| `AzureBackend` |"))
        cols = [c.strip() for c in azure_row.split("|")[1:-1]]
        assert cols[1] == "`AsyncAzureBackend`"
        assert cols[2] == "—"

    def test_memory_pair_reports_lazy_read_delta(self, gen_features_module, graph):
        table = gen_features_module.project_async_backend_pairs(graph)
        mem_row = next(row for row in table.splitlines() if row.startswith("| `MemoryBackend` |"))
        assert "`AsyncMemoryBackend`" in mem_row
        assert "async adds `LAZY_READ`" in mem_row

    def test_async_only_backend_absent(self, gen_features_module, graph):
        """GraphBackend has no sync mirror, so it must not appear in the pairing table."""
        table = gen_features_module.project_async_backend_pairs(graph)
        assert "GraphBackend" not in table

    def test_sorted_by_sync_backend(self, gen_features_module, graph):
        table = gen_features_module.project_async_backend_pairs(graph)
        names = [row.split("|")[1].strip().strip("`") for row in table.splitlines()[2:] if row.startswith("| `")]
        assert names == sorted(names)


class TestRetryability:
    def test_status_table_header(self, gen_features_module, graph):
        table = gen_features_module.project_retryability(graph)
        lines = table.splitlines()
        assert lines[0] == "| Status | Disposition | Surfaced as |"
        assert lines[1] == "|---|---|---|"

    def test_all_classified_statuses_rendered(self, gen_features_module, graph):
        """Every retryable and terminal status appears exactly once, sourced from code."""
        from remote_store._retry import RETRYABLE_STATUSES, TERMINAL_STATUSES

        table = gen_features_module.project_retryability(graph)
        for status in RETRYABLE_STATUSES | TERMINAL_STATUSES:
            assert f"| `{status}` |" in table

    def test_retryable_rows_surface_backend_unavailable(self, gen_features_module, graph):
        table = gen_features_module.project_retryability(graph)
        for line in table.splitlines():
            if line.startswith("| `429` |") or line.startswith("| `503` |"):
                assert "Retried" in line
                assert "`BackendUnavailable`" in line

    def test_terminal_rows_map_to_typed_errors(self, gen_features_module, graph):
        table = gen_features_module.project_retryability(graph)
        expected = {"404": "`NotFound`", "403": "`PermissionDenied`", "423": "`ResourceLocked`"}
        for status, error in expected.items():
            row = next(line for line in table.splitlines() if line.startswith(f"| `{status}` |"))
            assert "Not retried" in row
            assert error in row

    def test_mechanism_table_lists_all_backends(self, gen_features_module, graph):
        table = gen_features_module.project_retryability(graph)
        types = [t for t, _ in gen_features_module._parse_registry_order()]
        for type_str in types:
            assert f"| `{type_str}` |" in table

    def test_status_drift_guard_raises(self, gen_features_module, graph, monkeypatch):
        """Dropping a code-classified status from the curated detail must fail generation."""
        pruned = {s: d for s, d in gen_features_module._STATUS_DETAIL.items() if s != 404}
        monkeypatch.setattr(gen_features_module, "_STATUS_DETAIL", pruned)
        with pytest.raises(ValueError, match="drifted"):
            gen_features_module.project_retryability(graph)

    def test_mechanism_drift_guard_raises(self, gen_features_module, graph, monkeypatch):
        pruned = {t: m for t, m in gen_features_module._RETRY_MECHANISM.items() if t != "local"}
        monkeypatch.setattr(gen_features_module, "_RETRY_MECHANISM", pruned)
        with pytest.raises(ValueError, match="drifted"):
            gen_features_module.project_retryability(graph)

    def test_http_row_carries_408_footnote(self, gen_features_module, graph):
        """The http mechanism row is marked and a footnote documents its 408 extension.

        The shared status table is generated from ``_retry`` only, so 408 (which
        the sync http backend retries as a transport-local extension) would
        otherwise read as unclassified/terminal for http.
        """
        table = gen_features_module.project_retryability(graph)
        http_row = next(line for line in table.splitlines() if line.startswith("| `http`"))
        assert "†" in http_row
        assert "408" in table
        assert "transport-local extension" in table

    def test_http_408_extension_drift_guard_raises(self, gen_features_module, graph, monkeypatch):
        """A change to _http's transient-status extension must fail generation.

        Closes the backend-local-drift gap: the footnote's 408 claim is checked
        live against ``_http._TRANSIENT_STATUSES``, so a new http-local status
        cannot land without updating the footnote.
        """
        import remote_store.backends._http as http_mod
        from remote_store._retry import RETRYABLE_STATUSES

        monkeypatch.setattr(http_mod, "_TRANSIENT_STATUSES", RETRYABLE_STATUSES | {408, 425})
        with pytest.raises(ValueError, match="extension drifted"):
            gen_features_module.project_retryability(graph)


class TestAtomicity:
    def test_header_row(self, gen_features_module, graph):
        table = gen_features_module.project_atomicity(graph)
        lines = table.splitlines()
        assert lines[0] == "| Backend | `write` | `write_atomic` | `move` | `copy` |"
        assert lines[1] == "|---|---|---|---|---|"

    def test_all_registered_backends_present(self, gen_features_module, graph):
        table = gen_features_module.project_atomicity(graph)
        for type_str, _ in gen_features_module._parse_registry_order():
            assert f"| `{type_str}` |" in table

    def test_representative_cells(self, gen_features_module, graph):
        table = gen_features_module.project_atomicity(graph)
        rows = {line.split("`")[1]: line for line in table.splitlines() if line.startswith("| `")}
        assert "Copy+delete" in rows["s3"]  # non-atomic move surfaced, not hidden
        # s3-pyarrow: plain write is non-atomic (truncated multipart per AW-007),
        # while write_atomic buffers the body first and IS atomic — the reverse of s3fs.
        pa_write, pa_write_atomic = (c.strip() for c in rows["s3-pyarrow"].split("|")[2:4])
        assert not pa_write.startswith("Atomic")
        assert pa_write_atomic == "Atomic"
        assert rows["sql-blob"].count("Atomic") == 4  # all four ops atomic
        assert "read-only" in rows["http"]

    def test_footnotes_present(self, gen_features_module, graph):
        table = gen_features_module.project_atomicity(graph)
        assert "truncated" in table  # ‡ s3-pyarrow plain-write footnote
        assert "posix_rename" in table  # † azure/sftp footnote

    def test_move_cell_cross_checked_against_atomic_move(self, gen_features_module, graph, monkeypatch):
        """A curated 'Atomic' move for a backend lacking ATOMIC_MOVE must fail generation."""
        tampered = {t: dict(cells) for t, cells in gen_features_module._ATOMICITY.items()}
        tampered["s3"]["move"] = "Atomic"  # s3 does not declare ATOMIC_MOVE
        monkeypatch.setattr(gen_features_module, "_ATOMICITY", tampered)
        with pytest.raises(ValueError, match="ATOMIC_MOVE"):
            gen_features_module.project_atomicity(graph)


class TestConsistency:
    def test_header_rows(self, gen_features_module, graph):
        table = gen_features_module.project_consistency(graph)
        assert "| Backend | Read-after-write | Listing consistency |" in table
        assert "| Async backend | Read-after-write | Listing consistency |" in table

    def test_all_registered_backends_present(self, gen_features_module, graph):
        table = gen_features_module.project_consistency(graph)
        for type_str, _ in gen_features_module._parse_registry_order():
            assert f"| `{type_str}` |" in table

    def test_async_backends_present(self, gen_features_module, graph):
        table = gen_features_module.project_consistency(graph)
        for cls_name in ("AsyncAzureBackend", "AsyncMemoryBackend", "GraphBackend"):
            assert f"| `{cls_name}` |" in table

    def test_representative_cells(self, gen_features_module, graph):
        table = gen_features_module.project_consistency(graph)
        rows = {line.split("`")[1]: line for line in table.splitlines() if line.startswith("| `")}
        # Read/write backends normalise to strong; read-only backends carry no guarantee.
        assert rows["local"] == "| `local` | Strong | Strong |"
        assert "read-only" in rows["http"]
        assert "read-only" in rows["sql-query"]
        # S3 listing carries the opt-in-cache caveat marker; object read is unmarked.
        s3_read, s3_listing = (c.strip() for c in rows["s3"].split("|")[2:4])
        assert s3_read == "Strong"
        assert s3_listing == r"Strong\*"
        # Graph (async-only) carries the async-monitor caveat marker.
        assert "†" in rows["GraphBackend"]

    def test_footnotes_present(self, gen_features_module, graph):
        table = gen_features_module.project_consistency(graph)
        assert "use_listings_cache" in table  # * s3 listing-cache caveat
        assert "read-your-writes" in table  # † graph read-your-writes / async monitor

    def test_sync_key_set_drift_guard_raises(self, gen_features_module, graph, monkeypatch):
        pruned = {t: c for t, c in gen_features_module._CONSISTENCY.items() if t != "local"}
        monkeypatch.setattr(gen_features_module, "_CONSISTENCY", pruned)
        with pytest.raises(ValueError, match="drifted from the registry"):
            gen_features_module.project_consistency(graph)

    def test_async_key_set_drift_guard_raises(self, gen_features_module, graph, monkeypatch):
        pruned = {c: v for c, v in gen_features_module._CONSISTENCY_ASYNC.items() if c != "GraphBackend"}
        monkeypatch.setattr(gen_features_module, "_CONSISTENCY_ASYNC", pruned)
        with pytest.raises(ValueError, match="drifted from the graph"):
            gen_features_module.project_consistency(graph)

    def test_s3_listings_cache_default_guard_raises(self, gen_features_module, graph, monkeypatch):
        """Flipping S3's listings-cache default on must fail generation.

        The ``*`` footnote asserts s3 / s3-pyarrow listings are strong *by
        default*; that holds only while the s3fs DirCache is off by default, so
        the footnote is cross-checked live against
        ``_s3_base._DEFAULT_USE_LISTINGS_CACHE``.
        """
        import remote_store.backends._s3_base as s3_base

        monkeypatch.setattr(s3_base, "_DEFAULT_USE_LISTINGS_CACHE", True)
        with pytest.raises(ValueError, match="use_listings_cache flipped on"):
            gen_features_module.project_consistency(graph)


class TestCost:
    def test_header_rows(self, gen_features_module, graph):
        table = gen_features_module.project_cost(graph)
        assert "| Backend | `read` | `metadata` | `list` |" in table
        assert "| Async backend | `read` | `metadata` | `list` |" in table

    def test_all_registered_backends_present(self, gen_features_module, graph):
        table = gen_features_module.project_cost(graph)
        for type_str, _ in gen_features_module._parse_registry_order():
            assert f"| `{type_str}` |" in table

    def test_async_backends_present(self, gen_features_module, graph):
        table = gen_features_module.project_cost(graph)
        for cls_name in ("AsyncAzureBackend", "AsyncMemoryBackend", "GraphBackend"):
            assert f"| `{cls_name}` |" in table

    def test_representative_cells(self, gen_features_module, graph):
        table = gen_features_module.project_cost(graph)
        rows = {line.split("`")[1]: line for line in table.splitlines() if line.startswith("| `")}
        # A LAZY_READ backend streams; a non-LAZY_READ one materialises with the * marker.
        assert rows["local"].split("|")[2].strip() == "Streaming"
        assert r"\*" in rows["sql-blob"]  # full BLOB into memory
        # http has no LIST capability; the list cell says so rather than guessing a cost.
        assert "no `LIST`" in rows["http"]
        # sync memory buffers where its async peer streams — the two must not converge.
        assert "Buffered" in rows["memory"]
        assert rows["AsyncMemoryBackend"].split("|")[2].strip() == "Streaming"

    def test_footnote_present(self, gen_features_module, graph):
        table = gen_features_module.project_cost(graph)
        assert "LAZY_READ" in table  # * materialisation footnote cites the missing capability
        assert "larger than process memory" in table

    def test_read_cell_cross_checked_against_lazy_read(self, gen_features_module, graph, monkeypatch):
        """A `read` cell that disagrees with the graph's LAZY_READ must fail generation.

        `local` declares LAZY_READ, so flipping its cell off "Streaming" contradicts
        the capability — the guard that keeps the streaming-vs-materialised class
        honest (mirrors the ATOMIC_MOVE cross-check on the atomicity `move` cell).
        """
        tampered = {t: dict(c) for t, c in gen_features_module._COST.items()}
        tampered["local"]["read"] = r"Buffered in memory\*"
        monkeypatch.setattr(gen_features_module, "_COST", tampered)
        with pytest.raises(ValueError, match="disagrees with the graph's LAZY_READ"):
            gen_features_module.project_cost(graph)

    def test_sync_key_set_drift_guard_raises(self, gen_features_module, graph, monkeypatch):
        pruned = {t: c for t, c in gen_features_module._COST.items() if t != "local"}
        monkeypatch.setattr(gen_features_module, "_COST", pruned)
        with pytest.raises(ValueError, match="drifted from the registry"):
            gen_features_module.project_cost(graph)

    def test_async_key_set_drift_guard_raises(self, gen_features_module, graph, monkeypatch):
        pruned = {c: v for c, v in gen_features_module._COST_ASYNC.items() if c != "GraphBackend"}
        monkeypatch.setattr(gen_features_module, "_COST_ASYNC", pruned)
        with pytest.raises(ValueError, match="drifted from the graph"):
            gen_features_module.project_cost(graph)


class TestFeaturesReturnTypeAccuracy:
    """BUG-227: FEATURES.md §LIST / §GLOB return-type cells must match the Store signatures.

    The iterating reads moved off ``Iterator[str]`` long ago (ID-072 changed
    ``list_folders`` / ``iter_children`` to yield ``FolderEntry``), but the
    hand-authored method tables were never updated. Cross-check each documented
    cell against the live signature so the two cannot silently drift again.
    """

    @pytest.mark.parametrize("method", ["list_files", "list_folders", "iter_children", "glob"])
    def test_documented_return_type_matches_signature(self, method):
        import inspect
        import re

        from remote_store import Store

        # Under ``from __future__ import annotations`` the return annotation is a
        # string (e.g. "Iterator[FileInfo]"), which is exactly what we compare against.
        actual = str(inspect.signature(getattr(Store, method)).return_annotation)
        text = (ROOT / "FEATURES.md").read_text(encoding="utf-8")
        row = re.search(rf"\|\s*`{method}\([^`]*\)`\s*\|\s*`([^`]+)`\s*\|", text)
        assert row, f"no FEATURES.md Store-API row found for {method}()"
        documented = row.group(1).replace(r"\|", "|")  # unescape the Markdown pipe

        def _norm(s: str) -> str:
            return re.sub(r"\s+", "", s)

        assert _norm(documented) == _norm(actual), (
            f"{method}(): FEATURES.md documents {documented!r} but the signature is {actual!r}"
        )


class TestRegionReplacement:
    def test_replaces_known_region(self, gen_features_module):
        text = "before\n<!-- BEGIN_GENERATED:foo -->\nold content\n<!-- END_GENERATED:foo -->\nafter"
        result = gen_features_module._replace_regions(text, {"foo": "new content"})
        assert "old content" not in result
        assert "new content" in result
        assert "before" in result
        assert "after" in result

    def test_leaves_unmatched_document_region_untouched(self, gen_features_module):
        # Region in document without a corresponding projection key is left as-is.
        text = (
            "<!-- BEGIN_GENERATED:foo -->\nfoo content\n<!-- END_GENERATED:foo -->\n"
            "<!-- BEGIN_GENERATED:bar -->\nbar content\n<!-- END_GENERATED:bar -->"
        )
        result = gen_features_module._replace_regions(text, {"foo": "new foo"})
        assert "new foo" in result
        assert "bar content" in result

    def test_raises_if_projection_key_not_in_document(self, gen_features_module):
        text = "<!-- BEGIN_GENERATED:bar -->\nstuff\n<!-- END_GENERATED:bar -->"
        with pytest.raises(ValueError, match="other"):
            gen_features_module._replace_regions(text, {"other": "x"})

    def test_replaces_multiple_regions(self, gen_features_module):
        text = (
            "<!-- BEGIN_GENERATED:a -->\nA old\n<!-- END_GENERATED:a -->\n"
            "middle\n"
            "<!-- BEGIN_GENERATED:b -->\nB old\n<!-- END_GENERATED:b -->"
        )
        result = gen_features_module._replace_regions(text, {"a": "A new", "b": "B new"})
        assert "A new" in result
        assert "B new" in result
        assert "old" not in result


class TestFeaturesFileIntegrity:
    def test_features_md_has_all_regions(self):
        text = (ROOT / "FEATURES.md").read_text(encoding="utf-8")
        for region in (
            "store_api_gated",
            "store_api_ungated",
            "backends_main",
            "backends_flags",
            "backends_async",
            "backends_async_flags",
            "async_backend_pairs",
            "retryability",
            "atomicity",
            "consistency",
            "cost",
            "install_extras",
        ):
            assert f"<!-- BEGIN_GENERATED:{region} -->" in text
            assert f"<!-- END_GENERATED:{region} -->" in text

    def test_features_md_is_up_to_date(self, gen_features_module, graph, pyproject):
        """Generated regions in FEATURES.md must match current projection output."""
        text = (ROOT / "FEATURES.md").read_text(encoding="utf-8")
        text_lf = text.replace("\r\n", "\n")
        projections = gen_features_module.project_all(graph, pyproject)
        updated = gen_features_module._replace_regions(text_lf, projections)
        assert text_lf == updated, "FEATURES.md generated regions are out of date. Run: hatch run gen-features"
