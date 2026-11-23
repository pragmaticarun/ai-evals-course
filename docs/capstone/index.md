# MediaDoctor eval report: replace `v1` with `retry`?

**Date:** 2026-11-23 · **Author:** the course (reference report for [module 12](../modules/12-capstone/index.md)) · **Slice:** audio-focus · **Held-out look:** spent (release run)

!!! info "Synthetic-authored model behaviour, real everything else"
    The model turns, token counts, and latencies in every fixture this report reads were written by the
    course's `scripts/author_module*_fixtures.py` scripts and are labelled `synthetic-authored`. The numbers
    show what the method produces; they make no claim about how Claude models behave on your system. The
    agent loop, tools, checks, judge prompts, prices, and statistics are real code, and this page is
    regenerated from them by `uv run mediadoctor-capstone report`.

## 1. Decision requested

Approve `retry` as the release configuration in `config/release.toml`, in place of `v1`. `retry` is the end of a chain of changes that each passed its own pre-registered test (`v1` → `v2` → `v3` → `v3-cache` → `retry`; section 7). Separately, fund the follow-ups in section 9, starting with the app 4.2.0 evidence regression and the audio-focus slice.

## 2. Summary

- **Better answers.** On the 29 held-out queries, read once and never used to choose: `retry` 0.966 (28/29) [0.828, 0.994] against 0.828 (24/29) [0.655, 0.924] for `v1`, a difference of +0.138 [+0.000, +0.310]: the unbiased estimate, and too few queries to pin the size down. On the 108 dev queries every step was chosen on, 0.898 (97/108) [0.827, 0.942] against 0.667 (72/108) [0.573, 0.748], +0.231 [+0.157, +0.315] (25 fixed, 0 broken); optimistic, because the configuration was selected on them.
- **Cheaper per successful task.** $0.00428 [$0.00381, $0.00483] against $0.00880 [$0.00782, $0.01020], a change of -51%; p95 latency 10.4 s [8.3, 11.3] against 10.1 s, inside the 12 s guardrail.
- **Not a fix for everything.** Production monitoring shows evidence failures at 16.1% on app 4.2.0 against 0.0% on 4.1.3 (CUSUM alarm 19.7 h after the rollout), which this change does not address; the audio-focus slice is the weakest topic under `retry` at 0.667 (8/12) [0.391, 0.862].

## 3. Scope

| Item | Value |
|---|---|
| System | MediaDoctor, the course's Android and multimedia debugging agent (tool-calling, with KB retrieval) |
| Baseline | `v1`: claude-sonnet-5-5, prompt v1, no caching, single attempt |
| Candidate | `retry`: claude-sonnet-5-5, prompt v3, caching on, strategy retry |
| Judges | Haiku 5.5 (`claude-haiku-5-5`) for every LLM judge and the self-check |
| Prompt versions | agent v1, v2, v3 (`mediadoctor.experiments.PROMPTS`); judges as validated in module 5 |
| Dates | experiments pre-registered and run 2026-11-23; production window 2026-11-16 to 2026-11-22; report 2026-11-23 |
| Out of scope | real user traffic (all data is synthetic-authored), languages other than English, load and concurrency, multi-turn chat beyond module 7's simulated sessions, modes module 11 did not label (see section 8) |

## 4. Data

| Set | Size | How it was built | Used for |
|---|---|---|---|
| Module 1 smoke set | 20 queries | hand-written | the first baseline and code checks |
| Module 3 traces | 100 traces | synthetic-authored agent runs, open and axial coded | the failure taxonomy |
| Module 4 dataset v1 | 182 queries (train 88, dev 45, test 49) | dimension tuples → LLM-written queries, checked and deduplicated | judges, stats, experiments |
| Golden set | mediadoctor-golden 1.0.1, 12 files | module 8 manifest with hashes and splits | the CI gate |
| Experiment cases | 108 dev + 29 held out | module 5's agent slice of dataset v1 | this decision |
| Module 7 retrieval set | 48 labelled queries, 57 KB sections | hand-labelled relevance | the architecture-specific eval |
| Module 9 traffic | 776 requests over 7 days | simulated production with a rollout and a model snapshot change | monitoring |
| Module 10 suites | 60 attacks, 60 benign requests | authored attacks over five vectors, plus hard negatives | red-teaming |

