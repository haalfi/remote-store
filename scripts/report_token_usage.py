"""Where Claude Code sessions on this repo spend their tokens.

Two sections, from two sources:

1. **Transcripts** (local): reads Claude Code session transcripts
   (``*.jsonl``) and prints, per transcript, the API usage totals and a
   price-weighted split, then the tool results that cost most across all of
   them. A directory is scanned recursively, so subagent transcripts count
   as their own rows. Skipped with a note when the default directory is
   absent.
2. **Trace reads** (in the repo): ranks the files that ``sdd/traces/*.yml``
   steps read, by the number of traces reading each, its gate steps, its
   size on disk (bytes / 4) and their product, the token **exposure** of
   reading it whole in every trace that read it.

Two figures per transcript need a definition:

* **Prefix**: input + cache-write + cache-read tokens of the first API call,
  i.e. what the session paid before its first tool result: system prompt,
  tool definitions, ``CLAUDE.md``, skill and agent listings.
* **Units**: tokens weighted by relative price, input 1, 5-minute cache
  write 1.25, 1-hour cache write 2, cache read 0.1, output 5. These are the
  ratios Anthropic's pricing page lists for every current model; absolute
  prices are left out because they differ per model and change.

A tool result's **carried** cost is its size (characters / 4) times the API
calls left in its transcript, since every later call re-reads it from cache.
It ranks reads by what they cost the session, not by their size alone.

Run with::

    hatch run report-token-usage                  # this repo's transcripts
    hatch run report-token-usage -- [<path>] [--top N] [--traces-dir DIR] [--repo-root DIR]

The default path is the directory where Claude Code stores this repo's
transcripts in the user's home; ``default_dir`` derives it. Trace step
paths are sized against ``--repo-root``, not derived from ``--traces-dir``.

Exit codes: ``0`` whatever is found; ``2`` for a usage error (an explicit
transcript path, ``--traces-dir`` or ``--repo-root`` that does not exist,
or a negative ``--top``).

Why this is a report, not a gate
================================
The exit code never depends on what is found.
[`sdd/DRIFT-RULES.md` Rule 5](../sdd/DRIFT-RULES.md#mandatory-path) requires
an advisory check to say why it does not gate:

* **Its main input is not in the repo.** Transcripts live on each
  contributor's machine; CI has none, so a gate would have nothing to read.
  The trace section is in the repo but has no defect to flag: a file read
  by every trace may be read because it should be.
* **Token cost is a trade-off, not a defect.** A long session that reads
  the ripple-check can be the right session. The figures inform where to
  restructure; a person decides whether to.

What this report does NOT catch
===============================
State the bound, per [Rule 7](../sdd/DRIFT-RULES.md#miss-rate):

* **Tool-result sizes are estimates.** Characters / 4 approximates tokens;
  the API reports usage per call, not per content block, so exact
  attribution is impossible from a transcript.
* **Carried cost ignores compaction.** After ``/compact`` a result is no
  longer re-read, but the transcript still counts it to the last call, so
  carried cost is an upper bound for compacted sessions.
* **The transcript format is Claude Code's, not ours.** Records without
  ``message.usage`` or ``tool_use``/``tool_result`` blocks are skipped; a
  format change shows as zero calls, never as an error. Lines that are not
  JSON are counted and reported.
* **Exposure is an upper bound, not a measurement.** A trace step names a
  ``section``, and most steps read one section, not the whole file; size is
  today's, not the size at the time of the read. Exposure ranks where a
  section index would pay most; the transcript section measures what was
  paid. Steps naming a directory or a missing file get size 0.
* **Traces record what authors wrote down.** A read nobody traced, and
  reads by sessions that wrote no trace, are absent.

Drift-gate::

    kind:       report
    surfaces:   token usage, price-weighted cost split and costliest tool results per
        Claude Code session transcript; files read across sdd/traces with size and exposure
    domain:     process
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent))

from _trace_corpus import ROOT as _REPO  # noqa: E402
from _trace_corpus import TRACES_DIR as _TRACES  # noqa: E402
from _trace_corpus import iter_trace_files, load_trace  # noqa: E402

# Relative price per token class; see module docstring.
_WEIGHTS = {"input": 1.0, "write_5m": 1.25, "write_1h": 2.0, "read": 0.1, "output": 5.0}
# First matching input key names a tool call's target.
_TARGET_KEYS = ("file_path", "command", "pattern", "skill", "subagent_type", "url", "query")


@dataclass
class Session:
    name: str
    calls: int = 0
    prefix: int = 0
    tokens: Counter[str] = field(default_factory=Counter)
    # target -> (estimated tokens, carried tokens)
    results: dict[str, list[int]] = field(default_factory=dict)
    bad_lines: int = 0

    @property
    def units(self) -> float:
        return sum(_WEIGHTS[k] * n for k, n in self.tokens.items())


def default_dir(repo: Path = _REPO) -> Path:
    return Path.home() / ".claude" / "projects" / re.sub(r"[^A-Za-z0-9]", "-", str(repo))


def _target(name: str, inp: object) -> str:
    if isinstance(inp, dict):
        for key in _TARGET_KEYS:
            if key in inp:
                return f"{name} {' '.join(str(inp[key]).split())[:80]}"
    return name


def _chars(content: object) -> int:
    if isinstance(content, str):
        return len(content)
    if isinstance(content, list):
        return sum(_chars(c.get("text", c.get("content", ""))) for c in content if isinstance(c, dict))
    return 0


def _add_usage(tokens: Counter[str], usage: dict) -> None:
    tokens["input"] += usage.get("input_tokens", 0)
    tokens["read"] += usage.get("cache_read_input_tokens", 0)
    tokens["output"] += usage.get("output_tokens", 0)
    split = usage.get("cache_creation")
    if isinstance(split, dict):
        tokens["write_5m"] += split.get("ephemeral_5m_input_tokens", 0)
        tokens["write_1h"] += split.get("ephemeral_1h_input_tokens", 0)
    else:  # Older transcripts carry only the total; assume the 5-minute default.
        tokens["write_5m"] += usage.get("cache_creation_input_tokens", 0)


def parse(lines: list[str], name: str) -> Session:
    s = Session(name)
    seen: set[str] = set()
    targets: dict[str, str] = {}
    # (target, estimated tokens, call index at which it entered the context)
    pending: list[tuple[str, int, int]] = []
    for line in lines:
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            s.bad_lines += 1
            continue
        msg = rec.get("message") if isinstance(rec, dict) else None
        if not isinstance(msg, dict):
            continue
        usage = msg.get("usage")
        # One API response is split over several records sharing its id.
        if isinstance(usage, dict) and msg.get("id") not in seen:
            seen.add(msg.get("id"))
            if s.calls == 0:
                s.prefix = sum(
                    usage.get(k, 0) for k in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")
                )
            s.calls += 1
            _add_usage(s.tokens, usage)
        content = msg.get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "tool_use":
                targets[block.get("id", "")] = _target(block.get("name", "?"), block.get("input"))
            elif block.get("type") == "tool_result":
                target = targets.get(block.get("tool_use_id", ""), "?")
                pending.append((target, _chars(block.get("content")) // 4, s.calls))
    for target, est, at in pending:
        row = s.results.setdefault(target, [0, 0])
        row[0] += est
        row[1] += est * (s.calls - at)
    return s


def load(root: Path) -> list[Session]:
    files = sorted(root.rglob("*.jsonl")) if root.is_dir() else [root]
    base = root if root.is_dir() else root.parent
    return [
        parse(f.read_text(encoding="utf-8", errors="replace").splitlines(), str(f.relative_to(base))) for f in files
    ]


@dataclass
class FileReads:
    path: str
    traces: set[str] = field(default_factory=set)
    steps: int = 0
    gates: int = 0
    size: int = 0  # bytes / 4, 0 when not a file

    @property
    def exposure(self) -> int:
        return len(self.traces) * self.size


def trace_reads(traces: Path, repo: Path) -> tuple[list[FileReads], int, int]:
    """Aggregate trace steps per file; returns (rows, traces read, traces unparseable)."""
    rows: dict[str, FileReads] = {}
    read = bad = 0
    for trace in iter_trace_files(traces):
        try:
            # The shared loader rejects duplicate keys instead of keeping the last.
            data = load_trace(trace.read_text(encoding="utf-8"))
        except (yaml.YAMLError, OSError, UnicodeDecodeError):
            bad += 1
            continue
        read += 1
        phases = data.get("phases") if isinstance(data, dict) else None
        for phase in phases or []:
            for step in (phase or {}).get("steps") or []:
                if not isinstance(step, dict) or not step.get("file"):
                    continue
                # A step may name an anchor (`path#id`); the file is the unit.
                path = str(step["file"]).split("#")[0].strip()
                row = rows.setdefault(path, FileReads(path))
                row.traces.add(trace.name)
                row.steps += 1
                row.gates += step.get("read_type") == "gate"
    for row in rows.values():
        f = repo / row.path
        row.size = f.stat().st_size // 4 if f.is_file() else 0
    return list(rows.values()), read, bad


def _print_trace_reads(traces: Path, repo: Path, top: int) -> None:
    rows, read, bad = trace_reads(traces, repo)
    print(f"\nTop {top} files read across {read} trace(s) in {traces}, by exposure (traces x size):\n")
    print("| Exposure | Traces | % of traces | Steps | Gate steps | Size | File |")
    print("| ---: | ---: | ---: | ---: | ---: | ---: | --- |")
    for r in sorted(rows, key=lambda r: (r.exposure, len(r.traces)), reverse=True)[:top]:
        size = f"{r.size:,}" if r.size else "—"
        print(
            f"| {r.exposure:,} | {len(r.traces)} | {100 * len(r.traces) / (read or 1):.0f}"
            f" | {r.steps} | {r.gates} | {size} | `{r.path}` |"
        )
    if bad:
        print(f"\n{bad} trace(s) were not valid YAML and were skipped.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "transcripts",
        nargs="?",
        type=Path,
        default=None,
        help="Transcript file or directory (default: this repo's Claude Code transcripts; skipped if absent).",
    )
    parser.add_argument("--top", type=int, default=15, help="Rows per ranking table (default: 15).")
    parser.add_argument(
        "--traces-dir", type=Path, default=_TRACES, help="Directory of trace YAML files (default: sdd/traces)."
    )
    parser.add_argument(
        "--repo-root", type=Path, default=_REPO, help="Root trace step paths are sized against (default: the repo)."
    )
    args = parser.parse_args(argv)

    if args.transcripts is not None and not args.transcripts.exists():
        parser.error(f"no transcripts at {args.transcripts}")
    if not args.traces_dir.is_dir():
        parser.error(f"--traces-dir does not exist: {args.traces_dir}")
    # --repo-root sizes every step: pointed somewhere wrong, every size and
    # exposure reads 0 and the table still looks real. Loud, not plausible.
    if not args.repo_root.is_dir():
        parser.error(f"--repo-root does not exist: {args.repo_root}")
    # A negative --top makes [:top] drop the lowest rows and look complete.
    if args.top < 0:
        parser.error(f"--top must be >= 0, got {args.top}")

    root = args.transcripts or default_dir()
    if root.exists():
        _print_transcripts(root, args.top)
    else:
        print(f"No transcripts at {root}; transcript section skipped.")
    _print_trace_reads(args.traces_dir, args.repo_root, args.top)
    return 0


def _print_transcripts(root: Path, top: int) -> None:
    sessions = load(root)
    print(f"Token usage in {len(sessions)} transcript(s) under {root}.")
    print("Units weight input 1, cache write 1.25 (5m) / 2 (1h), cache read 0.1, output 5.\n")
    print("| Transcript | Calls | Prefix | Cache read | Cache write | Output | Units | Read % | Write % | Output % |")
    print("| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |")
    for s in sorted(sessions, key=lambda x: x.units, reverse=True):
        t, u = s.tokens, s.units or 1.0
        write = t["write_5m"] + t["write_1h"]
        write_u = _WEIGHTS["write_5m"] * t["write_5m"] + _WEIGHTS["write_1h"] * t["write_1h"]
        print(
            f"| {s.name} | {s.calls} | {s.prefix:,} | {t['read']:,} | {write:,} | {t['output']:,}"
            f" | {s.units:,.0f} | {100 * _WEIGHTS['read'] * t['read'] / u:.0f}"
            f" | {100 * write_u / u:.0f} | {100 * _WEIGHTS['output'] * t['output'] / u:.0f} |"
        )
    total: dict[str, list[int]] = {}
    for s in sessions:
        for target, (est, carried) in s.results.items():
            row = total.setdefault(target, [0, 0])
            row[0] += est
            row[1] += carried
    print(f"\nTop {top} tool results by carried tokens (size x later calls), all transcripts:\n")
    print("| Carried | Size | Tool target |")
    print("| ---: | ---: | --- |")
    for target, (est, carried) in sorted(total.items(), key=lambda kv: kv[1][1], reverse=True)[:top]:
        print(f"| {carried:,} | {est:,} | `{target.replace('|', '/')}` |")
    bad = sum(s.bad_lines for s in sessions)
    if bad:
        print(f"\n{bad} line(s) were not JSON and were skipped.")


if __name__ == "__main__":
    sys.exit(main())
