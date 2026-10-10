# Research: Where Claude Code sessions on this repo spend their tokens
<!-- doc: repo-only -->

**Date:** 2026-10-09
**Backlog items:** BK-418
**Status:** Point-in-time snapshot per [`sdd/000-process.md` § Document types](../../000-process.md#document-types). It ports, re-runs and corrects an analysis done in a scratch session on 2026-10-09. Every figure names the result file it comes from, as `[file: key]` under `results/`. § Reproducing says which script and inputs produced each file. BK-418 tracks the interventions it motivates.

## Question

Where do the tokens of a `/ship` delivery, and of sessions on this repo in
general, go? Which of those costs could a change to how sessions work
actually move?

## Answer

**Almost all spend is the model re-reading its own context on every call, so
a session costs roughly its number of calls times its context size, and the
review loop after the PR opens is where both are largest.** Cache reads are
98.7% of tokens and 79.0% of price-weighted units [inventory:
`tokens_pct`, `units_pct`].

- **The cost is after the PR opens.** In run A (`/ship BUG-280`), 94.1% of
  units went to the main session after the PR opened plus all subagents (the one
  subagent spawned before the PR-link record is 0.5%) [run_a_final: `phases`,
  `rounds`]. In BK-397's `/ship` run, 82% came after the PR opened [work_items:
  `after_pr_open`].
- **The review loop runs on the implementation's context.** Every round pays
  again for the context the build left behind. Starting the post-PR work from a
  fresh context would have saved an estimated 23 to 28% of BK-397's `/ship`
  session group, and 28 to 31% of the v0.33.0 release's [work_items:
  `fresh_context_ceiling`].
- **The long tail of a review loop is prose, and most of it the loop made
  itself.** From round 4 on, 49 to 78% of findings were caused by an earlier
  fix in the same loop [rounds: `origin_by_round`]. Of 321 prose findings in the
  13 longest loops, 94% are checkable by a command or by listing the cases
  [prose_classes: `checkable_counts`].
- **Run A's context named most related items early.** BUG-280 shares spec
  BE-021 with seven open items. The IDs BK-389 and RFC-0017 first appeared in
  context at call 2, before the first edit at call 9, and five of the seven items
  by call 14. BK-394 and ADR-0042 first appeared at calls 414 and 415
  [run_a_orient_check: `first_mention_call`; run_a_final: `first_edit_call`].
  When an ID first appears is all this measures, not whether the plan used it.
- **The always-loaded instruction files are second order.** The backlog files,
  linked docs and `CLAUDE.md` text each account for about 2 to 3% of re-read
  context [backlog_links: `groups`; composition: `instruction_files`].

## What this does not establish

**Two working days, one dominant session, and one run per arm: the figures
describe what happened, they do not estimate a rate.**

- **Two transcript days.** The window (2026-08-14 to 2026-10-09) holds
  transcripts from 2026-09-05 and 2026-10-04 only [inventory: `window_days`].
  Cloud sessions and the analysis session are excluded. Claude Code deleted the
  2026-09-05 transcripts during the analysis (its 30-day cleanup). The extract
  taken before that is the only copy, and it is not committed (§ Reproducing).
  BUG-264's session alone is 43% of the window's units [inventory:
  `top_session_groups`].
- **Small n per comparison.** The PR model is fitted on 6 PRs, the trace
  comparison has 8 work items, and run A is one run. The prose classification
  covers 13 PRs chosen as the longest loops, so it describes the expensive tail,
  not a typical PR.
- **Pruning.** A compaction resets carried context, and this record counts an
  item only until its segment ends. For the six work items with a trace, the
  files the trace names hold 30 to 65% of the Read tokens their sessions spent
  [work_items: `read_tokens_not_in_trace_pct`, 35 to 70 not in the trace]. Trace sizes are
  taken at each trace's creation commit and bound the read from above.
- **LLM-assisted classification.** The prose labels were assigned once, by a
  model, against a fixed rubric (`prose_classes.py`). The analysis session
  judged 9 of the 10 fixed-seed sample labels clearly right [prose_classes:
  `spot_check_keys`]. That check was not repeated independently.
