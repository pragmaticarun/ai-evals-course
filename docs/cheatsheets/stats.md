# Cheat sheet: statistics for eval metrics

All functions are in `evalkit.stats` (plain Python, seeded). PASS = True.

## Three sources of noise

| Source | Measure it with | Reduce it with |
|---|---|---|
| which queries | interval over queries | more queries; pairing |
| which run (model sampling, serving) | k repeated runs per query | report pass^k; more queries for comparisons |
| which verdict (judge error) | TPR / TNR on labels (module 5) | better judge; `bootstrap_corrected` |

## One rate

| Need | Use |
|---|---|
| interval for k / n | `wilson_interval(k, n)` (never Wald; 6/6 → [0.61, 1.00]) |
| interval for anything else | `bootstrap_ci(data, statistic, draws=2000, seed=...)`, resampling the unit you sampled |
| judge-measured rate | `bootstrap_corrected(labelled_pairs, verdicts)`; needs TPR + TNR > 1 |

`observed = θ·TPR + (1 − θ)(1 − TNR)`: a judge inflates low rates, deflates high ones, and shrinks differences by
`TPR + TNR − 1`.

## Two variants

Run both on the **same queries**.

```text
               B pass   B fail
   A pass        .      a_only
   A fail     b_only      .        McNemar uses only a_only and b_only
```

- `paired_bootstrap_diff(a, b)` → diff (B − A), 95% CI, discordant counts, exact McNemar p.
- Few discordant pairs (< ~10): trust the exact p, not the bootstrap interval.
- Overlapping per-variant intervals are **not** a test.

## How many queries

| Question | Function | Example |
|---|---|---|
| ±h on one rate | `n_for_halfwidth(p, h)` | p 0.8, ±0.05 → 246 |
| detect p₁ → p₂, separate queries | `n_two_proportions(p1, p2)` | 0.80 → 0.85 → 906 per variant |
| detect δ, same queries | `n_paired(discordant, δ)` | ψ 0.15, δ 0.05 → 469 |
| what can n detect? | `mdd_two_proportions(n, p)`, `mdd_paired(n, ψ)` | n 137: p 0.8 → 0.12; ψ 0.15 → 0.09 |

Defaults: α = 0.05 two-sided, power 0.8. n grows with 1/δ²: half the effect, four times the queries.

## Many tests

- Failure modes, slices, metrics: `holm({name: p})` → adjusted p; compare with 0.05.
- Pick slices before looking; a post-hoc slice is a hypothesis, not a finding.

## Repeated runs

| Metric | Meaning | Function |
|---|---|---|
| pass@k | at least one of k runs passes | `pass_at_k(n, c, k)` |
| pass^k | all k runs pass (reliability) | `pass_hat_k(n, c, k)` |
| flaky queries | pass in some runs, fail in others | `trial_summary(outcomes)` |

Temperature cannot remove run-to-run variance (and current Claude models accept only the default); measure it.

## What goes in a metric report

1. Every rate with n and a 95% interval.
2. Comparisons paired, with a diff interval and McNemar p.
3. Per failure mode, Holm-adjusted; a pass-all rate if one number is required.
4. Repeated-run reliability: range, pass^k, flaky count.
5. Minimum detectable difference at this n.
6. Judge-measured rates corrected, with the judge's uncertainty in the interval.

## Vanity metric test

Does the metric separate passing from failing traces in your labels? Chance that a random PASS outscores a random
FAIL: 0.5 = useless. In the lab: helpfulness 1-10 → 0.42; word-overlap F1 → 0.47.

## Repeated looks and small slices

- Checking a running experiment until p < 0.05 is many tests: fix n and look once, or use always-valid
  (sequential) intervals. CUSUM is the monitoring version.
- Ranking many small slices: shrink toward the overall rate (beta-binomial prior worth a few queries); still a
  hypothesis, not a finding.

## Commands

```bash
uv run mediadoctor-lab06 runs | variance | compare [--mode M] | modes | slices | samples | vanity | judges
uv run mediadoctor-lab06 show m4q031
uv run mediadoctor-lab06 report --out runs/m6_report.md
```
