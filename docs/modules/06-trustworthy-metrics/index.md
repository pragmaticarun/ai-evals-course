# 6. Metrics you can trust: signal, noise, and honest comparisons

**Goal:** know when a number is real and when it is noise.

**Estimated time:** 6 hours (lesson 1.5 h, lab 3 h, exercises and quiz 1.5 h)

By the end of this module you will be able to:

- name the three sources of noise in an eval number (which queries, which run, which evaluator) and measure
  run-to-run variance with repeated trials;
- put a Wilson or bootstrap confidence interval on every pass rate, and correct judge-measured rates for judge error;
- work out how many queries a decision needs (power, minimum detectable difference) before you collect them;
- compare two prompts on the same queries with a paired bootstrap and McNemar's test;
- avoid the multiple-comparisons trap when you slice results or test many failure modes;
- report per-failure-mode metrics instead of one aggregate score, and recognise vanity metrics;
- produce a small metric report that says what changed and how sure you are.

Artifacts: `evalkit.stats` with tests (`labs/evalkit/src/evalkit/stats.py`, `tests/test_stats.py`), the
[stats cheat sheet](../../cheatsheets/stats.md), and a metric report (`runs/m6_report.md`).

## Intuition: every metric is a measurement with an error bar

You would not merge a decoder optimisation because one benchmark run was 3% faster. You would run it a few
dozen times, look at the spread, and check the difference against it, because thermal state, scheduling, and
cache warmth all move the number. Eval pass rates are the same kind of measurement, with more sources of noise.

Take a case that comes up all the time: prompt A passes 49 of 60 queries (82%), prompt B passes 47 (78%). The 95%
intervals are [0.70, 0.89] and [0.66, 0.87]; a two-sample test gives p ≈ 0.65. With 60 queries, the smallest
change you could reliably detect from 80% is about 16 points. The 3-point gap is a coin flip, yet it is exactly
the kind of number that ends up in a status update as "B regressed quality by 3%".

So: every rate gets an n and an interval, every comparison gets a paired test, and you decide before you look how
big a change you need to detect.

## Step 1: where the noise comes from

| Source | What varies | How to see it | What helps |
|---|---|---|---|
| Sampling | which queries you happened to evaluate | confidence interval over queries | more queries; paired comparisons |
| Run-to-run | the model's answer to the same query | repeat each query k times | repeated trials; report pass^k |
| Evaluator | the judge's verdict on the same answer | TPR and TNR on labelled data (module 5) | better judges; correction with an interval |

**Run-to-run variance is real even when nothing changed.** In the lab, prompt v2 was run 5 times on the same 37
dev queries. Its pass rate came out 0.46, 0.49, 0.49, 0.46, and 0.38. Compare run 2 with run 5 as if they were two
prompts and you get −11 points with a paired interval of [−0.24, 0.00]: an apparent regression between two runs
of the *same* prompt. 19 of the 37 queries passed in some runs and failed in others.