- **Prices are fitted, not listed.** Dollars use per-model prices fitted to
  Claude Code's cost records, with mean errors of 15.0% (Opus 5.5) and 1.8%
  (Opus 5, n = 4) [calibration: `price_fit`].

## 1. Calibration

**Tool results and attachments run at about 2.4 characters per token, not
the 4 that `scripts/report_token_usage.py` assumes. Hidden thinking stays in
context almost token for token.** A no-intercept least-squares fit of context
growth between consecutive calls on what entered between them explains R² 0.911
over 3,667 pairs [calibration: `pairs`, `r2`].

| Entering content | Characters per token |
| --- | ---: |
| Tool results | 2.37 |
| Attachments and user text | 2.43 |
| Visible assistant output | 3.14 |

Hidden thinking enters the next call's context at 0.947 tokens per output token
[calibration: `context_per_hidden_output_token`]. These coefficients are
`_common.COEF`, used by every other script. Dollars per unit are fitted the
same way from the cost records [calibration: `price_fit`].

## 2. Cost structure

**Cost grows faster than session length, because each call re-reads a
context that has grown.** Context per call has a median of 164k tokens, a 90th
percentile of 607k and a maximum of 879k [inventory: `context_per_call`].
Calls at 400k or more are 22.8% of calls and 47.4% of units [inventory:
`context_bands`].

- **Scaling.** Across 13 main sessions, units grow with calls to the power
  1.19. For 42 subagents the exponent is 0.91 [inventory: `scaling`]. In the
  four longest main sessions, half the units are spent after 59 to 67% of the
  calls [inventory: `longest_main_transcripts`].
- **Concentration.** Four session groups took 84% of units: BUG-264 43%,
  BK-397's `/ship` session 18%, BK-403 14% and the v0.33.0 release 9%
  [inventory: `top_session_groups`].
- **Totals.** 958 M tokens and about $430: Opus 5 $283, Opus 5.5 $147
  [inventory: `tokens_total`, `usd_estimate`]. Subagents are 24.7% of units
  [inventory: `subagent_units_pct`].
- **Cache.** Main sessions write the cache only at the 1-hour TTL, which is
  8.9% of units. Subagents write at 5 minutes [inventory: `units_pct`,
  `cache`]. There were 5 rebuilds, 4 of them after a gap of over an hour,
  costing 2.1% of units [inventory: `cache`].

## 3. What the re-read context is made of

**The session prefix and tool results dominate. What the repo controls
directly, its instruction files, is a few percent.** Summed over all calls,
957 M tokens of context were re-read [composition: `sum_context_tokens`].

| Component | Share |
| --- | ---: |
| Session prefix (system prompt, tools, instructions, listings) | 22.3% |
| Read results | 21.6% |
| Bash results | 13.2% |
| Hidden thinking | 11.8% |
| Tool inputs the model wrote | 10.1% |
| Harness attachments added mid-session | 4.9% |
| Grep results | 4.7% |
| Unexplained | 4.4% |

From [composition: `shares_pct`]; smaller rows are in the file.

- **The prefix.** A main session's first call carries 55.9k tokens on mean,
  11.8k of them instructions and 2.6k the skill listing. A subagent carries
  52.9k, 4.9k of it instructions [composition: `prefix`]. Every subagent pays
  its prefix before doing any work.
- **Instruction files.** `CLAUDE.md` is about 6.2k tokens. In every call it
  would be 2.5% of units. MEMORY.md before its trim (5.6k tokens, main sessions
  only) was 1.19% [composition: `instruction_files`].
- **Costliest single items.** Reads of files under Claude Code's transcript
  folder (spilled tool outputs and subagent transcripts read back) are 2.67%. Python Bash
  results are 1.80%, the skill listing 1.57%, `sdd/BACKLOG.md` 1.41% and
  `.claude/skills/rvw-pr/SKILL.md` 1.36% [composition: `top_items_pct`]. The
  rvw-pr skill file was read by 24 subagents [composition:
  `files_read_by_most_subagents`].
