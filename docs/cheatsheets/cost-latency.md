# Cheat sheet: improving accuracy, latency, and cost

Code: `mediadoctor.experiments` (configurations, requests, grading), `mediadoctor.lab11` (metrics, decisions,
reports), `evalkit.config.Price.cost_usd`, `evalkit.stats.percentile`. CLI: `uv run mediadoctor-lab11 --help`.

## The headline number

```text
cost per successful task = total cost of every call (agent, judge, retries, escalations) / tasks that succeeded
success                  = all checks pass AND the task finished within the timeout
```

Report it next to success (Wilson CI), p50 and p95 latency (bootstrap CI for p95), timeouts, and cost per task.

## Choosing what to fix

| Quantity | Formula |
|---|---|
| value of fixing a mode | rate × severity × P(fix works) |
| per day | value ÷ effort in days |

Write the guesses down. With ~100 traces, rank big modes against small ones, not neighbours against each other.

## Experiment design (write before the run)

| Item | Example |
|---|---|
| one change from the parent | prompt v2 → v3; nothing else |
| primary metric | dev success within 15 s |
| rule for a quality change | superiority: paired 95% CI for (new − old) above 0 |
| rule for a cost change | non-inferiority: CI lower bound above −margin (0.05) and cost per success down |
| rule for caching | no change: graded answers identical, cost down, p95 held |
| guardrails | p95 ≤ 12 s; cost per success ≤ $0.01 |
| sample size | `mdd_paired(n, discordant)`; `n_paired(discordant, diff)` |
| held-out | one look, by the chosen config, `HoldoutGuard`, logged |

## Levers and what they cost

| Lever | Typical effect | Watch |
|---|---|---|
| prompt fix aimed at a mode | + success on that mode | longer prompt: cost and latency per call; check the targeted mode moved |
| few-shot examples | strong steer | tokens on every call; leakage from the eval set; over-steering |
| automated optimizer (e.g. DSPy) | hill-climbs a metric | only as good as the metric; overfits small dev sets; train split only |
| smaller model | much cheaper, faster | test as non-inferiority; failures may be invisible to your checks |
| cascade (cheap → expensive) | cheap when the router is right | router recall on the failures that matter; latency of escalations adds up |
| self-check + retry | fixes some caught defects | judge TPR/TNR; every task pays the judge; retries hit p95 |
| prompt caching | input cost of the prefix ↓ ~90-95% | needs traffic within the TTL; prefix must be byte-identical; ≥ minimum length |
| Batch API | −50% on every token | results within 24 h: evals and backfills, not users |

## Prompt caching (Claude)

```python
system = [
    {"type": "text", "text": SYSTEM, "cache_control": {"type": "ephemeral"}}
]  # caches tools + system
```

| Item | Value (check the pricing page) |
|---|---|
| prefix order | tools → system → messages, up to the `cache_control` marker |
| lifetime | 5 minutes, refreshed on each hit (1-hour option costs more to write) |
| write | 1.25 × input price |
| read | 0.05 × (Sonnet 5.5), 0.1 × (Haiku 5.5) input price |
| minimum prefix | 512 tokens (Sonnet 5.5, Haiku 5.5) |
| usage fields | `cache_creation_input_tokens`, `cache_read_input_tokens`; `input_tokens` excludes both |
| hit rate | cache reads ÷ (uncached + writes + reads) input tokens |

One call per cache lifetime costs more than no caching. The discounts stack with Batch.

## Latency

- Report p50 and p95 of whole-task time (root span), never only the mean.
- p95 of n tasks rests on about n/20 of them: give it an interval.
- Count tasks past the timeout as failures.
- Explain a regression from spans: time per kind (agent calls, self-checks, tools), then the tasks that slowed most.
- Output tokens and sequential calls dominate; caching and shorter outputs help; retries and escalations hurt the tail.

## Pareto frontier

A configuration is on the frontier if no other is both cheaper (per task) and more accurate. Dominated configs are
never the right choice; picking among frontier points is a business decision. Plot CIs: points that look separated
often are not.

## When to stop

- The next hoped-for gain is below the minimum detectable difference of your dev set.
- A perfect system would save little: compare cost per task with cost per success.
- Held-out results start trailing dev (the dev set is used up): refresh it from production.
- The taxonomy changed after a big win: redo error analysis before the next round.

## Thinking and effort

- Set `thinking` and `effort` per model (`config/models.toml`, `[generation.<model>]`); defaults differ and
  thinking counts toward `max_tokens`.
- Test the same model at a different effort before a cascade: one cache, no router. Thinking on: raise
  `max_tokens`, re-record, and report p95 and cost per success.
- A pre-registered rule names its test; below about 10 changed tasks, require the exact McNemar p as well.

## Communicating

| Document | Reader | Contents |
|---|---|---|
| experiment log | team, future you | per experiment: change, hypothesis, expected, rule, result with CI, decision (keep the failures) |
| decision memo | decider | one page: decision, three numbers, options, how sure, what we are not saying, next steps |
| eval report | reviewer | data, evaluators, full results, risks, reproduction |

Do not say "X% accurate", "no regression", "model A is worse", or "significant" without n, interval, and scope.