**Coverage gaps.** Dataset v1 covers 242/242 feasible pairs of dimension values overall, but the dev split alone covers 202/242 and test 183/242, so some combinations are only ever seen in training. Every query is synthetic: the phrasing of real support tickets, real devices outside the course's device table, and non-English questions are not represented.

## 5. Failure taxonomy

From [module 3](../modules/03-error-analysis/index.md)'s 100 coded traces of `v1` (52 failing), ranked by count × severity:

| # | Failure mode | Traces | Rate (k/n) [95% CI] | Severity | Fix | Example trace |
|---|---|---|---|---|---|---|
| 1 | ignored-tool-output | 11 | 0.110 (11/100) [0.063, 0.186] | 3 | medium | `m3t003` |
| 2 | fabricated-evidence | 8 | 0.080 (8/100) [0.041, 0.150] | 3 | easy | `m3t033` |
| 3 | skipped-investigation | 8 | 0.080 (8/100) [0.041, 0.150] | 2 | easy | `m3t014` |
| 4 | wrong-tool-args | 8 | 0.080 (8/100) [0.041, 0.150] | 2 | easy | `m3t001` |
| 5 | wrong-api-detail | 8 | 0.080 (8/100) [0.041, 0.150] | 2 | medium | `m3t002` |
| 6 | retrieval-miss | 7 | 0.070 (7/100) [0.034, 0.137] | 2 | medium | `m3t019` |
| 7 | redundant-steps | 5 | 0.050 (5/100) [0.022, 0.112] | 1 | easy | `m3t008` |
| 8 | vague-next-step | 3 | 0.030 (3/100) [0.010, 0.085] | 1 | easy | `m3t048` |
| 9 | format-violation | 2 | 0.020 (2/100) [0.006, 0.070] | 1 | easy | `m3t044` |

**Before and after,** for the four modes module 11's reference labels record in final answers (dev, n = 108; paired difference in the share of queries with the mode):

| Mode | v1 | retry | Change [95% CI] |
|---|---|---|---|
| accepted-false-premise | 0.157 (17/108) [0.101, 0.238] | 0.046 (5/108) [0.020, 0.104] | -0.111 [-0.176, -0.056] |
| ignored-tool-output | 0.093 (10/108) [0.051, 0.162] | 0.046 (5/108) [0.020, 0.104] | -0.046 [-0.083, -0.009] |
| skipped-investigation | 0.037 (4/108) [0.014, 0.091] | 0.000 (0/108) [0.000, 0.034] | -0.037 [-0.074, -0.009] |
| format-violation | 0.037 (4/108) [0.014, 0.091] | 0.009 (1/108) [0.002, 0.051] | -0.028 [-0.065, +0.000] |

Where the first failure happens in a failing trace (module 3): chat:answer 24, chat:plan 13, retrieval 7, execute_tool ffprobe 4. Most failures start in the model's final answer or its plan, not in the tools, which is why the improvements in section 7 are prompt and self-check changes.

## 6. Evaluators

Every judge was validated against human labels on a split it was not tuned on. PASS is the positive class: TPR is the share of good answers the judge passes, TNR the share of bad answers it fails.

| Evaluator | Built in | Validated on | TPR | TNR |
|---|---|---|---|---|
| `tool-grounding@v2` judge | module 5 | test, n=25 | 0.90 (18/20) | 0.60 (3/5) |
| `false-premise@v1` judge | module 5 | test, n=29 | 0.96 (23/24) | 0.60 (3/5) |
| `next-step@v1` judge | module 5 | test, n=29 | 0.92 (23/25) | 1.00 (4/4) |
| RAG faithfulness judge | module 7 | n=96 | 0.94 (67/71) | 0.68 (17/25) |
| RAG answer relevance judge | module 7 | n=96 | 0.94 (76/81) | 0.87 (13/15) |
| Self-check judge (the retry step) | module 11 | dev first answers, n=108 | 0.99 (91/92) | 0.88 (14/16) |
| Injection detector (guardrails v2) | module 10 | screened texts, n=82 | flags 0.85 of injections (34/40) | passes 0.95 of clean texts (40/42) |