- **Re-reads.** 24% of Read tokens are re-reads of a file already read in the
  same transcript [composition: `read_tokens_reread_pct`].
- **Output.** Output is 5.6% of units. Half of it is thinking the user never
  sees [composition: `output`].
- **The backlog and links hypotheses.** Backlog files are 2.22% of re-read
  context, files linked from `CLAUDE.md` 2.26%, and second-hop links 3.09%, an
  upper bound since link sets are today's [backlog_links: `groups`].
  `BACKLOG-DONE.md` was never read whole in the surviving transcripts: 19
  sliced Reads and 18 content Greps [backlog_links:
  `backlog_touches_in_surviving_transcripts`].

## 4. Five months of traces and PRs

**Commits per PR, review threads per PR and review rounds per trace step up
when `/ship` and ADR-0033 landed on 2026-08-05. PR throughput had already
fallen in July.** Traces and PRs carry no token counts, so cost here is
projected from commits per PR, fitted on six PRs with measured units. All six
are from September and October, so every earlier month is an extrapolation.

| Month | PRs merged | Commits (median) | Review threads (mean) | Est. units per PR |
| --- | ---: | ---: | ---: | ---: |
| 2026-05 | 141 | 3 | 6.1 | 12.5 M |
| 2026-06 | 157 | 3 | 3.2 | 4.6 M |
| 2026-07 | 63 | 3 | 6.2 | 7.6 M |
| 2026-08 | 44 | 7.5 | 21.6 | 27.5 M |
| 2026-09 | 56 | 5.5 | 14.8 | 19.8 M |
| 2026-10 | 40 | 7.5 | 12.2 | 27.2 M |

From [pr_model: `monthly`]. Commit count predicts a PR's units best: log-log r
0.83, with a leave-one-out error factor of 2.3. The other features score 3.0 to
3.7 [pr_model: `features`, `calibration_prs`]. The estimated units depend on
the baseline month: August's 27.5 M per PR is 6.0 times June's and 2.2 times
May's. Read them as orders of magnitude. The observable step is commits (median
3 to 7.5) and review threads (mean 6.2 in July to 21.6 in August).

- **Review rounds per trace** went from a median of 2 (June, July) to 6
  (August, September) [trace_corpus: `monthly`].
- **The material every session reads grew two to four times.**
  `sdd/CLAUDE-REFERENCE.md` went from 18.2 KB (2026-05-15) to 61.7 KB
  (2026-10-09), `CONTRIBUTING.md` from 18.6 to 45.8 KB, and `CLAUDE.md` from 7.1
  to 14.7 KB [surface: `dates`]. Process files went from 38% of the bytes a
  trace reads in May to 61 to 66% in August and September [trace_corpus:
  `monthly`].
- **Concentration.** The top 10% of PRs by commits carry 48% of estimated units
  [pr_model: `top_10pct_share_of_est_units_pct`].
- **Bug share does not start at `/ship`.** By month, the bug share of entries
  leaving the backlog was 12% in June, 32% in July, 21% in August and 46% in
  September. April was already 37% [ship_era: `backlog_exits_by_month`]. The
  series is too noisy to date an onset. It does not support `/ship` as the
  cause. Recorded for BK-366 in its dossier.

## 5. Review-loop anatomy

**Code and test findings usually stop with the last code fix: on the median
PR no round with findings follows it. The long tail is prose whose checkable claims nothing checks except the next
round, and each round's fixes falsify neighbouring claims.** The 41 traces
with a derived `review:` block give each round's findings by origin [rounds:
`origin_by_round`]:

| Round | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9+ |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Findings | 124 | 79 | 116 | 96 | 55 | 30 | 38 | 27 | 85 |
| Loop-introduced | 0% | 28% | 23% | 49% | 67% | 60% | 53% | 78% | 71% |

