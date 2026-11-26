# Template: experiment log entry

Used in module 11. One entry per experiment, in a file the whole team can read (the lab keeps the pre-run half in
`config/experiments/log.toml` and renders the rest with `uv run mediadoctor-lab11 log`). Fill in the first block
**before** the run and do not edit it afterwards; if you must change the plan, add a dated amendment and say why.
Keep failed and inconclusive experiments: they stop the next person from repeating them.

## Before the run

| Field | What to write | Example |
|---|---|---|
| **ID and date** | a short id, the date the plan was written | E3, 2026-11-23 |
| **Parent → variant** | the configuration you compare against, and the new one | v3 → v3-cache |
| **The one change** | exactly what differs; if more than one thing, plan the ablation | cache the tools and system prompt |
| **Why** | the failure mode or cost line it targets, and its expected value | input tokens are about three quarters of a v3 model call's cost |
| **Hypothesis** | what you expect and why, in one sentence | caching cuts input cost without changing any answer |
| **Expected effect** | direction and rough size on each axis | cost/task −40 to −60%; answers identical; p50 slightly lower |
| **Primary metric** | the one number the decision rests on, and on which split | dev success within 15 s (n=119) |
| **Decision rule** | superiority, non-inferiority (with margin), or no-change; the test | no-change: graded answers identical, cost/success down, p95 held |
| **Guardrails** | metrics that must not get worse | p95 ≤ 12 s; cost/success ≤ $0.01 |
| **Power** | minimum detectable difference for this n | ~8 points at 10% discordant |

## After the run

The examples are module 11's E3 (`uv run mediadoctor-lab11 report` and `log`).

| Field | What to write | Example |
|---|---|---|
| **Commit and fixtures** | the git sha and the fixture or trace set the run used | `abc1234`, `mediadoctor-m11-*` |
| **Result** | primary metric for both, the paired difference with its CI, discordant counts | 0.714 → 0.639, −0.076 [−0.143, −0.017], 12 broken / 3 fixed; 23 of 119 answers grade differently |
| **Cost and latency** | cost per task, cost per success, p50, p95 (with CI) | $0.00842 → $0.00451 per task (−46%); $0.01178 → $0.00706 per success; p95 14.8 → 13.4 s |
| **What moved** | which failure modes changed, from the labels or judges | by the labels, little (0 and 3 skipped investigations); the answers are a different sample, not a changed behaviour |
| **Decision** | keep / reject / inconclusive, citing the rule | reject: graded answers not identical, and the latency guardrail missed (p95 13.4 s > 12 s), although cost per success fell below the one-cent guardrail |
| **Surprises and follow-ups** | anything unexpected, and the next experiment it suggests | the two runs were independent samples, so "no change" cannot be checked; rerun at temperature 0 or with several runs per configuration. The few-shot examples are now almost free |
