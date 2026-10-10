"""How long each `/ship` run took: wall time, the part spent working, and the part spent waiting.

A run is one or more main transcripts (a build session and the session that
resumed it), each read with its subagents. Time between two consecutive
timestamped records counts as **active** when it is at most ``--idle-min``
minutes, and as **idle** otherwise: an answer the maintainer had not yet given,
a background wait, or the gap between a handoff and its resume.

    python run_durations.py --run A=<main.jsonl> --run B=<build.jsonl>,<resume.jsonl> \
        --milestone A:pr_open=ISO --milestone B:pr_open=ISO

Writes ``results/run_durations.json``: per run, start, end, wall, active and
idle minutes, the longest idle gaps, and minutes from start to each milestone.
Bounds: the threshold decides what counts as waiting, so a long tool call (a
gate run under ten minutes) is active and a dialog answered within the
threshold is too; subagents running in parallel with the main session add no
time.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import _common as c


def ts(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def stamps(main: Path) -> list[datetime]:
    files = [main, *sorted((main.parent / main.stem / "subagents").glob("*.jsonl"))]
    out = []
    for f in files:
        for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                t = json.loads(line).get("timestamp")
            except json.JSONDecodeError:
                continue
            if t:
                out.append(ts(t))
    return sorted(out)


def main(argv=None) -> int:
    ap = c.parser(__doc__, data=False)
    ap.add_argument("--run", action="append", required=True, help="LABEL=main.jsonl[,main.jsonl...]")
    ap.add_argument("--milestone", action="append", default=[], help="LABEL:name=ISO")
    ap.add_argument("--idle-min", type=float, default=5.0, help="gap above which time counts as idle")
    args = c.resolve(ap.parse_args(argv))
    runs = {}
    inputs: dict[str, Path | str] = {}
    for spec in args.run:
        label, paths = spec.split("=", 1)
        mains = [Path(p) for p in paths.split(",")]
        for i, p in enumerate(mains):
            inputs[f"{label} transcript {i}"] = p
        t = sorted(x for p in mains for x in stamps(p))
        gaps = [(b - a).total_seconds() / 60 for a, b in zip(t, t[1:], strict=False)]
        idle = [g for g in gaps if g > args.idle_min]
        runs[label] = {
            "start": t[0].isoformat(),
            "end": t[-1].isoformat(),
            "wall_min": round((t[-1] - t[0]).total_seconds() / 60),
            "active_min": round(sum(g for g in gaps if g <= args.idle_min)),
            "idle_min": round(sum(idle)),
            "longest_idle_min": sorted((round(g) for g in idle), reverse=True)[:5],
            "milestones_min": {},
        }
    for spec in args.milestone:
        label, rest = spec.split(":", 1)
        name, iso = rest.split("=", 1)
        r = runs[label]
        r["milestones_min"][name] = round((ts(iso) - ts(r["start"])).total_seconds() / 60)
    payload = {"idle_threshold_min": args.idle_min, "runs": runs}
    c.write_result(args.results, "run_durations", "run_durations", inputs, payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
