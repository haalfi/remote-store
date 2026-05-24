"""ID-182: compose the rolling-issue body from per-extra drift reports.

Reads every ``<dir>/<extra>.json`` written by ``drift_check.py diff``,
renders a markdown summary, and reconciles a single rolling GitHub issue
with the resulting state via the ``gh`` CLI (preinstalled on GitHub-hosted
runners).

Logic:

* Any extra with ``status == "drift"`` or ``status == "needs_refresh"``
  → create-or-update the issue.
* All extras clear → comment "drift cleared" on the open issue (if any)
  and close it; no-op if no issue is open.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


def _load_reports(dir_: Path) -> dict[str, dict]:
    reports: dict[str, dict] = {}
    for path in sorted(dir_.glob("*.json")):
        # The matrix uploads artefacts under names like "drift-sftp" containing
        # "sftp.json"; download-artifact merge-multiple flattens that.
        with path.open(encoding="utf-8") as f:
            data = json.load(f)
        reports[data["extra"]] = data
    return reports


def _render_body(reports: dict[str, dict], run_url: str) -> str:
    lines: list[str] = []
    lines.append("Weekly drift check across every `[<extra>]` in `pyproject.toml`.")
    lines.append("")
    lines.append(f"Last run: [{run_url}]({run_url})")
    lines.append("")

    needs_refresh = [e for e, r in reports.items() if r["status"] == "needs_refresh"]
    if needs_refresh:
        lines.append("## Baselines awaiting first population")
        lines.append("")
        lines.append(
            "The following extras have stub baselines. Run "
            "`hatch run drift-check refresh-baseline <extra>` on Python 3.13 "
            "and commit `infra/drift-locks/<extra>.txt` (plus the regenerated "
            "`docs-src/reference/tested-versions.md`):"
        )
        lines.append("")
        for extra in needs_refresh:
            lines.append(f"- `[{extra}]`")
        lines.append("")

    drift_extras = [e for e, r in reports.items() if r["status"] == "drift"]
    if drift_extras:
        lines.append("## Drift detected")
        lines.append("")
        for extra in drift_extras:
            r = reports[extra]
            lines.append(f"### `[{extra}]`")
            lines.append("")
            lines.append(
                f"Baseline captured {r.get('captured', '?')} on Python "
                f"{r.get('python_baseline', '?')}; "
                f"resolved on Python {r.get('python_run', '?')}."
            )
            lines.append("")
            stable = r.get("stable_drift", [])
            if stable:
                lines.append("**Stable-version drift:**")
                lines.append("")
                lines.append("| Package | Baseline | Resolved |")
                lines.append("|---|---|---|")
                for d in stable:
                    lines.append(f"| `{d['package']}` | `{d['baseline'] or '—'}` | `{d['resolved'] or '—'}` |")
                lines.append("")
            pre = r.get("prerelease_drift", [])
            if pre:
                lines.append("**Pre-release drift (informational):**")
                lines.append("")
                lines.append("| Package | Baseline | Resolved |")
                lines.append("|---|---|---|")
                for d in pre:
                    lines.append(f"| `{d['package']}` | `{d['baseline'] or '—'}` | `{d['resolved'] or '—'}` |")
                lines.append("")

    errors = [e for e, r in reports.items() if r.get("status") == "error"]
    if errors:
        lines.append("## Errors")
        lines.append("")
        lines.append(
            "The drift check could not complete for these extras. The most "
            "common cause is a transient PyPI failure; if the next scheduled "
            "run still shows the same extra here, investigate."
        )
        lines.append("")
        for extra in errors:
            r = reports[extra]
            lines.append(f"- `[{extra}]` — `{r.get('reason', 'unknown')}`")
        lines.append("")

    clear = [e for e, r in reports.items() if r["status"] == "ok"]
    if clear:
        lines.append("## Clear")
        lines.append("")
        lines.append(", ".join(f"`[{e}]`" for e in clear))
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append(
        "This issue is managed by `.github/workflows/drift-guard.yml`. The body "
        "is fully regenerated on every run and the issue auto-closes when "
        "drift clears. Do not edit the body by hand."
    )
    return "\n".join(lines)


def _gh(*args: str, input_: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["gh", *args],
        check=True,
        capture_output=True,
        text=True,
        input=input_,
    )


def _find_open_issue(repo: str, title: str) -> int | None:
    result = _gh(
        "issue",
        "list",
        "--repo",
        repo,
        "--state",
        "open",
        "--search",
        f'in:title "{title}"',
        "--json",
        "number,title",
        "--limit",
        "20",
    )
    for issue in json.loads(result.stdout):
        if issue["title"] == title:
            return int(issue["number"])
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("reports_dir", type=Path)
    parser.add_argument("--repo", required=True, help='e.g. "haalfi/remote-store"')
    parser.add_argument("--run-url", required=True)
    parser.add_argument("--title", required=True)
    args = parser.parse_args(argv)

    reports = _load_reports(args.reports_dir)
    if not reports:
        print("No drift reports found; nothing to reconcile.", file=sys.stderr)
        return 0

    has_signal = any(r.get("status") in ("drift", "needs_refresh", "error") for r in reports.values())
    existing = _find_open_issue(args.repo, args.title)
    body = _render_body(reports, args.run_url)

    if has_signal:
        if existing is None:
            print(f"Creating new issue: {args.title}", file=sys.stderr)
            _gh(
                "issue",
                "create",
                "--repo",
                args.repo,
                "--title",
                args.title,
                "--body-file",
                "-",
                input_=body,
            )
        else:
            print(f"Updating issue #{existing}", file=sys.stderr)
            _gh(
                "issue",
                "edit",
                str(existing),
                "--repo",
                args.repo,
                "--body-file",
                "-",
                input_=body,
            )
        return 0

    # All clear.
    if existing is None:
        print("All extras clear; no open issue. No-op.", file=sys.stderr)
        return 0
    print(f"All clear — closing issue #{existing}", file=sys.stderr)
    _gh(
        "issue",
        "comment",
        str(existing),
        "--repo",
        args.repo,
        "--body",
        f"Drift cleared on this run.\n\n{args.run_url}",
    )
    _gh("issue", "close", str(existing), "--repo", args.repo)
    return 0


if __name__ == "__main__":
    sys.exit(main())
