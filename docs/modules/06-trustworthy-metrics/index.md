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

**Run-to-run variance is real even when nothing changed.** In the lab, prompt v2 was run 5 times on the same 30
dev queries. Its pass rate came out 0.97, 1.00, 0.97, 0.87, and 0.97. Compare run 2 with run 4 as if they were two
prompts and you get −13 points with a paired bootstrap interval of [−0.27, −0.03]: an apparent regression between
two runs of the *same* prompt, which the exact McNemar test (4 discordant queries against 0, p = 0.125) rightly
does not call significant. 6 of the 30 queries passed in some runs and failed in others.

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
| 144 / 147 | 0.98 | [0.94, 0.99] |
| 49 / 60 | 0.82 | [0.70, 0.89] |

For anything that is not a simple proportion (a difference, a mean score, a corrected rate, a ratio), use the
**percentile bootstrap** (`stats.bootstrap_ci(data, statistic)`): resample the queries with replacement a few
thousand times, recompute the statistic, and take the middle 95%. Two rules:

- **Resample the unit you sampled.** If each query was run five times, resample queries and keep their five runs
  together; resampling individual runs pretends you have five times as many independent queries. The same holds
  for multi-turn sessions or several questions about one file. Evan Miller's
  [Adding Error Bars to Evals](https://arxiv.org/abs/2411.00640) covers this clustering effect.
- **Seed it.** `bootstrap_ci` takes a seed, so the report does not change between runs of the report.

The module 5 judge numbers, with their intervals, show why this matters (lab section 5):

| Judge | Split | TPR | TNR |
|---|---|---|---|
| tool-grounding v2 | dev | 1.00 [0.89, 1.00] (n=30) | none (n=0) |
| tool-grounding v2 | test | 1.00 [0.88, 1.00] (n=28) | none (n=0) |
| false-premise v1 | test | 1.00 [0.88, 1.00] (n=28) | none (n=0) |
| next-step v1 | test | 1.00 [0.88, 1.00] (n=28) | none (n=0) |

A perfect TPR still has an interval: 28 of 28 is consistent with a true TPR as low as 0.88. And the labelled
splits contain no failures at all, so the TNR, the judge's ability to catch a bad answer, has not been measured.
That is the honest reading of module 5 on this data: the judges have never been shown a failure, so nothing says
they would catch one, and a judge-error correction (which needs the TNR) cannot be computed. With rare failures you
have to go looking for them (module 4's hypotheses, or sampling the traces a cheap check flags) before you can
validate a judge. The judge-error correction and its bootstrap now live in `evalkit.stats` (`corrected_pass_rate`,
`bootstrap_corrected`); `evalkit.judge` re-exports them, so module 5 code is unchanged.

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
detectable difference. The lab's numbers make the point at the extreme: 147 queries, v1's pass rate of 0.98, and a
discordant share of 0.04 (6 queries). Unpaired, no improvement over 0.98 is detectable (there are only 2 points of
headroom); paired, a difference can be at most the discordant share, and even 4 points would need about 190 shared
queries, so `mdd_paired` returns nan. This set cannot show that one prompt beats the other, however the numbers
look. It can still catch a regression: a 5-point drop from 0.98 needs 269 queries per variant unpaired.

Two consequences worth remembering. The n you need grows with 1/δ²: halving the change you want to see needs four
times the queries. And rates near 0 or 1 are cheaper: 95% → 99% needs 285 per variant, because there is less
binomial noise there.

## Step 4: compare two prompts on the same queries

The lab compares agent prompt v1 with v2, which adds an instruction to check the user's claims before building
on them (aimed at accepted-false-premise failures). Both ran once on the same 147 labelled queries.

### Worked example

Looked at as two separate rates, the prompts tie: 0.98 [0.94, 0.99] for both, 144 of 147. Identical rates do not
mean identical behaviour, and two rates side by side ignore that the queries are shared.

Pair them. On 147 queries, 3 pass under v1 only and 3 under v2 only; the other 141 behave the same under both.
The paired bootstrap interval for the difference is **+0.00 [−0.03, +0.03]**, and the exact McNemar test (are 3
vs 3 more uneven than a fair coin?) gives **p = 1.00**. The prompts fail on different queries, but there is no
evidence that either is better.

Then the repeated runs: on the 30 dev queries, both prompts' five runs range from 0.87 to 1.00. Averaging five
runs per query and comparing per-query means gives −0.01 [−0.03, +0.00] (exercise 4). Run-to-run variance (13
points between runs of one prompt) is larger than any difference between the prompts.

### Why pairing works

Query difficulty is the largest source of variation: some MediaDoctor questions are hard for any prompt. Running
both variants on the same queries cancels it, because each query is compared with itself. McNemar's test uses only
the discordant pairs; the paired bootstrap resamples queries and keeps each (v1, v2) pair together
(`stats.paired_bootstrap_diff(a, b)` gives both). With small discordant counts (fewer than about 10), trust the exact
McNemar p over the bootstrap interval, which comes out too narrow when there are very few disagreements.

## Step 5: per-failure-mode metrics, not one score

An aggregate can blend a fix in one failure mode and a regression in another into "no change", so look per mode
(`mediadoctor-lab06 modes`; failure rates, lower is better, v2 minus v1 with paired intervals). The table lists
only the modes that at least one prompt failed:

| Failure mode | v1 | v2 | v2 − v1 | p | Holm p |
|---|---|---|---|---|---|
| assumed-unstated-detail | 0.01 [0.00, 0.04] | 0.01 [0.00, 0.04] | −0.00 [−0.02, +0.02] | 1.000 | 1.000 |
| fabricated-evidence | 0.01 [0.00, 0.04] | 0.01 [0.00, 0.05] | +0.01 [−0.01, +0.03] | 1.000 | 1.000 |

On this data the per-mode view finds no hidden fix or regression either. The six failing answers spread over
four labels: v1 has one assumed-unstated-detail, one fabricated-evidence, and one redundant-steps; v2 has one
assumed-unstated-detail and two fabricated-evidence (one also labelled retrieval-miss). Redundant-steps and
retrieval-miss count against the overall pass rate but are not among the eight modes the table tests. The mode v2
was written for, accepted-false-premise, never occurred under either prompt, so the data cannot say whether v2's
premise check works. The decision is "no detectable difference"; to learn more you need queries on which v1
actually accepts false premises (module 4's method), not a cleverer statistic.

On data with more failures the same table earns its place. If v2 had cut false premises by 10 points while a
side effect broke the answer format on as many queries, the aggregate would read "about zero, not significant"
while two rows of this table showed a significant fix and a significant regression, and the right decision would be
"keep the fix, repair the regression, rerun", which no single score can tell you.

This is why the course reports one pass rate per failure mode. If someone needs a single number, use a pass-all
rate (a query passes only if it passes every check) and keep the per-mode table one click away; Hamel Husain and
Shreya Shankar recommend this in
[How do I combine my evals into a single metric?](https://hamel.dev/blog/posts/evals-faq/how-do-i-combine-my-evals-into-a-single-metric.html),
and they caution against elaborate weighted scores for the same reasons as against 1-to-5 scales.

## Step 6: multiple comparisons and slicing

Each test at α = 0.05 has a 5% chance of a false alarm. Test eight failure modes, or eight topic slices, and the
chance that at least one lights up by luck is far higher. The **Holm-Bonferroni** adjustment fixes that: sort the
p-values, multiply the smallest by the number of tests, the next by one fewer, and so on. A mode with p = 0.019
among eight tested would be "significant" alone but not after adjustment (0.019 × 8 = 0.15).
(`stats.holm` takes a dict of p-values and returns adjusted ones; compare them with 0.05 as usual.) On the lab's
data no p-value is below 0.05 even before adjustment.

Slices are worse, because they are small and there are many ways to cut. `mediadoctor-lab06 slices` splits the
v1-vs-v2 comparison by topic:

```text
av1-playback    n=21  v1 0.90  v2 1.00  diff +0.10 [+0.00, +0.24]  p=0.500  Holm p=1.000
drm-resolution  n=17  v1 1.00  v2 0.94  diff -0.06 [-0.18, +0.00]  p=1.000  Holm p=1.000
```

"v2 fixes AV1 playback and breaks DRM" is a story the data cannot support. The av1-playback difference is two
queries (v1 fails two, v2 none); drm-resolution's is one. The bootstrap intervals touch zero, and with so few
discordant pairs they are too narrow anyway; the exact tests give p = 0.5 and 1.0, and after adjusting for eight
slices, 1.0. Exercise 3 simulates the trap: with two
*identical* prompts and eight slices, about one experiment in eight shows at least one "significant" slice.

Rules: choose slices and failure modes before you look; adjust for the number you test; and treat a slice that
stands out after the fact as a hypothesis for the next, larger eval, not a finding.

**Looking more than once is a comparison too.** Checking a running experiment every day and stopping when p dips
below 0.05 inflates the false-alarm rate the same way slicing does, because each look is another test. Either fix
n in advance (Step 3) and look once, or use a method built for repeated looks: alpha spending, or *always-valid*
intervals that stay correct however often you check (Johari et al.,
[Always Valid Inference](https://arxiv.org/abs/1512.04922)). Module 9's CUSUM is the monitoring-side version of the
same idea: its threshold `h` is set for a stream you watch continuously.

**Small slices: shrink toward the whole.** A 6-query slice at 6/6 is not evidence of perfection; its Wilson
interval is [0.61, 1.00]. When you must rank many small slices, a simple Bayesian fix helps: give each slice a
beta prior centred on the overall rate, worth a few queries (a beta-binomial model), so small slices are pulled toward
the average and large ones barely move. It ranks slices more sensibly than raw rates, but it is still not a
substitute for a pre-registered comparison with enough queries.

## Step 7: repeated runs: pass@k and pass^k

With k runs per query there are two different questions, and two estimators:

- **pass@k**: the chance that *at least one* of k attempts passes. Useful when a person or a verifier picks the
  best attempt. Chen et al. gave the unbiased estimator 1 − C(n−c, k)/C(n, k) in
  [Evaluating Large Language Models Trained on Code](https://arxiv.org/abs/2107.03374).
- **pass^k** ("pass hat k"): the chance that *all* k attempts pass, C(c, k)/C(n, k). This is the reliability view
  for an agent: users who ask the same thing get a good answer every time. It was introduced with
  [τ-bench](https://arxiv.org/abs/2406.12045) (Yao et al.).

On the 30 dev queries (`mediadoctor-lab06 variance`):

| Prompt | pass^1 | pass^3 | pass^5 | pass@5 | flaky queries |
|---|---|---|---|---|---|
| v1 | 0.967 | 0.900 | 0.833 | 1.000 | 5 of 30 |
| v2 | 0.953 | 0.870 | 0.800 | 1.000 | 6 of 30 |

Every query passes at least once in five runs (pass@5 is 1.000), and no query always fails. But a 0.97 single-run
rate becomes 0.83 when you ask for five good answers in a row: one query in six fails at least once. The two
prompts differ by one flaky query, well within noise. For a support tool that engineers retry, pass^k is the number
to watch, and it is where rare failures show up first.

## Step 8: vanity metrics

Some metrics are easy to compute and pleasant to watch, and tell you almost nothing.

**A generic 1-to-10 "helpfulness" score.** The lab replays such a judge on run 1 of both prompts. Mean helpfulness
is 7.14 for v1 and 7.16 for v2, and 115 of v1's 147 answers score 7 or 8: the score barely varies. Does it at least
rank failing answers low? The chance that a random passing answer outscores a random failing one is 0.22 on v1
(its three failing answers all score 8, above the passing mean of 7.12) and 0.81 on v2 (its failing answers score
6, 6, and 7). The same judge looks worse than a coin on one prompt and useful on the other, because each number
rests on three failing answers. That is the real lesson of this data: you cannot validate a metric against labels
that contain three failures.

**Off-the-shelf similarity.** Word-overlap F1 against a reference answer (the kind of score used in QA benchmarks)
gives 0.28 on v1: its three failing answers score 0.39 to 0.46, and 82 of the 144 passing answers score below all
of them. Word overlap measures how an answer is worded, not whether it is right.

On data with more failures the same check is decisive. A generic judge tends to reward confident, specific-sounding
text whether or not it is true, and word overlap rewards an answer that copies the reference's wording while
getting a fact backwards; with dozens of labelled failures, a separation near or below 0.5 would show it.

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