Code checks need no validation set of their own but were checked against the same labels: format, citations (every cited KB id exists), investigated (a tool ran before the answer), and the reference check of the diagnosis. Trace checks from module 2 (evidence is real, no repeated retrieval, step budget) pass on format 8/8, evidence_is_real 7/8, no_repeat_retrieval 7/8, step_budget 7/8 of the module 2 traces.

**Judge error changes the numbers you report.** The tool-grounding judge's raw pass rate on 89 unlabelled traces is 0.820; corrected for its TPR and TNR it is 0.840 [0.236, 1.000] (the reference labels say 0.876). The corrected interval is wide because the judge was validated on only 25 labelled traces: more labels, not a better prompt, is what narrows it.

## 7. Results

### Configurations on dev (n = 108)

Each kept change was tested against its parent with a rule written down before the run (`config/experiments/preregistration.toml`). Success means all four checks pass within the 15 s timeout.

| Configuration | Success [95% CI] | p50 s | p95 s | Cost/task | Cost/success [95% CI] | Verdict |
|---|---|---|---|---|---|---|
| `v1` | 0.667 (72/108) [0.573, 0.748] | 5.09 | 10.06 | $0.00586 | $0.00880 [$0.00782, $0.01020] | baseline |
| `v2` | 0.759 (82/108) [0.671, 0.830] | 5.24 | 8.09 | $0.00619 | $0.00815 [$0.00734, $0.00919] | keep |
| `v3` | 0.833 (90/108) [0.752, 0.892] | 5.91 | 11.61 | $0.00818 | $0.00981 [$0.00892, $0.01077] | keep |
| `v3-cache` | 0.852 (92/108) [0.773, 0.907] | 5.14 | 7.76 | $0.00342 | $0.00402 [$0.00365, $0.00443] | keep |
| `haiku` | 0.639 (69/108) [0.545, 0.723] | 1.90 | 3.30 | $0.00018 | $0.00028 [$0.00025, $0.00034] | reject |
| `cascade` | 0.694 (75/108) [0.602, 0.773] | 2.07 | 7.25 | $0.00048 | $0.00069 [$0.00044, $0.00100] | reject |
| `retry` | 0.898 (97/108) [0.827, 0.942] | 5.84 | 10.42 | $0.00384 | $0.00428 [$0.00381, $0.00483] | keep |

Each kept step against its parent (paired, same queries):

| Step | Change | Difference [95% CI] | Fixed / broken | McNemar p |
|---|---|---|---|---|
| `v1` → `v2` | prompt | +0.093 [+0.037, +0.157] | 11 / 1 | 0.006 |
| `v2` → `v3` | prompt | +0.074 [+0.019, +0.139] | 10 / 2 | 0.039 |
| `v3` → `v3-cache` | prompt caching of tools + system prompt | +0.019 [+0.000, +0.046] | 2 / 0 | 0.500 |
| `v3-cache` → `retry` | self-check | +0.046 [+0.009, +0.093] | 5 / 0 | 0.062 |

**Held-out confirmation** (read once, logged in `runs/capstone/holdout_log.csv`): `v1` 0.828 (24/29) [0.655, 0.924], `retry` 0.966 (28/29) [0.828, 0.994], paired difference +0.138 [+0.000, +0.310] (5 fixed, 1 broken, McNemar p = 0.22).

### Per-case diff

`v1` → `retry` fixed 25 queries and broke 0. Fixed, by the baseline's failure: accepted-false-premise 12, ignored-tool-output 5, skipped-investigation 4, format-violation 3, timed out 1.

| Case | Topic | v1 mode | retry answer (first line) |
|---|---|---|---|
| `m4q001` | hdr-colour | timed out | Likely cause: The device is not the limit: the atlas-a1 has a hardware HEVC decoder with Main10HDR10 and an HD... |
| `m4q005` | av1-playback | accepted-false-premise | Likely cause: That premise does not hold here. Yes: the atlas-a1 has c2.atlas.av1.decoder, a hardware AV1 deco... |
| `m4q006` | hdr-colour | ignored-tool-output | Likely cause: The device is not the limit: the atlas-a1 has a hardware HEVC decoder with Main10HDR10 and an HD... |
| `m4q021` | audio-focus | accepted-false-premise | Likely cause: That premise does not hold here. The app does not request audio focus, or ignores losing it, so ... |
| `m4q026` | av1-playback | format-violation | Likely cause: Yes: the atlas-a1 has c2.atlas.av1.decoder, a hardware AV1 decoder for Main and Main10 up to 384... |