- **Prose leads from round 1.** Of 650 top-level review comments on 41 PRs,
  399 are on prose files, 59 on traces and 186 on code or tests [rounds:
  `comments`]. Prose and traces are 68% of round 1 and 84% from round 9 on
  [rounds: `prose_and_trace_share_by_round_pct`].
- **Pure code converges fast.**
  Of the 24 PRs with a code or test finding, the median has no round with
  findings after the last one, and 4 have two or more [rounds:
  `rounds_after_last_code_finding`]. The other 17 PRs drew prose and trace
  findings only, including loops of 13, 12, 11 and 10 rounds [rounds:
  `prs_without_code_finding`].

**The prose findings are checkable, not vague.** All 321 prose findings in the
13 longest loops were classified against a fixed rubric
([`prose_classes.py`](prose_classes.py) defines it) [prose_classes:
`class_counts`, `checkable_counts`]:

| Class | Findings | | Checkable by | Findings |
| --- | ---: | --- | --- | ---: |
| SCOPE | 91 | | listing the cases | 171 |
| FACT | 89 | | a command, grep, count or link check | 130 |
| MIRROR | 82 | | judgment | 20 |
| RULE | 34 | | | |
| DESIGN | 19 | | | |
| CLARITY | 6 | | | |

- **SCOPE peaks mid-loop.** Across the round bands 1–2, 3–4, 5–8 and 9+ (53, 98,
  97 and 73 findings), SCOPE is 23, 26, 36 and 26% of prose findings and FACT 38,
  29, 23 and 26% [prose_classes: `class_by_round_band_pct`].
- **Edits invalidate neighbouring claims.** Findings that say an earlier fix of
  the same PR caused them rise from 4% (rounds 1 to 2) to 19 to 21% (rounds 3
  and later). This counts only explicit statements, so it undercounts
  [prose_classes: `loop_ref_by_round_band_pct`].
- **Design documents carry most of it.** Backlog dossiers and items have 127
  findings and RFCs 74 [prose_classes: `findings_by_target_kind`].

## 6. Skills listed but never used

**Skills synced from claude.ai were listed in every session and every
subagent without ever being used, so turning them off removes part of a
listing this record measures at about 2.6k tokens per main session.**
Claude Code's `/plugins` Stats view, read on 2026-10-09, showed 13 synced
skills, about 3,160 tokens listed and zero uses, and about 380 tokens for this
repo's listed skills. No script here produces those three figures. They exceed
the whole listing this record measures in the first-call prefix: 2,558 tokens
per main session and 2,423 per subagent, at the § 1 calibration [composition:
`prefix`]. The two are on different scales, and this record does not reconcile
them.

- The skill listing re-enters mid-session too: 23 times in the window, 1.57% of
  re-read context [composition: `attachments_after_start`].
- In BK-397's `/ship` run it was the largest single re-read item, at 4.12%
  [bk397_ship_run: `top_items_pct`].
- The Stats view attributes tokens only while a skill's own turn is active.
  63.4% of all units carry no skill attribution [inventory:
  `skill_attribution_units_pct`].

## 7. Run A: `/ship BUG-280` at the round-7 checkpoint

