# Lab 6: Honest numbers for MediaDoctor (offline)

**Time:** about 3 hours. **Needs:** the setup from [lab 1](../01-why-evals/lab.md), and module 5.
**Does not need:** an API key or network access.

You will use `evalkit.stats` to put intervals on MediaDoctor's numbers, measure run-to-run variance from repeated
runs, compare agent prompt v1 with v2 on the same queries, work out what the eval set can and cannot detect, test
two vanity metrics against the labels, and write a metric report. Keep your own files under `runs/`, which git
ignores.

!!! info "Synthetic-authored fixtures"
    Run 1 of prompt v1 is module 5's run. The other nine runs (prompt v2, and repeats 2 to 5 of both prompts), their
    reference labels, the reference answers, and the helpfulness judge's scores were written for the course and
    recorded through the real code paths (`scripts/author_module06_fixtures.py`). Every record is labelled
    `"source": "synthetic-authored"`. Section 11 shows how to record real runs.

## 1. Update and check

```bash
git pull
uv sync
uv run pytest -q tests/test_stats.py tests/test_lab06.py
```

## 2. A tour of `evalkit.stats`

Open `labs/evalkit/src/evalkit/stats.py`; it is plain Python, under 400 lines with docstrings. Then try it:

```python
from evalkit import stats

print(stats.wilson_interval(49, 60))  # (0.70..., 0.89...)
print(stats.n_two_proportions(0.80, 0.85))  # 906 per variant
print(stats.mcnemar_exact(19, 26))  # 0.37...
print(stats.pass_hat_k(5, 3, 2))  # 0.3: both of 2 runs pass, given 3 of 5 passed
```

Read `tests/test_stats.py` too: each function is checked against a hand calculation, and the Wilson interval
against simulated coverage (about 95% of intervals contain the true rate).

## 3. The runs

```bash
uv run mediadoctor-lab06 runs
```

```text
v1 run 1: 137 queries, pass  52  0.38 [0.30, 0.46]
v1 run 2:  37 queries, pass  17  0.46 [0.31, 0.62]
...
v2 run 1: 137 queries, pass  59  0.43 [0.35, 0.51]
...
v2 run 5:  37 queries, pass  14  0.38 [0.24, 0.54]
```

Run 1 of each prompt covers the 137 labelled queries from module 5. Runs 2 to 5 repeat the 37 dev queries. The
pass rates are low because the set was built from failure hypotheses (module 4); it is a stress test, not a sample
of production traffic. Each run's outcome per failure mode comes from `data/labels/module06_runs.csv`.

Look at the v2 prompt in `labs/mediadoctor/src/mediadoctor/toolagent.py` (`SYSTEM_AGENT_V2`): one paragraph telling
the agent to check the user's claims.

## 4. Run-to-run variance

```bash
uv run mediadoctor-lab06 variance
```

```text
v1: 37 cases x 5 runs: run pass rates 0.405, 0.459, 0.432, 0.432, 0.459 (mean 0.438, sd 0.020); always pass 10, never pass 12, flaky 15
    k=1: pass@k 0.438  pass^k 0.438
    k=3: pass@k 0.576  pass^k 0.324
    k=5: pass@k 0.676  pass^k 0.270
v2: 37 cases x 5 runs: run pass rates 0.459, 0.486, 0.486, 0.459, 0.378 (mean 0.454, sd 0.040); always pass 7, never pass 11, flaky 19
    k=1: pass@k 0.454  pass^k 0.454
    k=3: pass@k 0.614  pass^k 0.289
    k=5: pass@k 0.703  pass^k 0.189
```

Then look at one flaky query across all ten runs:

```bash
uv run mediadoctor-lab06 show m4q031
```

v1 corrects the false premise in all five runs. v2 corrects it too, but in runs 2 to 5 it writes the correction as
`Premise check:` instead of `Likely cause:`, and the format check fails. The model's answer is a sample, so a
query's outcome is a probability, not a fact. Try `show m4q065` (v1 never passes, v2 passes 4 times out of 5).

## 5. Intervals on module 5's numbers

```bash
uv run mediadoctor-lab06 judges
```

```text
tool-grounding  test  TPR 0.90 [0.70, 0.97] (n=20)  TNR 0.60 [0.23, 0.88] (n=5)
false-premise   test  TPR 0.96 [0.80, 0.99] (n=24)  TNR 0.60 [0.23, 0.88] (n=5)
next-step       test  TPR 0.92 [0.75, 0.98] (n=25)  TNR 1.00 [0.51, 1.00] (n=4)
tool-grounding corrected estimate: observed pass rate 0.820 on 89 unlabelled traces; corrected 0.840, 95% CI [0.236, 1.000] ...
```

