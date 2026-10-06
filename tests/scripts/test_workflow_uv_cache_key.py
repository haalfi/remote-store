"""Pin that every cached ``setup-uv`` step names its Python (BUG-308).

Without a ``python-version`` input, setup-uv builds the cache key from
``uv python find`` -> ``python --version``: the runner image's full patch
version (3.13.15 on one image, 3.13.16 on the next), or ``unknown`` when the
find fails. One leg saves each shared key (BK-411), so a saver and its
restore-only readers on different images miss each other. With the input set,
the key carries that literal string and is image-independent.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

_GITHUB = Path(__file__).resolve().parents[2] / ".github"


def _caches(with_: dict[str, Any]) -> bool:
    # setup-uv defaults enable-cache to "auto", which caches on GitHub-hosted runners.
    return str(with_.get("enable-cache", "auto")).strip().lower() not in {"false", "0"}


def _violations(doc: dict[str, Any], name: str) -> tuple[list[str], int]:
    """Return (cached setup-uv steps without python-version, cached setup-uv steps seen)."""
    bad: list[str] = []
    seen = 0
    for job_id, job in (doc.get("jobs") or {}).items():
        for i, step in enumerate(job.get("steps") or []):
            if not str(step.get("uses", "")).startswith("astral-sh/setup-uv@"):
                continue
            with_ = step.get("with") or {}
            if not _caches(with_):
                continue
            seen += 1
            if not str(with_.get("python-version", "")).strip():
                bad.append(f"{name}:{job_id}:step{i}")
    return bad, seen


def test_every_cached_setup_uv_step_sets_python_version():
    bad: list[str] = []
    seen = 0
    for path in sorted(_GITHUB.glob("workflows/*.yml")):
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        doc_bad, doc_seen = _violations(doc, path.name)
        bad += doc_bad
        seen += doc_seen
    assert bad == []
    # Non-vacuous: ci.yml's five uv-dev steps and its test-cross-platform step,
    # plus ci-full.yml's test-full, cache today.
    assert seen >= 7


def test_default_enable_cache_counts_as_caching():
    doc = {
        "jobs": {
            "auto": {"steps": [{"uses": "astral-sh/setup-uv@v10.2.0"}]},
            "pinned": {"steps": [{"uses": "astral-sh/setup-uv@v10.2.0", "with": {"python-version": "3.13"}}]},
            "off": {"steps": [{"uses": "astral-sh/setup-uv@v10.2.0", "with": {"enable-cache": False}}]},
            "other": {"steps": [{"uses": "actions/setup-python@v7"}]},
        }
    }
    assert _violations(doc, "synthetic.yml") == (["synthetic.yml:auto:step0"], 2)
