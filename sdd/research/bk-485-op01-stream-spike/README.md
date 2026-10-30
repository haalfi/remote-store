# BK-485 OP-01 stream spike: record to checks

<!-- doc: repo-only -->

The evidence behind [`report.md`](report.md): whether OP-01's prose decisions
can be carried, step by checkable step, to checks that run against a backend.
One slice, the read stream's lifecycle (D6, D7, D15 to D18, D20, D36, plus D2's
shape). A spike: no tests of its own, frozen once landed. Step 5's spec and
model (BK-485) are written at their own paths and do not extend this folder.

**Not BK-506's trial.** Everything here is derived from the record, so RFC-0029
R4's information flow keeps it out of any session that writes the trial's
oracles.

| Path | Step | Role |
|---|---|---|
| `extract/extract_decisions.py` | 1 | The record's decisions whose own Open items field is `none`, as a Heading / Scenario / Observed table; a bare `(a)` is expanded from Options |
| `extract/OP-01-closed-decisions.md` | 1 | Its output on the record at `f1595ff` |
| `extract/stale_filter.py` | 1 | Counts how many of those decisions a later open item names (report § 2) |
| `slice/stream_rows.toml` | 2 | The slice as 30 example rows |
| `slice/stream_model.py` | 3 | Reference state machine, written from the rows |
| `slice/check_stream.py` | 3 | Replays the rows, runs a Hypothesis machine against an oracle written from the decisions, reports traceability |
| `slice/mutate.py` | 3 | Four mutants of the model; each must make `check_stream.py` fail |
| `slice/stream_rules.toml` | 2b | The slice as 17 guarded rules (guard, then effect) |
| `slice/rules_engine.py` | 2b | Interprets the rules as an oracle; checks every call in a finite domain matches exactly one rule |
| `slice/conform.py` | 4 | Drives the model and Local (plain, then with faults injected below the library) through the rules |

No file here is collected, built or run by any gate: the folder is outside
`testpaths` and `hatch run lint`'s ruff paths.

## Running

From the repo root:

```
hatch run python sdd/research/bk-485-op01-stream-spike/extract/extract_decisions.py sdd/observe/records/OP-01.md tmp/op01-closed.md
hatch run python sdd/research/bk-485-op01-stream-spike/extract/stale_filter.py sdd/observe/records/OP-01.md
hatch run python sdd/research/bk-485-op01-stream-spike/slice/check_stream.py
hatch run python sdd/research/bk-485-op01-stream-spike/slice/mutate.py
hatch run python sdd/research/bk-485-op01-stream-spike/slice/conform.py
```

Expected (2026-10-30, each under a minute): `24 rows`; `24` closed, `23`
mentioned, `10` reopened, noted or gapped; `Result: OK (0 failure(s))`; four
`killed`; static check `OK`, then `0`, `3`, `5`, `5` rules diverged for the
model, Local, and Local with faults (strict, protocol only). Hypothesis draws
fresh examples each run, so traces and hit counts differ; the diverging rules
did not across three runs.

`conform.py` writes its Local stores under `tmp/op01-stream-spike/`
(gitignored) and, for the fault runs only, shadows `open` in
`remote_store.backends._local` while `LocalBackend.read` runs.