(First five of 25; `uv run mediadoctor-lab11 trace retry CASE` shows any of them.)

### Latency and cost from traces

| Configuration | Median latency | p90 latency | Median cost | p90 cost | Most expensive traces |
|---|---|---|---|---|---|
| `v1` | 5.09 s | 7.48 s | $0.00583 | $0.00820 | `m4q065` $0.00856, `m4q159` $0.00840, `m4q004` $0.00838 |
| `retry` | 5.84 s | 8.41 s | $0.00371 | $0.00538 | `m4q132` $0.00870, `m4q081` $0.00841, `m4q172` $0.00839 |

`retry` retried 15 of 108 tasks; those carry the extra latency. Cache hit rate 64% of input tokens.

### Trace checks next to answer quality

| Check | v1 | retry |
|---|---|---|
| format | 0.963 (104/108) [0.909, 0.986] | 0.991 (107/108) [0.949, 0.998] |
| citations | 0.963 (104/108) [0.909, 0.986] | 1.000 (108/108) [0.966, 1.000] |
| investigated | 0.972 (105/108) [0.921, 0.991] | 1.000 (108/108) [0.966, 1.000] |
| correct | 0.750 (81/108) [0.661, 0.822] | 0.907 (98/108) [0.838, 0.949] |

### Architecture-specific eval: retrieval and RAG (module 7)

| Retrieval config | recall@5 [95% CI] | MRR | nDCG |
|---|---|---|---|
| fixed+keyword | 0.639 [0.531, 0.740] | 0.72 | 0.61 |
| fixed+bm25 | 0.708 [0.608, 0.795] | 0.79 | 0.70 |
| section+keyword | 0.736 [0.628, 0.833] | 0.80 | 0.72 |
| section+bm25 | 0.806 [0.715, 0.885] | 0.85 | 0.80 |

Section chunking with BM25 improves recall@5 by +0.167 [+0.087, +0.250] (n = 48). End to end, the improved RAG answers are correct and faithful on 0.604 against 0.562 (+0.042 [-0.042, +0.125]): retrieval got better, but the end-to-end interval includes zero. Attribution of the improved system's failures: 11 generation, 8 retrieval, so a generation fix is worth more than more retrieval work.

### Statistics that qualify the headline (module 6)

Five repeated runs of v2 on 37 queries: run pass rates 0.46, 0.49, 0.49, 0.46, 0.38; 7 always pass, 11 never pass, and 19 are flaky. One run of a configuration is one draw: module 11's fixtures pin one draw per query, so the dev differences above are conditional on it.

### CI gate (module 8)

The release configuration passes its gate against the committed baseline (pass: code tier pass, judge tier pass); the golden manifest has 0 problems. Switching `config/release.toml` to `retry` will change the request keys, so the pull request must re-record the gate fixtures and update `evals/baseline.json`.

### Monitoring (module 9)

| Signal | Reference rate | CUSUM alarm | After rollout |
|---|---|---|---|
| evidence_fail | 1.3% | Fri 20 Nov 05:42 IST | +19.7 h |
| tool_error | 8.9% | Thu 19 Nov 14:57 IST | +5.0 h |
| thumbs_down | 3.8% | no alarm | - |
| format_fail | 0.8% | no alarm | - |

After the rollout, by app version: evidence failures 0.000 (0/112) [0.000, 0.033] on 4.1.3 and 0.161 (41/255) [0.121, 0.211] on 4.2.0; tool errors 0.089 (10/112) [0.049, 0.157] and 0.408 (104/255) [0.349, 0.469].

### Red team (module 10)

| Guardrails | Attack success rate [95% CI] | Benign false-positive rate [95% CI] |
|---|---|---|
| none | 0.633 (38/60) [0.507, 0.744] | 0.000 (0/60) [0.000, 0.060] |
| v1 | 0.433 (26/60) [0.316, 0.559] | 0.100 (6/60) [0.047, 0.201] |
| v2 | 0.033 (2/60) [0.009, 0.114] | 0.050 (3/60) [0.017, 0.137] |

