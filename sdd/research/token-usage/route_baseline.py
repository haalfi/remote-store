"""Per-route review rounds of one ``/ship`` run, from a ``tokkit.py report`` snapshot.

A run that re-plans mid-loop has two routes: the rounds before the re-plan and
the rounds after it, which restart at round 1. ``tokkit.py`` lists the rounds
of the whole run; this script splits them at ``--route-start-call``, the first
main-session call of the new route, and writes one route's rounds and totals.

Round figures are ``tokkit.rounds_of``'s: one round per main-session call that
spawned reviewers, its main-session context at that call, the main-session
units up to the next spawn, and the units of the subagents it spawned, each
rounded by ``tokkit``. A route's units are its main-session calls from
``--route-start-call`` on plus every subagent that began at or after that call,
summed before rounding; an earlier route's subagent stays with it even when it
finishes after the boundary. ``--checkpoint`` (ISO timestamp) also
reports the units a ``tokkit.py report --until`` cut at that time leaves out,
so a route total can be reconciled with a checkpoint figure.

    python route_baseline.py --snapshot <snapshots>/<sid> --route-start-call 409 \\
        --checkpoint 2026-10-09T13:35:51Z --name run_a_route2

The snapshot holds prompts and paths and stays out of the repo; only the
aggregated figures are written to ``--results``.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import _common as c
import tokkit


def split(snapshot: Path, start: int, checkpoint: str | None) -> dict:
    main = snapshot / f"{snapshot.name}.jsonl"
    files = tokkit.transcript_files(main)
    parsed = {f: tokkit.parse_file(f) for f in files}
    mc, _, me = parsed[main]
    rounds = tokkit.rounds_of(mc, me, files, parsed)
    start_ts = mc[start]["ts"] or ""
    subs = [parsed[f][0] for f in files[1:] if parsed[f][0]]
    total = sum(x["units"] for f in files for x in parsed[f][0])
    # A subagent belongs to the route that was running when it began. Totals are summed from
    # unrounded call units; tokkit.rounds_of has already rounded its per-round figures.
    route_sub = sum(x["units"] for cs in subs if (cs[0]["ts"] or "") >= start_ts for x in cs)
    route_main = sum(x["units"] for x in mc[start:])

    # A round's spawn_call is the call after the spawning one (tokkit's event index).
    later = [r for r in rounds if r["spawn_call"] > start]
    first_spawn = later[0]["spawn_call"] if later else len(mc)
    out = {
        "run": {
            "transcripts": 1 + len(subs),
            "units_m": round(total / 1e6, 2),
            "main_calls": len(mc),
            "subagent_units_m": round(sum(x["units"] for cs in subs for x in cs) / 1e6, 2),
        },
        "route_start_call": start,
        "route_start_ts": start_ts,
        "route": {
            "units_m": round((route_main + route_sub) / 1e6, 2),
            "main_units_m": round(route_main / 1e6, 2),
            "subagent_units_m": round(route_sub / 1e6, 2),
            "before_first_round": {
                "calls": first_spawn - start,
                "units_m": round(sum(x["units"] for x in mc[start:first_spawn]) / 1e6, 2),
            },
            "loop_units_m": round((sum(x["units"] for x in mc[first_spawn:]) + route_sub) / 1e6, 2),
            "rounds": [{"round": n, **r} for n, r in enumerate(later, 1)],
        },
        "earlier_route_units_m": round((total - route_main - route_sub) / 1e6, 2),
    }
    if checkpoint:
        after = total - sum(x["units"] for f in files for x in parsed[f][0] if (x["ts"] or "") <= checkpoint)
        out["checkpoint"] = {
            "until": checkpoint,
            "units_m": round((total - after) / 1e6, 2),
            "after_units_m": round(after / 1e6, 2),
            "first_main_call_after": next((x["idx"] for x in mc if (x["ts"] or "") > checkpoint), None),
            # The route's units minus the cut's "after" units, from unrounded sums, and the two
            # parts that make it up: route calls before the cut, less earlier-route subagent
            # work after it (part of "after", not of the route).
            "route_minus_after_m": round((route_main + route_sub - after) / 1e6, 2),
            "route_main_units_before_cut_m": round(
                sum(x["units"] for x in mc[start:] if (x["ts"] or "") <= checkpoint) / 1e6, 2
            ),
            "earlier_subagent_units_after_m": round(
                sum(
                    x["units"]
                    for cs in subs
                    if (cs[0]["ts"] or "") < start_ts
                    for x in cs
                    if (x["ts"] or "") > checkpoint
                )
                / 1e6,
                2,
            ),
        }
    return out


def main(argv=None) -> int:
    ap = c.parser(__doc__, data=False)
    ap.add_argument("--snapshot", type=Path, required=True, help="tokkit snapshot folder <snapshots>/<session id>")
    ap.add_argument("--route-start-call", type=int, required=True, help="first main-session call of the route")
    ap.add_argument("--checkpoint", default=None, help="ISO timestamp of a tokkit --until cut to reconcile with")
    ap.add_argument("--name", default="route", help="result file name, without .json")
    args = c.resolve(ap.parse_args(argv))
    tokkit.ARGS = argparse.Namespace(repo_root=args.repo_root)
    snapshot = args.snapshot.resolve()
    payload = split(snapshot, args.route_start_call, args.checkpoint)
    payload["derivation"] = (
        f"route_baseline.py --snapshot <snapshots>/<sid> --route-start-call {args.route_start_call}"
        + (f" --checkpoint {args.checkpoint}" if args.checkpoint else "")
        + f" --name {args.name}"
    )
    c.write_result(
        args.results, args.name, "route_baseline", {"main transcript": snapshot / f"{snapshot.name}.jsonl"}, payload
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
