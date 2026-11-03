# BK-511 OP-01 behaviours classified

<!-- doc: repo-only -->

The evidence behind [`report.md`](report.md): OP-01's decisions split into
behaviour clauses and classified along fixed facets, piloted on the stream
lifecycle. Derived from the record, so RFC-0029 R4 keeps it from BK-506's
oracle sessions. The record governs; a clause is a reading of it.

| Path | Role |
|---|---|
| `effective.py` | Per decision: axis, Amends targets, amenders direct and transitive, keyword signals; writes JSON |
| `pilot.toml` | The pilot: 37 behaviour clauses and 4 record-text-only decisions |
| `whole/SCHEMA.md` | The clause schema and facet vocabularies, as decided after the pilot |
| `whole/a.toml` to `d.toml` | The rest of the record by axis group: A AX-1 to AX-4, B AX-5 and AX-13, C AX-7 to AX-9 and AX-15, D the rest (clause ids X..) |
| `check.py` | Vocabulary, coverage (pilot set with `--pilot`, else all decisions), mapping of the spike's freeze-1 rules; prints the views |

No file here is collected, built or run by any gate.

## Running

From the repo root:

```
hatch run python sdd/research/bk-511-op01-behaviour-classification/effective.py sdd/observe/records/OP-01.md tmp/op01-effective.json
hatch run python sdd/research/bk-511-op01-behaviour-classification/check.py sdd/observe/records/OP-01.md --pilot
```

Expected (2026-11-03, on `observe/OP-01/freeze-1`): `decisions: 156; amended:
79; amending: 95`; `pilot decisions: 45; clauses: 37; record-text only: 4`,
then the pilot's views and `Result: OK`. Without `--pilot`: `decisions in scope: 156;
clauses: 127; record-text only: 32`, the views of `report.md` § 5 and `Result: OK`.
`check.py` reads `../bk-485-op01-stream-spike/freeze-1/stream_rules.toml`.