The weakest vector under v2 is `filename` at 0.222 (2/9) [0.063, 0.547].

### Slice deep-dive

| Topic | n | v1 | retry | Paired difference [95% CI] |
|---|---|---|---|---|
| audio-focus | 12 | 0.417 | 0.667 | +0.250 [+0.000, +0.500] |
| av-sync | 13 | 0.769 | 1.000 | +0.231 [+0.000, +0.462] |
| av1-playback | 18 | 0.611 | 0.944 | +0.333 [+0.111, +0.556] |
| codec-limits | 16 | 0.812 | 0.875 | +0.062 [+0.000, +0.188] |
| drm-resolution | 15 | 0.867 | 1.000 | +0.133 [+0.000, +0.333] |
| hdr-colour | 19 | 0.421 | 0.789 | +0.368 [+0.158, +0.579] |
| live-stream | 9 | 0.778 | 1.000 | +0.222 [+0.000, +0.556] |
| mp4-startup | 6 | 0.833 | 1.000 | +0.167 [+0.000, +0.500] |

### The audio-focus slice

Chosen because it is the topic where `retry` does worst on dev (`uv run mediadoctor-capstone slices`). Every number below is on the 12 dev queries in this topic, so the intervals are wide: read them before the point estimates.

**Every configuration on the slice** (success, Wilson 95% CI):

| Configuration | Success on audio-focus |
|---|---|
| `v1` | 0.417 (5/12) [0.193, 0.680] |
| `v2` | 0.583 (7/12) [0.320, 0.807] |
| `v3` | 0.583 (7/12) [0.320, 0.807] |
| `v3-cache` | 0.583 (7/12) [0.320, 0.807] |
| `haiku` | 0.417 (5/12) [0.193, 0.680] |
| `cascade` | 0.500 (6/12) [0.254, 0.746] |
| `retry` | 0.667 (8/12) [0.391, 0.862] |

**Paired, v1 → retry on the slice:** +0.250 [+0.000, +0.500]; fixed 3, broken 0, McNemar p = 0.25.

| Failure mode (reference labels) | v1 | retry |
|---|---|---|
| accepted-false-premise | 2 | 0 |
| ignored-tool-output | 3 | 3 |
| skipped-investigation | 1 | 0 |
| format-violation | 1 | 1 |

**Queries `retry` still fails on this slice** (4):

| Case | Mode | Question |
|---|---|---|
| `m4q078` | ignored-tool-output | How should a Media3 app handle phone calls and navigation prompts? |
| `m4q099` | ignored-tool-output | our podcast app keeps playing during phnoe calls |
| `m4q169` | ignored-tool-output | we already confirmed audiofocusrequest works from api 21, ticket from a user: ho |
| `m4q176` | format-violation | AudioFocusRequest works from API 21, so it's not that. Customer report - how do  |

**The retry step's self-check judge on this slice** (first answers, PASS is positive): TPR 7/7, TNR 5/5. It triggered 5 retries here and 1 of them ended correct (across all dev topics: 6 of 15). Too few retries to say whether the retry works better or worse here; what the slice does show is which failures survive it.

**Coverage of the slice** (dev queries per value):

- evidence: none 12
- ambiguity: clear 6, false-premise 6
- expertise: expert 2, intermediate 4, novice 6
- persona: app-developer 4, media-engineer 2, qa-tester 3, support-agent 3
- goal: diagnose 2, how-to 10

**Held out:** 10 test queries in this topic; v1 0.600 (6/10) [0.313, 0.832], retry 1.000 (10/10) [0.722, 1.000].

**What the slice can and cannot show.** With 12 paired queries and a discordant share of 0.25, no difference smaller than the discordant share itself can be reliably detected (80% power, α = 0.05). A 10-point slice-specific improvement would need about 182 more queries in this topic, so the next experiment needs more data before it can be read on the slice alone.

## 8. Risks and caveats

