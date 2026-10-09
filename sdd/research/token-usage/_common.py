"""Shared inputs, constants and helpers for the token-usage analysis scripts.

Every script takes ``--repo-root`` (default: the checkout this file sits in),
``--data`` (the directory ``extract.py`` writes and the others read; default
``<repo-root>/tmp/token-usage-data``, which is gitignored) and ``--results``
(default: ``results/`` beside this file). Extracts hold prompts, local paths
and session IDs, so they never leave ``--data``; only aggregated figures are
written to ``--results``, each with a ``_provenance`` block naming the script
and the SHA-256 of every input it read.
"""

from __future__ import annotations

import argparse
import collections
import datetime as _dt
import hashlib
import json
import re
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping

HERE = Path(__file__).resolve().parent
DEFAULT_REPO = HERE.parents[2]

# Relative price per token class (Anthropic's published ratios): input 1,
# cache read 0.1, 5-minute write 1.25, 1-hour write 2, output 5.
W = {"input": 1.0, "read": 0.1, "w5": 1.25, "w1h": 2.0, "out": 5.0}
# Tokens per character, from calibrate.py's regression of context growth
# between consecutive calls. "hidden" is tokens of context per hidden output token.
COEF = {"tool_result": 0.421, "attachment": 0.411, "user": 0.411, "assistant": 0.318, "hidden": 0.947}
# Dollars per unit (input-token equivalent), fitted by calibrate.py to the
# cost-state records Claude Code writes per session.
PRICE = {"claude-opus-5-5": 2.31e-6, "claude-opus-5": 5.05e-6}

# Work items compared across transcripts, traces and PRs. Sessions are
# assigned to an item through the PR they served (see ``session_prs``), never
# by session ID.
WORK = {
    "BUG-264": {"prs": [992], "traces": ["bug-264-azure-blank-error-message.yml"], "kind": "/ship (2026-09-05)"},
    "BK-397": {"prs": [1073], "traces": ["bk-397-recorder.yml"], "kind": "/ship + 5 rvw-pr sessions"},
    "BK-403": {"prs": [1074], "traces": ["bk-403-rfc-0019-phase-0.yml"], "kind": "interactive research"},
    "BUG-304/305": {
        "prs": [1071],
        "traces": ["bug-304-windows-tooling-tests.yml", "bug-305-report-trace-outcomes-cp1252.yml"],
        "kind": "interactive + 2 rvw-pr",
    },
    "ID-268": {"prs": [1072], "traces": [], "kind": "fix-pr + 2 rvw-pr"},
    "v0.33.0 release": {"prs": [1069], "traces": [], "kind": "/release + fix-pr + 2 rvw-pr"},
    "BUG-303 (review only)": {
        "prs": [1068],
        "traces": ["bug-303-mutation-gremlins-1-10-throughput.yml"],
        "kind": "1 rvw-pr",
    },
    "ID-256 (review only)": {"prs": [968], "traces": ["ID-256-kernsatz-rule.yml"], "kind": "/orchestrate review panel"},
}


def parser(doc: str | None, *, data: bool = True, results: bool = True) -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=(doc or "").strip().splitlines()[0] if doc else None)
    ap.add_argument("--repo-root", type=Path, default=DEFAULT_REPO, help="checkout to read sdd/ and git from")
    if data:
        ap.add_argument(
            "--data", type=Path, default=None, help="extract directory (default <repo-root>/tmp/token-usage-data)"
        )
    if results:
        ap.add_argument("--results", type=Path, default=HERE / "results", help="where aggregated JSON goes")
    return ap


def resolve(args: argparse.Namespace) -> argparse.Namespace:
    args.repo_root = args.repo_root.resolve()
    if getattr(args, "data", "absent") is None:
        args.data = args.repo_root / "tmp" / "token-usage-data"
    return args


