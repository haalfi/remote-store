"""Unit tests for benchmarks/slim_run_of_record.py (ID-230).

The run-of-record slimming + guard exists because the chart generators degrade
*silently* when their input is shaped wrong — a bad run ships a blank or
placeholder SVG with no error. These tests pin the three guarded invariants
(§3.5 of the ID-230 plan) and the divergence from the baseline recipe (the
top-level ``network_profile`` key is retained, not dropped).
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from benchmarks import slim_run_of_record as slim

if TYPE_CHECKING:
    from pathlib import Path

_RAW_SDK = {
    "s3": "boto3_raw",
    "s3-pyarrow": "boto3_raw",
    "sftp": "paramiko_raw",
    "azure": "azure_blob_raw",
    "s3-latency": "boto3_raw",
    "sftp-latency": "paramiko_raw",
    "azure-latency": "azure_blob_raw",
}


def _entry(test: str, backend: str, target: str, payload: int | None = None, mean: float = 0.01) -> dict[str, Any]:
    params: dict[str, Any] = {"bench_target": [backend, target]}
    if payload is not None:
        params["payload"] = payload
    # extra_info is carried in real runs; the slim must drop it.
    return {
        "name": f"{test}[{backend}-{target}]",
        "params": params,
        "stats": {"mean": mean, "stddev": 1.0},
        "extra_info": {"x": 1},
    }


def _overhead_entries(backend: str, target: str) -> list[dict[str, Any]]:
    return [
        _entry("test_write_bytes", backend, target, payload=1048576),
        _entry("test_read_bytes", backend, target, payload=1048576),
        _entry("test_exists_hit", backend, target),
        _entry("test_list_files", backend, target),
        _entry("test_delete", backend, target),
    ]


def _clean_raw(backends: list[str]) -> dict[str, Any]:
    benches: list[dict[str, Any]] = []
    for b in backends:
        benches += _overhead_entries(b, "remote_store")
        benches += _overhead_entries(b, _RAW_SDK[b])
    return {
        "network_profile": "clean",
        "machine_info": {"cpu": {"brand_raw": "Test CPU"}, "python_version": "3.13"},
        "benchmarks": benches,
        "version": "should-be-dropped",
    }


def _rtt_raw(profile: str, backends: list[str]) -> dict[str, Any]:
    benches: list[dict[str, Any]] = []
    for b in backends:
        benches += _overhead_entries(b, "remote_store")
        benches += _overhead_entries(b, _RAW_SDK[b])
    return {"network_profile": profile, "machine_info": {}, "benchmarks": benches}


def _write(path: Path, data: dict[str, Any]) -> Path:
    path.write_text(json.dumps(data))
    return path


def test_slim_keeps_only_generator_fields(tmp_path: Path) -> None:
    src = _write(tmp_path / "clean-raw.json", _clean_raw(["s3", "s3-pyarrow", "sftp", "azure"]))
    dest = slim.slim_file(src, tmp_path / "out")
    assert dest.name == "clean.json"
    out = json.loads(dest.read_text())
    # Top-level keeps network_profile + machine_info + benchmarks, nothing else.
    assert set(out) == {"network_profile", "machine_info", "benchmarks"}
    assert out["network_profile"] == "clean"
    # Each entry slimmed to name / params / stats.mean — extra_info and stddev gone.
    entry = out["benchmarks"][0]
    assert set(entry) == {"name", "params", "stats"}
    assert set(entry["stats"]) == {"mean"}
    assert "extra_info" not in entry


def test_slim_retains_network_profile_for_latency_file(tmp_path: Path) -> None:
    # The divergence from the baseline recipe: rtt files MUST keep network_profile
    # so charts.py groups them correctly; the filename derives from it.
    src = _write(tmp_path / "rtt50-raw.json", _rtt_raw("rtt50", ["s3-latency", "sftp-latency", "azure-latency"]))
    dest = slim.slim_file(src, tmp_path / "out")
    assert dest.name == "rtt50.json"
    assert json.loads(dest.read_text())["network_profile"] == "rtt50"


def test_guard_passes_on_well_formed_set(tmp_path: Path) -> None:
    out = tmp_path / "out"
    slim.slim_file(_write(tmp_path / "c.json", _clean_raw(["s3", "s3-pyarrow", "sftp", "azure"])), out)
    slim.slim_file(_write(tmp_path / "r.json", _rtt_raw("rtt20", ["s3-latency", "sftp-latency", "azure-latency"])), out)
    assert slim.guard(out) == []


def test_guard_flags_single_profile(tmp_path: Path) -> None:
    # Guard 1: only a clean file -> overhead-vs-rtt would render its placeholder.
    out = tmp_path / "out"
    slim.slim_file(_write(tmp_path / "c.json", _clean_raw(["s3", "s3-pyarrow", "sftp", "azure"])), out)
    errors = slim.guard(out)
    assert any("guard 1" in e for e in errors)


def test_guard_flags_dropped_profile_key(tmp_path: Path) -> None:
    # Guard 1: two files that both collapse to "clean" (the profile key was
    # stripped) -> < 2 distinct profiles.
    out = tmp_path / "out"
    out.mkdir()
    _write(out / "clean.json", {"network_profile": "clean", "benchmarks": _overhead_entries("s3", "remote_store")})
    _write(out / "other.json", {"benchmarks": _overhead_entries("s3", "remote_store")})  # no profile key
    assert any("guard 1" in e for e in slim.guard(out))


def test_guard_flags_base_backends_in_latency_file(tmp_path: Path) -> None:
    # Guard 2: rtt file used the base backends, not the -latency variants, so the
    # _LATENCY_VARIANT lookup misses and the series drop silently.
    out = tmp_path / "out"
    slim.slim_file(_write(tmp_path / "c.json", _clean_raw(["s3", "s3-pyarrow", "sftp", "azure"])), out)
    slim.slim_file(_write(tmp_path / "r.json", _rtt_raw("rtt20", ["s3", "sftp", "azure"])), out)
    errors = slim.guard(out)
    assert any("guard 2" in e for e in errors)


def test_guard_flags_clean_missing_comparative_backend(tmp_path: Path) -> None:
    # Guard 3: clean file missing azure -> the single-file comparative charts
    # would be blank for that backend.
    out = tmp_path / "out"
    slim.slim_file(_write(tmp_path / "c.json", _clean_raw(["s3", "s3-pyarrow", "sftp"])), out)
    slim.slim_file(_write(tmp_path / "r.json", _rtt_raw("rtt20", ["s3-latency", "sftp-latency", "azure-latency"])), out)
    errors = slim.guard(out)
    assert any("guard 3" in e and "azure" in e for e in errors)


def test_guard_empty_dir(tmp_path: Path) -> None:
    out = tmp_path / "out"
    out.mkdir()
    assert slim.guard(out) == [f"no run-of-record JSON files in {out}"]