**Temperature does not make this go away, and you can no longer set it.** Lowering temperature narrowed the
sampling, but Anthropic's API reference long noted that even temperature 0.0 was not fully deterministic. Since
API version `2026-10-21` (the default in the `anthropic` 2.x SDK this course pins), a Messages request that sends
`temperature`, `top_p`, or `top_k` returns a 400 error on every model, even at the default value
([migration guide](https://platform.claude.com/docs/en/api/migration-2026-10-21)). Part of the variation comes from
the serving stack itself (batching changes floating-point reduction order; see Thinking Machines'
[Defeating Nondeterminism in LLM Inference](https://thinkingmachines.ai/blog/defeating-nondeterminism-in-llm-inference/)).
Evaluate at the settings you ship, and measure the variance instead of hoping it away.

**Repeated trials in replay.** The live API gives a new sample every call, but a fixture store keyed by the request
would replay the same answer five times. `evalkit` now takes a trial number: `LLM(namespace, trial=n)` mixes `n`
into the fixture key, so run 1 is trial 0 (the ordinary fixture) and runs 2 to 5 are trials 1 to 4, each replaying
its own recorded answers.

## Step 2: confidence intervals for a pass rate

A pass rate is k passes out of n queries: a binomial proportion. The textbook interval p ± 1.96·√(p(1−p)/n)
(the Wald interval) breaks exactly where evals live: at 6/6 it gives [1.00, 1.00], and near 0 or 1 it can leave
[0, 1]. Use the **Wilson score interval** instead (`stats.wilson_interval(k, n)`). It stays inside [0, 1], behaves
at small n, and is what the rest of the course prints.

| k / n | Rate | Wilson 95% interval |
|---|---|---|
| 6 / 6 | 1.00 | [0.61, 1.00] |
| 3 / 5 | 0.60 | [0.23, 0.88] |
| 52 / 137 | 0.38 | [0.30, 0.46] |
| 49 / 60 | 0.82 | [0.70, 0.89] |

For anything that is not a simple proportion (a difference, a mean score, a corrected rate, a ratio), use the
**percentile bootstrap** (`stats.bootstrap_ci(data, statistic)`): resample the queries with replacement a few
thousand times, recompute the statistic, and take the middle 95%. Two rules:

- **Resample the unit you sampled.** If each query was run five times, resample queries and keep their five runs
  together; resampling individual runs pretends you have five times as many independent queries. The same holds
  for multi-turn sessions or several questions about one file. Evan Miller's
  [Adding Error Bars to Evals](https://arxiv.org/abs/2411.00640) covers this clustering effect.
- **Seed it.** `bootstrap_ci` takes a seed, so the report does not change between runs of the report.

The module 5 judge numbers, with their intervals, show why this matters
(`mediadoctor-lab06 judges`):

| Judge | Split | TPR | TNR |
|---|---|---|---|
| tool-grounding v2 | dev | 0.89 [0.72, 0.96] (n=27) | 1.00 [0.61, 1.00] (n=6) |
| tool-grounding v2 | test | 0.90 [0.70, 0.97] (n=20) | 0.60 [0.23, 0.88] (n=5) |
| false-premise v1 | test | 0.96 [0.80, 0.99] (n=24) | 0.60 [0.23, 0.88] (n=5) |
| next-step v1 | test | 0.92 [0.75, 0.98] (n=25) | 1.00 [0.51, 1.00] (n=4) |

Every TNR is estimated from 4 to 6 failures, and its interval spans most of the scale. That is the honest reading
of module 5, and it is why the corrected pass rate there had the interval [0.24, 1.00]. The judge-error correction
and its bootstrap now live in `evalkit.stats` (`corrected_pass_rate`, `bootstrap_corrected`); `evalkit.judge`
re-exports them, so module 5 code is unchanged.

## Step 3: how many queries do you need?

Decide the smallest change worth detecting first, then size the eval set for it. Three questions, three formulas
(all in `evalkit.stats`):

- **How precise is one rate?** For a ±h interval at rate p: n ≈ 1.96² · p(1−p) / h². At p = 0.8, ±5 points needs
  246 queries (`n_for_halfwidth`).
- **Can I detect p₁ → p₂ between two variants run on different queries?** The two-proportion power formula
  (`n_two_proportions`): 80% → 85% at α = 0.05 and 80% power needs 906 queries *per variant*.
- **Can I detect it when both variants run on the same queries?** Only the queries where they disagree carry
  information, so the answer depends on the discordant share ψ (from a pilot or a previous comparison). Connor's
  approximation (`n_paired`) with ψ = 0.15 gives 469 queries in total.

Turn it around for the eval set you have: `mdd_two_proportions(n, p)` and `mdd_paired(n, ψ)` give the minimum
detectable difference. With the lab's 137 queries, v1's pass rate of 0.38, and a discordant share of 0.33, that is
about 17 points unpaired and 14 points paired. Anything smaller is invisible to this set, however the numbers look.

Two consequences worth remembering. The n you need grows with 1/δ²: halving the change you want to see needs four
times the queries. And rates near 0 or 1 are cheaper: 95% → 99% needs 285 per variant, because there is less
binomial noise there.

## Step 4: compare two prompts on the same queries

The lab compares agent prompt v1 with v2, which adds an instruction to check the user's claims before building
on them (aimed at module 5's accepted-false-premise failures). Both ran once on the same 137 labelled queries.

### Worked example

Looked at as two separate rates, v2 is ahead: 0.38 [0.30, 0.46] for v1 against 0.43 [0.35, 0.51] for v2, about
5 points. The intervals overlap, but overlapping intervals are not a test, and they ignore that the queries are
shared.

Pair them. On 137 queries, 19 pass under v1 only and 26 under v2 only; the other 92 behave the same under both.
The paired bootstrap interval for the difference is **+0.05 [−0.04, +0.15]**, and the exact McNemar test (are 19
vs 26 more uneven than a fair coin?) gives **p = 0.37**. The difference is within what chance produces.

Then the repeated runs: on the 37 dev queries, v1's five runs range from 0.41 to 0.46 and v2's from 0.38 to 0.49.
Averaging five runs per query and comparing per-query means gives +0.02 [−0.14, +0.18] (exercise 4). Run-to-run
variance is as large as the effect we were hoping to see.

### Why pairing works

Query difficulty is the largest source of variation: some MediaDoctor questions are hard for any prompt. Running
both variants on the same queries cancels it, because each query is compared with itself. McNemar's test uses only
the discordant pairs; the paired bootstrap resamples queries and keeps each (v1, v2) pair together
(`stats.paired_bootstrap_diff(a, b)` gives both). With small discordant counts (fewer than about 10), trust the exact
McNemar p over the bootstrap interval, which comes out too narrow when there are very few disagreements.

## Step 5: per-failure-mode metrics, not one score

The aggregate said "maybe +5 points". The per-mode table says something more useful
(`mediadoctor-lab06 modes`; failure rates, lower is better, v2 minus v1 with paired intervals):

| Failure mode | v1 | v2 | v2 − v1 | p | Holm p |
|---|---|---|---|---|---|
| accepted-false-premise | 0.18 [0.12, 0.25] | 0.07 [0.03, 0.12] | −0.11 [−0.17, −0.05] | <0.001 | **0.005** |
| ignored-tool-output | 0.16 [0.11, 0.23] | 0.08 [0.05, 0.14] | −0.08 [−0.14, −0.02] | 0.019 | 0.115 |
| vague-next-step | 0.13 [0.08, 0.20] | 0.12 [0.08, 0.19] | −0.01 [−0.04, +0.03] | 1.000 | 1.000 |
| assumed-unstated-detail | 0.14 [0.09, 0.21] | 0.12 [0.07, 0.18] | −0.02 [−0.07, +0.02] | 0.508 | 1.000 |
| format-violation | 0.03 [0.01, 0.07] | 0.17 [0.11, 0.24] | +0.14 [+0.08, +0.20] | <0.001 | **<0.001** |
| wrong-api-detail | 0.07 [0.03, 0.12] | 0.04 [0.02, 0.08] | −0.03 [−0.06, −0.01] | 0.125 | 0.625 |

(Skipped-investigation and fabricated-evidence did not change: 4 of 137 each.)

v2 did what it was written for: accepted false premises fell from 18% to 7%. It also broke something: in 19
queries v2 opened its answer with a `Premise check:` line instead of `Likely cause:`, so the answer format
check fails, and no query went the other way. The aggregate blended a real fix and a real regression into "+5,
not significant". The decision is not "ship v2" or "keep v1"; it is "keep v2's premise check, and tell it to put the
correction inside `Likely cause:`", then rerun.

This is why the course reports one pass rate per failure mode. If someone needs a single number, use a pass-all
rate (a query passes only if it passes every check) and keep the per-mode table one click away; Hamel Husain and
Shreya Shankar recommend this in
[How do I combine my evals into a single metric?](https://hamel.dev/blog/posts/evals-faq/how-do-i-combine-my-evals-into-a-single-metric.html),
and they caution against elaborate weighted scores for the same reasons as against 1-to-5 scales.

## Step 6: multiple comparisons and slicing

Each test at α = 0.05 has a 5% chance of a false alarm. Test eight failure modes, or eight topic slices, and the
chance that at least one lights up by luck is far higher. In the per-mode table, ignored-tool-output has p = 0.019:
"significant" alone, but not after the **Holm-Bonferroni** adjustment for the eight modes tested (0.115).
(`stats.holm` takes a dict of p-values and returns adjusted ones; compare them with 0.05 as usual.)

Slices are worse, because they are small and there are many ways to cut. `mediadoctor-lab06 slices` splits the
v1-vs-v2 comparison by topic:

```text
codec-limits    n=19  v1 0.47  v2 0.21  diff -0.26 [-0.47, -0.05]  p=0.062  Holm p=0.500
live-stream     n=13  v1 0.15  v2 0.46  diff +0.31 [+0.08, +0.54]  p=0.125  Holm p=0.875
```

"v2 is much better on live streaming and much worse on codec limits" is a story the data cannot support. The
bootstrap intervals exclude zero, but with 13 and 19 queries and a handful of discordant pairs they are too narrow;
the exact tests give p above 0.05, and after adjusting for eight slices, p is 0.5 or more. Exercise 3 simulates the trap: with two
*identical* prompts and eight slices, about one experiment in eight shows at least one "significant" slice.

Rules: choose slices and failure modes before you look; adjust for the number you test; and treat a slice that
stands out after the fact as a hypothesis for the next, larger eval, not a finding.

## Step 7: repeated runs: pass@k and pass^k

With k runs per query there are two different questions, and two estimators:

- **pass@k**: the chance that *at least one* of k attempts passes. Useful when a person or a verifier picks the
  best attempt. Chen et al. gave the unbiased estimator 1 − C(n−c, k)/C(n, k) in
  [Evaluating Large Language Models Trained on Code](https://arxiv.org/abs/2107.03374).
- **pass^k** ("pass hat k"): the chance that *all* k attempts pass, C(c, k)/C(n, k). This is the reliability view
  for an agent: users who ask the same thing get a good answer every time. It was introduced with
  [τ-bench](https://arxiv.org/abs/2406.12045) (Yao et al.).

On the 37 dev queries (`mediadoctor-lab06 variance`):

| Prompt | pass^1 | pass^3 | pass^5 | pass@5 | flaky queries |
|---|---|---|---|---|---|
| v1 | 0.438 | 0.324 | 0.270 | 0.676 | 15 of 37 |
| v2 | 0.454 | 0.289 | 0.189 | 0.703 | 19 of 37 |

v2 is slightly ahead on a single run and clearly behind on consistency: its format slip happens in some runs and not
others, so more queries are flaky. For a support tool that engineers retry, pass^k is the number to watch.

## Step 8: vanity metrics

Some metrics are easy to compute and pleasant to watch, and tell you almost nothing.

**A generic 1-to-10 "helpfulness" score.** The lab replays such a judge on run 1 of both prompts. Mean helpfulness
is 7.71 for v1 and 7.66 for v2: flat, while two failure modes moved by more than 10 points each. Worse, it points
the wrong way. Answers that correctly ask for the missing file or device (PASS) average 4.89; answers that accepted a
false premise average 8.04, and answers contradicting the tool output 8.45. Confident, specific-sounding text
scores well whether or not it is true. The chance that a random passing answer outscores a random failing one is
0.42, worse than a coin.

**Off-the-shelf similarity.** Word-overlap F1 against a reference answer (the kind of score used in QA benchmarks)
does no better: 0.47. Trace m4q012 says both streams start at 0.000 s, the opposite of what ffprobe reported
(video starts at 0.300 s), and still scores 0.77, because it shares the reference's next step word for word.
Correct answers that ask for details or reject a premise use different words and score low.

Hamel Husain and Shreya Shankar make the same point in
[Should I use "ready-to-use" evaluation metrics?](https://hamel.dev/blog/posts/evals-faq/should-i-use-ready-to-use-evaluation-metrics.html)
and
[Are similarity metrics useful for evaluating LLM outputs?](https://hamel.dev/blog/posts/evals-faq/are-similarity-metrics-bertscore-rouge-etc-useful-for-evaluating-llm-outputs.html):
generic scores can help you find traces to read, but they are not quality measures. The test for any metric is the
one used here: does it separate passing from failing traces in your labels?

## Step 9: the metric report

`mediadoctor-lab06 report --out runs/m6_report.md` writes a one-page Markdown report. Every number in it follows
the rules of this module:

1. Every rate has its n and a 95% interval (Wilson for proportions, bootstrap otherwise).
2. Comparisons are paired (same queries), with an interval for the difference and an exact McNemar p.
3. Results are per failure mode, with p-values adjusted for the number of modes tested.
4. Reliability from repeated runs: run-to-run range, pass^k, and the number of flaky queries.
5. What the data can detect: the minimum detectable difference at this n, so nobody reads a 3-point move as news.
6. Judge-measured rates (module 5) would be corrected for judge error, with the interval that includes it. Here the
   per-mode outcomes are reference labels, so no correction is needed; in production they would come from the
   module 5 judges, and the report would carry the corrected rates.

Module 8 turns this report into a CI gate whose thresholds account for these intervals.

## Checklist

- [ ] Every pass rate printed with n and a Wilson (or bootstrap) interval.
- [ ] Comparisons run both variants on the same queries; reported with a paired interval and McNemar p.
- [ ] The minimum detectable difference is known before the comparison, and the eval set is sized for it.
- [ ] Repeated runs measure run-to-run variance; pass^k reported where consistency matters.
- [ ] Results per failure mode; a pass-all rate if a single number is required.
- [ ] Slices and modes chosen in advance; p-values adjusted (Holm) when testing several.
- [ ] Judge-measured rates corrected for judge error, with an interval that includes the judge's uncertainty.
- [ ] No generic helpfulness or similarity score used as a quality metric unless it separates your labels.
- [ ] Bootstraps seeded; the report is reproducible from replayed fixtures.

## Summary

An eval number has three kinds of noise: which queries you ran, which sample the model gave, and how the evaluator
judged it. Put a Wilson or bootstrap interval on every rate; size the eval set for the smallest change you care
about; compare variants on the same queries with a paired test; look per failure mode, because an aggregate can hide
a fix and a regression at once; adjust when you test many things; measure consistency with repeated runs; and keep
generic scores out of the dashboard unless they agree with your labels.

Next: [the lab](lab.md), then the [exercises](exercises.md) and [quiz](quiz.md). The
[stats cheat sheet](../../cheatsheets/stats.md) summarises the formulas.
