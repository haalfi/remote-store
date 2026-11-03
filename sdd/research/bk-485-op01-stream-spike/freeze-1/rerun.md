# The stream spike rerun against OP-01's freeze-1

<!-- doc: repo-only -->

**Date:** 2026-11-03
**Backlog items:** BK-485
**Status:** Addendum to [`../report.md`](../report.md), whose folder stays as
it landed. A point-in-time snapshot of the record tagged
`observe/OP-01/freeze-1` (`a7de4e31`).

---

## 1. What changed and what it shows

Of the spike's eight rule assumptions, four are decided at freeze-1 and one
in part, and the rules carried forward still check complete and judge the
model with no divergence. Against Local they add two decided divergences (`seekable()`,
`seek`) and expose a third, more serious one: a `readline()` that fails at the
OS silently drops a buffered byte and reports the end, which D51 and D93
forbid. Four of the spike's nine prose gaps stay open (F1 in part, F3, F5 in
part, F10).

## 2. The record between the spike and the freeze

The record grew from D44 to D156; 104 decisions carry an `Amends:` line. An
amendment lives in the amending decision: no original's text is rewritten, so
D18's table (record line 502) still reads as the spike saw it, and its current
meaning is D18 with D50, D51, D70, D100, D117 and D132, some of them amended
again (D132 by D148 and D155, D117 by D137 and D154). Direct amendments of the
slice, from `amends.py`:

| Decision | Amended by |
|---|---|
| D2 | D69, D70 |
| D15 | D117 |
| D16 | D51, D52, D117 |
| D18 | D50, D51, D70, D100, D117, D132 |
| D20 | D50, D81 |
| D6, D7, D17, D36 | — |

The spike's stale-filter measure rerun (`extract/stale_filter.py`): 135 of the
156 decisions carry Open items `none`; a later open item mentions 134 and is
about 40.

## 3. The spike's gaps at freeze-1

Read against the decisions named, in the frozen record.

| # | At freeze-1 |
|---|---|
| F1 `read(0)` mid-stream | Partly: D155 fixes `read1(0)` and an empty `readinto` as `b''`/0 and "not the end"; `read(0)` is still D6's min(n, r) only |
| F2 cancelled `close()` | Decided: Closed, every local resource released (D50, D94, D118) |
| F3 unclosed Exhausted or Failed stream warns? | Open: D17 unchanged |
| F4 `readinto`, `readline` | Decided (D70), with `read1`, `tell`, `readable`, `seekable`, `seek` |
| F5 `chunks(0)` | Partly: the state is decided (D51, D80, D92, D117); raised at the call or at the first `next()` is not |
| F6 "the same failure again" | Decided: a new exception of the category, the original as `__cause__` (D52, D95) |
| F7 a failed call delivers no bytes | Implied, not stated: D72 (a read "returns its full count or fails"), D93 (`tell()` is the bytes delivered) |
| F8 cancellation without a transfer | Decided: every state but Closed goes to Closed (D50) |
| F10 Exhausted is the oracle's fact | Open: D18 still defines Exhausted as "at end" |

## 4. The rules carried forward

`stream_rules.toml` here is the slice's, with every source updated to the
amending decisions and three new call kinds from D70: `read1` (RF9), `tell`
(T1), `seek` (S1, `io.UnsupportedOperation`). Of the eight `assumed` fields,
RF7, K2, Z1 and Z2 are decided and dropped; four remain, counted from the file:
RF4 (F1), RF6 (F10), G2 (F3), and RF1 for F5's open half. `check_rules`, now
over 10 call kinds: OK. The model, the
slice's own and unchanged, conforms: 0 rules diverged.

## 5. Local at freeze-1

`conform.py` here, three runs on these scripts, 400 examples each:

| Run | Plain Local | Faults, strict | Faults, protocol only |
|---|---|---|---|
| 1 | RF4, RF7, Z1, S1 | RF2, RF6, K1, K3, G1, Z2 | RF2, RF3, K1, K3, G1, Z2, T1 |
| 2 | RF4, RF7, Z1, S1 | RF2, RF6, K3, G1, Z2 | RF2, RF3, K1, K3, G1, Z2, T1 |
| 3 | RF4, RF7, Z1, S1 | RF2, RF6, K1, K3, G1, Z2 | RF2, RF3, K1, K3, G1, Z2 |

More call kinds share each example's 25 steps, so a rule is reached less often
than in the slice's runs; K1 and T1 show in two of three.

| # | Decision | Local today | New at freeze-1 |
|---|---|---|---|
| C1 to C5 | as in `../report.md` § 5 | unchanged; Z2 (`tell()` on a stream a cancelled read left open) is C1 again | — |
| C6 | D70 | `seekable()` is `True` | yes: Z1 rested on `O25`, now decided `False` |
| C7 | D70, D153 | `seek(0)` works and returns 0 | yes: `io.UnsupportedOperation` decided |
| C8 | D51, D93 | a `readline()` failing at the OS drops the byte it had buffered: `tell()` passes it and the next `read()` returns `b''` | yes |

C8 is reproduced without the library or the spike's wrapper by
`readline_loss.py`: on CPython's `io.BufferedReader`, `readinto(6)` of 7
bytes, then a `readline()` whose raw read raises `OSError`, leaves `tell()` at
7 and the next `read()` at `b''`. It is C2 (Failed not sticky) made silent:
the caller sees a clean end, short by one byte. D51 makes that stream Failed,
so the next read raises the failure again, and D93's `tell()` counts only
bytes delivered.

## 6. Limits

The rules are still one author's; D18's current meaning was assembled by hand
from its amendments, which no tool yet does (§ 2). `read1`'s n < -1, `readline`
with a limit, `readinto1`, `readlines`, `truncate`, `write` and the async form
are not exercised. The fault wrapper's limits are `../report.md` § 5's.
