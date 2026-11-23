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
| **Why** | the failure mode or cost line it targets, and its expected value | input tokens are about four fifths of v3's cost per task |
| **Hypothesis** | what you expect and why, in one sentence | caching cuts input cost without changing any answer |
| **Expected effect** | direction and rough size on each axis | cost/task −40 to −60%; answers identical; p50 slightly lower |
| **Primary metric** | the one number the decision rests on, and on which split | dev success within 15 s (n=108) |
| **Decision rule** | superiority, non-inferiority (with margin), or no-change; the test | no-change: graded answers identical, cost/success down, p95 held |
| **Guardrails** | metrics that must not get worse | p95 ≤ 12 s; cost/success ≤ $0.01 |
| **Power** | minimum detectable difference for this n | ~8 points at 10% discordant |

## After the run

| Field | What to write | Example |
|---|---|---|
| **Commit and fixtures** | the git sha and the fixture or trace set the run used | `abc1234`, `mediadoctor-m11-*` |
| **Result** | primary metric for both, the paired difference with its CI, discordant counts | 0.833 → 0.852, +0.019 [+0.000, +0.046], 0 broken / 2 fixed |
| **Cost and latency** | cost per task, cost per success, p50, p95 (with CI) | $0.00981 → $0.00402 per success; p95 11.6 → 7.8 s |
| **What moved** | which failure modes changed, from the labels or judges | none; two v3 timeouts finished in time |
| **Decision** | keep / reject / inconclusive, citing the rule | keep (answers identical, cost down, p95 held) |
| **Surprises and follow-ups** | anything unexpected, and the next experiment it suggests | the few-shot examples are now almost free |
