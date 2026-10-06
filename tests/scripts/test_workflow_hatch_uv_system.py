"""Pin that no CI step runs hatch under ``UV_SYSTEM_PYTHON=1`` (BK-411).

hatch's uv installer honours ``UV_SYSTEM_PYTHON``: set truthy, it syncs the
env's features into the runner's Python and leaves hatch's ``.venv`` without
them (the BK-269 "uv drops features in CI" failure). Most workflows set it
workflow-wide for their bare ``uv pip install`` steps, so every step that runs
hatch must resolve it falsy through step, job or workflow ``env``. Composite
actions cannot see their caller's env here, so a hatch step in one must set it
falsy itself.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

_GITHUB = Path(__file__).resolve().parents[2] / ".github"
_HATCH = re.compile(r"\bhatch\b")
_FALSY = {"", "0", "false"}


def _falsy(value: Any) -> bool:
    return value is None or str(value).strip().lower() in _FALSY


def _env(*scopes: dict[str, Any] | None) -> Any:
    """Innermost scope wins, as in GitHub Actions (step > job > workflow)."""
    for scope in scopes:
        if scope and "UV_SYSTEM_PYTHON" in (scope.get("env") or {}):
            return scope["env"]["UV_SYSTEM_PYTHON"]
    return None


def _violations(doc: dict[str, Any], name: str) -> tuple[list[str], int]:
    """Return (offending step labels, hatch steps seen) for one workflow or action."""
    bad: list[str] = []
    seen = 0
    if "runs" in doc:  # composite action: only the step's own env is knowable
        jobs = {"(composite)": {"steps": doc["runs"].get("steps") or []}}
        workflow: dict[str, Any] | None = None
    else:
        jobs = doc.get("jobs") or {}
        workflow = doc
    for job_id, job in jobs.items():
        for i, step in enumerate(job.get("steps") or []):
            if not _HATCH.search(str(step.get("run", ""))):
                continue
            seen += 1
            if workflow is None:  # unset inherits the caller's env, which may be truthy
                ok = "UV_SYSTEM_PYTHON" in (step.get("env") or {}) and _falsy(_env(step))
            else:
                ok = _falsy(_env(step, job, workflow))
            if not ok:
                bad.append(f"{name}:{job_id}:step{i}")
    return bad, seen


def _documents() -> list[tuple[str, dict[str, Any]]]:
    paths = sorted(_GITHUB.glob("workflows/*.yml")) + sorted(_GITHUB.glob("actions/*/action.yml"))
    return [(str(p.relative_to(_GITHUB)), yaml.safe_load(p.read_text(encoding="utf-8"))) for p in paths]


def test_every_hatch_step_runs_with_uv_system_python_falsy():
    bad: list[str] = []
    seen = 0
    for name, doc in _documents():
        doc_bad, doc_seen = _violations(doc, name)
        bad += doc_bad
        seen += doc_seen
    assert bad == []
    # Non-vacuous: ci.yml's lint (3 steps) and docs (1 step) run hatch today.
    assert seen >= 4


def test_workflow_wide_flag_without_job_override_is_flagged():
    doc = {
        "env": {"UV_SYSTEM_PYTHON": 1},
        "jobs": {
            "gate": {"steps": [{"run": "uvx hatch run lint"}]},
            "safe": {"env": {"UV_SYSTEM_PYTHON": "0"}, "steps": [{"run": "uvx hatch run lint"}]},
            "plain": {"steps": [{"run": 'uv pip install -e ".[dev]"'}]},
        },
    }
    bad, seen = _violations(doc, "synthetic.yml")
    assert bad == ["synthetic.yml:gate:step0"]
    assert seen == 2


def test_step_env_overrides_a_falsy_job_env():
    doc = {
        "jobs": {
            "gate": {
                "env": {"UV_SYSTEM_PYTHON": "0"},
                "steps": [{"run": "hatch run docs-gate", "env": {"UV_SYSTEM_PYTHON": "true"}}],
            }
        }
    }
    assert _violations(doc, "synthetic.yml") == (["synthetic.yml:gate:step0"], 1)


def test_composite_action_hatch_step_needs_its_own_falsy_env():
    step: dict[str, Any] = {"run": "hatch run lint", "shell": "bash"}
    doc = {"runs": {"using": "composite", "steps": [step]}}
    flagged = (["actions/x/action.yml:(composite):step0"], 1)
    assert _violations(doc, "actions/x/action.yml") == flagged  # unset: caller's env leaks in
    step["env"] = {"UV_SYSTEM_PYTHON": "1"}
    assert _violations(doc, "actions/x/action.yml") == flagged
    step["env"] = {"UV_SYSTEM_PYTHON": "0"}
    assert _violations(doc, "actions/x/action.yml") == ([], 1)