- **Synthetic data.** Every fixture is synthetic-authored. The method transfers; the rates do not. Re-record live (module 12, *Make it your own*) before using any number for a real decision.
- **Sample size.** 108 dev queries detect a paired change of about 0.13; the audio-focus slice (12 queries) cannot detect anything smaller than its discordant share. A step can be detected below that size only when almost every query that changed moved the same way: the last step, +0.046 [+0.009, +0.093], rests on 5 fixed and 0 broken queries.
- **The last step's test.** `retry` was kept by the pre-registered rule (a paired bootstrap interval above zero), but it rests on 5 changed queries, and the exact McNemar p is 0.06. Module 6 trusts the exact test below about 10 changed queries; amendment 1 of the pre-registration requires it from the next study on. Read the last step as likely, not proven, and confirm it on more queries.
- **Judge error.** The self-check judge fails 1 good first answers and passes 2 bad ones on dev; the other judges' TNRs (section 6) are lower than their TPRs, so raw judge pass rates overstate quality.
- **Metric definitions differ across modules.** Module 6 grades all human-labelled failure modes (v1 → v2 +0.051 [-0.044, +0.146]); module 11 grades four checks (v1 → v2 +0.093 [+0.037, +0.157]). They answer different questions; do not quote one as the other.
- **Modes not tracked after the change.** Module 11's labels cover four modes. Fabricated evidence, wrong tool arguments, wrong API details, and retrieval misses (modules 3 and 7) were not re-measured for `retry`.
- **Distribution shift.** Production traffic after the 4.2.0 rollout differs from the dev set (more AV1, a new device); the dev results say nothing about it.
- **Latency headroom.** p95 10.4 s with an upper CI of 11.3 s against a 12 s guardrail.
- **Security.** Guardrails v2 still let 2 of 60 attacks through and refuse 3 of 60 benign requests; the suite has 60 cases, so a 0% observed rate would still allow an upper bound near 6%.

## 9. Recommendation and next steps

**Ship `retry`.** It is better on dev with an interval that excludes zero, and the one held-out look points the same way (+0.138 [+0.000, +0.310]; with 29 queries it is a check for a reversal, not a second significance test). It is also cheaper per successful task. Ship it behind module 8's gate, with module 9's monitors unchanged, and watch p95 latency for the first week.

1. Investigate the evidence-failure regression on app 4.2.0 before rollout widens (owner: app team; module 9's dashboard is the success measure).
2. Close the `filename` injection vector (module 10), then re-run the red-team gate.
3. audio-focus: the top remaining mode is ignored-tool-output. Pre-register a slice-specific fix, and write about 182 more audio-focus queries (module 4) so the experiment can be read on the slice.
4. Re-label a sample of the candidate's answers for the modes module 11 did not track (section 8).
5. Rotate the held-out split (module 8's `rotate`) now that it has been read for this decision.

## 10. Appendix

- **Code version:** `git log -1 --format=%H -- docs/capstone/index.md` (the commit that published this page)
- **Inputs fingerprint:** `4ebd82858623197e` (sha256 of `fixtures/recorded`, `data`, and `config`)
- **Golden set:** mediadoctor-golden 1.0.1
- **Reproduce:**

```bash
uv run mediadoctor-capstone report --slice audio-focus --release --date 2026-11-23 --out runs/capstone/report.md
uv run mediadoctor-capstone run         # the stage summary
uv run mediadoctor-lab11 trace retry m4q001   # any quoted trace
```

- **Trace and case ids quoted in this report:** `m4q001`, `m4q005`, `m4q006`, `m4q021`, `m4q026`, `m4q078`, `m4q099`, `m4q169`, `m4q176`; module 3 examples `m3t003`, `m3t033`, `m3t014`, `m3t001`, `m3t002`, `m3t019`, `m3t008`, `m3t048`, `m3t044`; module 9 alarms at requests `r0513`, `r0458`.
- **Where each number comes from:** [module 1](../modules/01-why-evals/index.md), [module 2](../modules/02-agent-with-tracing/index.md), [module 3](../modules/03-error-analysis/index.md), [module 4](../modules/04-synthetic-data/index.md), [module 5](../modules/05-evaluators-and-judges/index.md), [module 6](../modules/06-trustworthy-metrics/index.md), [module 7](../modules/07-architectures/index.md), [module 8](../modules/08-ci-cd/index.md), [module 9](../modules/09-monitoring-and-annotation/index.md), [module 10](../modules/10-red-teaming/index.md), [module 11](../modules/11-improving-with-evidence/index.md).