def default_transcripts(repo: Path) -> list[Path]:
    """Claude Code's transcript folders for *repo*: the one ``scripts/report_token_usage.py``'s
    ``default_dir`` computes, plus the sibling folders a worktree of that checkout gets."""
    base = Path.home() / ".claude" / "projects"
    slug = re.sub(r"[^A-Za-z0-9]", "-", str(repo))
    if not base.is_dir():
        return []
    return sorted(d for d in base.iterdir() if d.is_dir() and d.name.startswith(slug))


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def write_result(results: Path, name: str, script: str, inputs: Mapping[str, Path | str], payload: dict) -> Path:
    """Write ``results/<name>.json`` with a provenance block; inputs are hashed, not copied."""
    results.mkdir(parents=True, exist_ok=True)
    prov = {
        "script": f"{script}.py",
        "generated": _dt.date.today().isoformat(),
        # a file is recorded by its hash; a string (a commit, a query) verbatim
        "inputs": {k: p if isinstance(p, str) else sha256(p) for k, p in inputs.items()},
    }
    out = results / f"{name}.json"
    out.write_text(json.dumps({"_provenance": prov, **payload}, indent=1, sort_keys=False) + "\n", encoding="utf-8")
    print(f"written: {out.relative_to(HERE) if out.is_relative_to(HERE) else out}")
    return out


def load_extract(data: Path):
    """(calls, items, sessions) from extract.py's output; synthetic calls dropped."""
    calls = [json.loads(line) for line in (data / "calls.jsonl").open(encoding="utf-8")]
    calls = [c for c in calls if c["model"] != "<synthetic>"]
    items = [json.loads(line) for line in (data / "items.jsonl").open(encoding="utf-8")]
    sessions = json.loads((data / "sessions.json").read_text(encoding="utf-8"))
    return calls, items, sessions


def extract_inputs(data: Path) -> dict[str, Path]:
    return {n: data / n for n in ("calls.jsonl", "items.jsonl", "sessions.json")}


def by_file(calls):
    out = collections.defaultdict(list)
    for c in calls:
        out[c["file"]].append(c)
    return out


def segment_ends(bycall) -> dict:
    """(transcript, segment) -> index one past its last call; an item stops being re-read there."""
    ends: dict = {}
    for f, cs in bycall.items():
        for c in cs:
            ends[(f, c["seg"])] = max(ends.get((f, c["seg"]), 0), c["idx"] + 1)
    return ends


def group(kind: str) -> str:
    if kind.startswith("tool_result"):
        return "tool_result"
    if kind == "attachment":
        return "attachment"
    if kind.startswith("assistant"):
        return "assistant"
    return "user"


_PR_IN_PROMPT = re.compile(r"(?:/(?:rvw-pr|fix-pr|ship|orchestrate)\b|\breview pr\b)\D{0,40}?#?(\d{3,5})", re.I)


def session_prs(s: dict, head_branch_to_pr: dict[str, int]) -> set[int]:
    """PRs a main session served: a ``pr-link`` record, or a PR number its first real prompt
    hands a review or fix skill. Only when neither exists, a git branch that is some PR's
    head branch: a session that opened its own PR may also have checked out another's."""
    out = {int(p) for p in s.get("prs") or [] if p}
    out |= {int(m.group(1)) for m in _PR_IN_PROMPT.finditer(s.get("first_prompt") or "")}
    if not out:
        out = {head_branch_to_pr[b] for b in s.get("branches") or [] if b in head_branch_to_pr}
    return out


def work_groups(sessions: dict, prs: list[dict]) -> dict[str, set[str]]:
    """Work item -> set of session parents (a main session and its subagents share one)."""
    head = {p["branch"]: p["number"] for p in prs if p.get("branch") not in (None, "master", "main")}
    served = {s["parent"]: session_prs(s, head) for s in sessions.values() if not s["is_sub"]}
    return {name: {parent for parent, ps in served.items() if ps & set(w["prs"])} for name, w in WORK.items()}


def load_prs(data: Path) -> list[dict]:
    return json.loads((data / "prs.json").read_text(encoding="utf-8"))


def pct(x: float, total: float, nd: int = 1) -> float:
    return round(100 * x / total, nd) if total else 0.0
