# Template: decision memo

Used in module 11. One page for the person who decides. Draft it from the numbers
(`uv run mediadoctor-lab11 memo` does this for the lab), then edit it yourself: you sign it, not the script. The
[eval report](eval-report.md) holds the detail; the [experiment log](experiment-log.md) holds the history.

```markdown
# Decision memo: <system> <what is being decided>

Date: <date> · Author: <you> · Decider: <name> · Status: draft | decided

## Decision requested
<One sentence. "Switch MediaDoctor from v1 to <config> (<model>, prompt <v>, caching)." Not a question about method.>

## Recommendation and why
- <Primary metric: before → after, paired difference with 95% CI, n.>
- <Cost per successful task: before → after (percent).>
- <Latency: p50 and p95 before → after; timeouts.>
- <How you got there: the chain of kept changes, each tested against a rule written before its run.>
- <The most tempting alternative and why it was not chosen, in one line.>

## Options considered
| Option | Success (95% CI) | Cost / success | p95 | Outcome |
|---|---|---|---|---|
| <current release> | | | | current |
| <each tested option> | | | | recommended / kept / rejected: <reason> |

## How sure we are
- <n, one run per task or k runs; the smallest difference this data can detect.>
- <The thinnest step: how many tasks changed outcome, and the pre-registered test's result.>
- <The held-out check: n, result, and that it was the only look.>
- <How success was scored (checks, judges with TPR/TNR, human labels) and what that scoring cannot see.>
- <Assumptions behind the cost numbers (prices as of <date>, traffic that keeps the cache warm).>

## What we are not saying
- <The claims a reader might take from the numbers that the data does not support.>

## Next steps
1. <What happens if approved, and what you will watch in production (cost per success, p95, failure modes).>
2. <What would make you revisit the decision.>
```

## Writing it well

- **Lead with the decision.** The first sentence is what you want the reader to approve.
- **Three numbers, each with its uncertainty.** Success, cost per successful task, p95. More belongs in the report.
- **Say how small a difference you could have seen.** "No regression detected" means nothing without it.
- **Name the weakest link.** The step with the fewest tasks behind it, the evaluator with the lowest agreement, the
  assumption the cost depends on.
- **Avoid:** "X% accurate" (say: on which set, with what interval), "no regression" (say: none detected at this
  size), "model A is worse" (say: on this task and prompt), "significant" on its own (say: which test, what interval).
- **Keep rejected options in the table** with the reason. It saves the next meeting.