Write down, for one judge, how many more labelled *failures* would bring its TNR interval to ±0.10 (use
`stats.n_for_halfwidth`). The corrected estimate is the same as module 5's: the correction moved from
`evalkit.judge` to `evalkit.stats` unchanged, and `evalkit.judge` re-exports it.

## 6. Compare the prompts, paired

```bash
uv run mediadoctor-lab06 compare
uv run mediadoctor-lab06 compare --mode accepted-false-premise
```

```text
v1: 0.38 [0.30, 0.46]   v2: 0.43 [0.35, 0.51]   (Wilson)
paired (v2 - v1): n=137  A 0.380  B 0.431  diff +0.051 95% CI [-0.044, +0.146]  discordant: only A 19, only B 26  McNemar p=0.371

v1: 0.82 [0.75, 0.88]   v2: 0.93 [0.88, 0.97]   (Wilson)
paired (v2 - v1): n=137  A 0.825  B 0.934  diff +0.109 95% CI [+0.051, +0.168]  discordant: only A 2, only B 17  McNemar p=0.001
```

(With `--mode`, "pass" means "free of that failure mode".) Overall, the difference is within noise. For the failure
mode v2 was written to fix, it is not: 17 queries improved and 2 got worse.

## 7. The per-failure-mode table

```bash
uv run mediadoctor-lab06 modes
```

Compare with the table in the lesson. Note which rows are significant before and after the Holm adjustment, and
which change the aggregate hid. Write one sentence per significant row saying what you would do about it.

## 8. Slices

```bash
uv run mediadoctor-lab06 slices
```

Find the two topics with the largest differences. Before reading the Holm column, write down whether you believe
them. Then read it, and do exercise 3.

## 9. Sample sizes

```bash
uv run mediadoctor-lab06 samples
```

```text
v1 pass rate 0.38 on 137 queries; v1/v2 discordant share 0.33
queries for a +/-5-point interval on one rate: 362
to detect 0.38 -> 0.43 (80% power, alpha 0.05): 1512 per prompt on separate queries, 1029 shared queries if paired
smallest detectable change with 137 queries: 0.168 unpaired, 0.136 paired
```

A 5-point overall change needs about 1,000 shared queries at this discordant share. Per failure mode the picture is
better, because the changes are larger and most queries agree: the false-premise change (11 points, 19 discordant
queries) was detectable with 137.

## 10. Vanity metrics

```bash
uv run mediadoctor-lab06 vanity
```

```text
v1 helpfulness: mean 7.71 [7.46, 7.96]; passing answers 7.23, failing answers 8.00; separation (AUC) 0.42
v2 helpfulness: mean 7.66 [7.41, 7.92]; passing answers 7.12, failing answers 8.08; separation (AUC) 0.37
v1 token F1 vs reference answer: passing 0.69, failing 0.78; separation (AUC) 0.47
```

Separation is the chance that a random passing answer scores above a random failing one: 0.5 is a coin, 1.0 is
perfect. Both metrics are at or below a coin. Exercise 5 looks at why.

## 11. The metric report

```bash
uv run mediadoctor-lab06 report --out runs/m6_report.md
```

Open `runs/m6_report.md` (it renders on GitHub or in any Markdown viewer). It has the overall pass rates, the
per-mode table with Holm-adjusted p-values, reliability from repeated runs, and the minimum detectable difference.
Add a short "Decision" section at the top in your own words.

## 12. Optional: record real repeated runs

With an API key, `run_traces` records any run you ask for; trial numbers keep repeats apart:

```bash
EVALS_LLM_MODE=record uv run python -c "
from mediadoctor import lab06
for run in (2, 3):
    lab06.run_traces('v2', run)
"
```

Each agent run makes two to four Claude calls of a few thousand input tokens; 37 queries times two runs is roughly
150 Sonnet calls, a dollar or two at the prices in `config/models.toml`. Recording overwrites the synthetic records
for those runs; `git checkout fixtures/` restores them. Real runs need labels: run the module 5 judges on them, correct their
pass rates, and compare the run-to-run spread with the synthetic one.

## Checkpoint

- [ ] `uv run pytest -q tests/test_stats.py tests/test_lab06.py` passes
- [ ] A note on run-to-run variance: the spread of v2's five runs and which queries are flaky
- [ ] The paired comparison overall and for the failure mode v2 targeted, with your reading of each
- [ ] The number of queries you would need to detect a 5-point overall change, paired and unpaired
- [ ] `runs/m6_report.md` with your decision section