**A pure-baseline `/ship` run on an S-sized bug spent 31.5 M units by its
seventh review round, nine tenths of it in the review loop and its subagents, hardening a fix
that related open work would reshape.** The maintainer paused it there
[run_a_round7]. The cut is the
round-7 checkpoint's last call (`tokkit.py report --until
2026-10-09T13:35:51Z`). It reproduces the checkpoint's 1,012 calls and $72.77.

| Phase | Calls | Share of units | Mean context |
| --- | ---: | ---: | ---: |
| Orient and plan (before the first edit) | 9 | 0.7% | 89k |
| Build (first edit to PR open) | 120 | 10.3% | 212k |
| Review loop (main session) | 284 | 58.3% | 567k |
| Review subagents | 599 | 30.6% | — |

From [run_a_round7: `phases`]. The main session's context entering each round
grew from 255k (round 1) to 828k (round 7) [run_a_round7: `rounds`]. That key
has eight spawns for seven rounds: round 6 spawned twice (calls 335 and 348).
Round 1's spawn at call 103 comes before the PR-link record at call 129
[run_a_round7: `rounds`, `pr_open_call`].

- **The late context.** BUG-280 lists one spec, BE-021, and seven open items
  shared it at the run's base commit. Two were the backend redesign, BK-389 and
  BK-394 [run_a_orient_check: `related`]. The IDs BK-389 and RFC-0017 first
  appeared in context at call 2, and five of the seven items by call 14. BK-394
  and ADR-0042 first appeared at calls 414 and 415 [run_a_orient_check:
  `first_mention_call`]. A first appearance can be a single line in a listing,
  so this says when an ID was in front of the session, not whether the plan
  weighed it. The other five shared items are sibling bugs and a gate item.
- **Environment cost.** Of 19 local gate runs, 3 were cut off at the tool's 600 s
  limit, and one background wait left the session idle for 37 minutes
  [run_a_gates]. The maintainer attributes these to full test suites from other
  sessions running at the same time.

## 8. Changes made so far

**Two always-loaded items were cut on 2026-10-09. Both remove tokens from
every call, so neither needs a change in how sessions work.**

| Change | Per call | Scope |
| --- | ---: | --- |
| Synced claude.ai skills off (`syncClaudeAiSkills: false` in local settings) | part of a listing measured at about 2.6k tokens (§ 6) | Main sessions and every subagent, this repo |
| MEMORY.md trimmed from 13,620 to 4,043 bytes | about −3.9k tokens | Main sessions only |

The skills figures and why they differ are in § 6. The MEMORY.md sizes are the file's
bytes before and after the trim, divided by 2.43 characters per token (§ 1). Its
measured cost before the trim was 1.19% of units [composition:
`instruction_files`]. Both changes apply to sessions started afterwards. The
skills setting took effect during run A.

## 9. Hypotheses

**Each row names its evidence, the largest share of spend it could move, and
the measurement that would confirm or refute it.** Ceilings are shares this
sample attributes to the factor. They overlap, do not add up, and bound what
acting could move rather than predicting a saving.

| # | Hypothesis | Evidence | Ceiling | How to test |
| --- | --- | --- | --- | --- |
| 1 | The review loop is expensive mainly because it runs on the implementation's context | 82% (BK-397) of units after PR open; 94.1% (run A) in the post-PR main session plus all subagents; fresh-context estimate 23–28% net on BK-397, the one `/ship` run [work_items: `after_pr_open`] computes it for (28–31% on the release) | 23–28% of a `/ship` session group | Units per round with and without a fresh context at PR open |
| 2 | The part of the prefix this repo controls is the instruction files | Prefix 22.3%; instructions 11.8k of 55.9k per main call | 2.5% (`CLAUDE.md`) + 1.19% (MEMORY.md, before trim) | First-call prefix before and after a size change |
| 3 | Subagents pay the prefix again and re-read the same process files | Subagents 24.7% of units; mean prefix 52.9k; rvw-pr skill read by 24 | 24.7% | Per subagent: prefix, shared process files, PR-specific reads |
| 4 | Oversized outputs read back are the costliest read pattern | Transcript-folder reads 2.67% | about 3% | Spilled outputs and their read-back tokens per run |
| 5 | Re-reads add context without information | 24% of Read tokens | about 5% | Re-read share, and whether the second read followed an edit |
| 6 | Hidden thinking is a large carried cost | Half of output; 11.8% of context | 11.8% | Thinking share by effort level |
| 7 | The 1-hour TTL costs more than the misses it prevents | 1-hour writes 8.9% of units; 5 rebuilds cost 2.1% | under 8.9% | Simulate 5-minute TTL on the recorded timeline |
| 8 | Backlog files and linked docs are second order | 2.22%, 2.26%, 3.09% (upper bound) | 2–5% | Same, over a longer sample, with Grep hits |
| 9 | The repo's own token report understates context | 4 chars/token assumed against 2.4 measured; prefix and thinking left out | measurement | Re-run § 1 on new transcripts, compare rankings |
| 10 | The long prose tail is checkable claims nothing checks but the next round | 49–78% loop-introduced from round 4; 94% of prose findings checkable | most of a long loop | Per round, count findings a mechanical check would have caught first |
| 11 | Listed but unused skills cost on every call | 13 synced skills (Stats view: 3,160 tokens); whole listing measured at 2.6k per main session; 4.12% of BK-397's re-read context | about 1% | First-call context with and without the listing |
| 12 | An orient check for related open work prevents loops on items a redesign will reshape | Run A: BE-021 shared with 7 open items; the ID BK-389 first in context at call 2, BK-394 at call 414; whether a dialog about related items changes a plan is untested | a whole loop, on affected items | Before planning, list open items sharing spec IDs and ask how each relates; count how often the plan changes |

Sources: rows 1, 12 [work_items], [run_a_final], [run_a_orient_check]; rows
2–6, 8 [composition], [backlog_links]; row 7 [inventory]; row 9 [calibration];
row 10 [rounds], [prose_classes]; row 11 § 6.

## Run A final

**Run A finished at 59.3 M units, $137, with 94.1% in the post-PR main session
and all subagents. The
compaction at call 458 cut the main context to 113k, and six rounds later it
was back at 625k.** Figures from [run_a_final] (the finished transcript, no cut)
and [run_a_final_gates].

| Phase | Calls | Share of units | Mean context |
| --- | ---: | ---: | ---: |
| Orient and plan | 9 | 0.4% | 89k |
| Build | 120 | 5.5% | 212k |
| Review loop (main session) | 666 | 64.4% | 493k |
| Review subagents | 1,028 | 29.7% | — |

- **Two routes.** Rounds 1 to 7 ran on the original plan; the session then
  re-planned (narrowed the PR) and ran six more spawning rounds after the
  compaction [run_a_final: `rounds`, `compaction_calls`]. The first route cost
  31.5 M units; the whole run 59.3 M.
- **Compaction as a natural test of hypothesis 1 (fresh context).** Main context
  at a round's start fell from 828k (round 7) to 113k after the compaction, then
  stood at 113k, 223k, 273k, 396k, 479k and 625k at the next six rounds
  [run_a_final: `rounds`]. That is about 102k of regrowth per round ((625 − 113)
  / 5 intervals), so a one-time reset buys a few cheap rounds and the saving
  decays within one loop.
- **Gates.** Over the whole run, 33 gate runs: 3 cut off at the 600 s limit,
  the same three as at round 7, and one 37-minute idle stall
  [run_a_final_gates].
- **Prose against code findings for the second route:** § Run B baseline.

## Run B baseline: run A's route 2

**Run B has route 2's scope, so route 2's figures are recorded here for the
comparison: six rounds, 28.19 M units from the re-plan on, and 49 findings, of
which a fix-commit classifier labels 30 prose and a hand reading 37.** The
rounds are review states, not submissions: PR #1093 has 88 review submissions
over 13 rounds [pr_1093_rounds: `submissions`, `routes`]. Context and units are
from [run_a_route2], findings from [pr_1093_rounds].

RFC-0020's decision rule, written before this baseline existed, still compares
run B with run A's first route (31.5 M in total; 255k, 304k and 355k context at
rounds 1 to 3), and its metrics table lists findings by round as not yet
derived. Which route each check compares against is settled when RFC-0020 is
rewritten, after the other BK-418 changes for run B have merged; until then the
RFC's rule is the one in force.

| Round | Members | Main context at start | Main units | Subagent units | Findings | Prose (classifier) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 1 | 113k | 1.50 M | 0.39 M | 3 | 0 |
| 2 | 1 | 223k | 1.08 M | 0.29 M | 4 | 3 |
| 3 | 3 | 273k | 2.34 M | 1.57 M | 7 | 3 |
| 4 | 2 | 396k | 1.60 M | 1.07 M | 9 | 5 |
| 5 | 3 | 479k | 3.75 M | 2.21 M | 15 | 10 |
| closing | 3 | 625k | 4.39 M | 2.44 M | 11 | 9 |

From [run_a_route2: `route.rounds`] and [pr_1093_rounds: `rounds`, route 2].
The closing round's eleventh finding has no fix (the CHANGELOG stub, kept by the
maintainer's call), so its classes sum to 10.

- **Where route 2 starts.** Call 408 asks the maintainer how to proceed after
  round 7; call 409 enters plan mode, so route 2 is call 409 on, plus every
  subagent that began after it. It cost 28.19 M units: 5.56 M re-planning and
  re-building over 86 calls before its first round, and 22.62 M in the loop
  [run_a_route2: `route`]. Route totals are summed from unrounded call units,
  so they can differ by 0.01 M from sums of the rounded figures shown. The
  round-7 checkpoint cut (`--until 2026-10-09T13:35:51Z`) leaves 27.80 M after
  it. The route exceeds that by 0.38 M, all of it calls 409 to 412, which ran
  before the cut; no route-1 subagent ran past it [run_a_route2:
  `checkpoint.route_minus_after_m`, `route_main_units_before_cut_m`,
  `earlier_subagent_units_after_m`].
- **Rounds and routes.** `pr_rounds.py` groups findings by the head commit they
  were posted against, and puts a round in route 2 when that head descends from
  `cdcaa35c6`. Route 2's findings per round, 3, 4, 7, 9, 15 and 11, match the
  hand reading; route 1 has seven rounds, the last posted in its review body
  with no inline finding [pr_1093_rounds: `routes`].
- **Classifier against the hand count.** The classifier labels a finding prose
  when its fix commit changes no executable line of the finding's file. That
  gives 30 prose, 18 code and 1 unfixed; the hand reading gave 37 prose and 12
  code. Reading the fix replies of the 18 code labels, six are docstring or
  prose fixes whose commit also fixed code in the same file, or a test file, for
  another finding: the round-1 delete-pending finding, answered by a
  measurement, whose reply cites another finding's fix commit; the round-3
  `list_files` docstring; the round-4 "as below" docstring and the 3.11/3.12
  `RuntimeError`, recorded in prose rather than fixed; and the round-5
  `list_folders` docstring and stale test-module docstring. With those and the
  unfixed CHANGELOG finding counted prose, 30 + 6 + 1 = 37. The classifier
  marks 14 of the 18 code labels `shared_fix` (their fix commit also fixed
  another finding in that file); five of the six are among them, the test-module
  docstring is not, because the code in its commit was for a finding filed
  against `_local.py` [pr_1093_rounds: `code_in_shared_fix`].
- **What that means for run B.** The fix pass commits once per round, so a
  per-commit classifier cannot split a commit's prose fixes from its code fixes
  in the same file. Narrowing to the function enclosing the finding's line was
  tried and was worse: it labelled the round-1 link finding prose, whose fix added
  a new helper rather than changing the commented function. Run B's PR goes
  through the same rule, so the two runs compare like for like. On #1093 the
  rule errs toward code; a prose label can also be wrong, when the code a
  finding asked for landed only in another file and the finding's own file got
  only a docstring.

## Reproducing

**Every result file is produced by one script from inputs named in its own
`_provenance` block: a file by SHA-256, a git input by commit.** The extracts
(`calls.jsonl`, `items.jsonl`, `sessions.json`) hold prompts, session IDs and
local paths and are never committed. Every script takes `--repo-root`,
`--data` (extract directory, default `<repo-root>/tmp/token-usage-data`) and
`--results`. Transcript folders default to those
`scripts/report_token_usage.py`'s `default_dir` computes, plus worktree
siblings (`_common.default_transcripts`).

| Result file | Script | Inputs |
| --- | --- | --- |
| *(extract, not committed)* | `extract.py --since 2026-08-14` | transcripts |
| `inventory.json` | `inventory.py` | extract, `prs.json` |
| `calibration.json` | `calibrate.py` | extract |
| `composition.json` | `composition.py` | extract, `CLAUDE.md` |
| `work_items.json` | `workitems.py` | extract, `prs.json`, `sdd/traces` |
| `backlog_links.json` | `backlog_links.py --transcripts …` | extract, `CLAUDE.md` and authority-doc links, surviving transcripts |
| `trace_corpus.json` | `trace_corpus.py` (also writes `corpus.json` to `--data`) | git, `sdd/traces` |
| `surface.json` | `surface.py` | git, `origin/master` |
| *(`prs.json`, in `--data`)* | `prs.py` | GitHub GraphQL |
| `pr_model.json` | `pr_model.py` | `prs.json`, `corpus.json`, `work_items.json` |
| `ship_era.json` | `ship_era.py` | git (`BACKLOG-DONE.md` history), `prs.json`, `corpus.json` |
| `rounds.json` | `rounds.py` | `sdd/traces`, GitHub review comments (cached in `--data`) |
| `prose_labels.json` | `prose_classes.py --build` | `prose_findings.json` (`prose_fetch.py`), classifier batches |
| `prose_classes.json` | `prose_classes.py` | `prose_labels.json` |
| `run_a_round7.json`, `run_a_final.json`, `bk397_ship_run.json` | `tokkit.py report --json` (`--until` for round 7) | one `/ship` session and its subagents |
| `run_a_gates.json`, `run_a_final_gates.json` | `gates.py` (`--until` for round 7) | run A's main transcript |
| `run_a_orient_check.json` | `orient_check.py --item BUG-280 --rev ff00a1dd7` | `BACKLOG.md` at run A's base commit, run A's transcript |
| `run_a_route2.json` | `route_baseline.py --route-start-call 409 --checkpoint 2026-10-09T13:35:51Z --name run_a_route2` | run A's `tokkit.py` snapshot (`--snapshot`) |
| `pr_1093_rounds.json` | `pr_rounds.py --pr 1093 --route-start cdcaa35c6` | GitHub reviews and PR commits (cached in `--data`), the fix commits in git |

Sessions are assigned to work items through the PR they served, never by
session ID: a `pr-link` record, a PR number the first real prompt hands
`/rvw-pr` or `/fix-pr`, or, failing both, the PR whose head branch the session
was on (`_common.session_prs`). Grouping this way reproduces the scratch
analysis's hand-made session table for all eight work items. Two notes on the
extract used here: it predates the rule that skips a `/clear` wrapper as the
first prompt, and the PR-open timestamps. Both fields were refreshed from the
surviving 2026-10-04 transcripts before these results were generated.

### Corrections to the scratch analysis

**Porting re-derived every figure. Five changed, and this record carries the
corrected ones.**

- **Cache rebuilds.** The scratch analysis reported 11 rebuilds costing 0.4% of
  units. Nine of those were Claude Code's `<synthetic>` records, which carry no
  usage. Real rebuilds right after one went undetected. Measured over real calls:
  5 rebuilds, 2.1% [inventory: `cache`].
- **Thinking share of output.** 50% with the calibrated visible-output size, not
  52% at 4 characters per token [composition: `output`].
- **Calls.** 3,738 API calls, not 3,749, after dropping the 11 synthetic records
  [inventory: `calls`].
- **Bug share by month.** The scratch series counted how far the highest done ID
  in `sdd/backlogid.json` advanced each month. That is neither items closed nor
  items minted. This record counts done-entry headers as they first appear in
  `BACKLOG-DONE.md`, which turns a smooth July rise into a noisy series
  [ship_era: `backlog_exits_by_month`].
- **Oversized outputs.** The scratch figure of 43 spilled outputs (22 of them `gh
  pr diff`) was counted from raw transcripts that no longer exist. It is
  dropped. The 2.67% share is kept, narrowed to reads of files under the
  transcript folder [composition: `top_items_pct`].

Counts that depend on today's tree also moved since the scratch run: 372 traces
(was 370), 41 review blocks and 650 comments (was 42 and 633). The scripts read
the current `sdd/traces` [trace_corpus], [rounds].
