# Cheat sheet: production monitoring and annotation

Free checks on everything, judges on a sample, people on a weighted queue. Module 9; code in `evalkit.monitor`,
`evalkit.annotate` (`cohen_kappa`, `kappa_report`), `mediadoctor.lab09`, and the app in `labs/annotate`.

## Who evaluates what in production

| Evaluator | Coverage | Report as |
|---|---|---|
| Code checks (format, real citations, investigated, known-mode detectors) | all traffic | rates, p-chart, CUSUM |
| Validated LLM judge | random sample at a stated rate | raw rate for change; corrected rate with an interval for level |
| People (annotation queue) | triggered + random + stratified picks | labels; rates weighted by 1/p |
| User feedback (thumbs, retries, copies) | whoever bothers | a pointer to traces, never the metric |

## Sampling

| Method | Finds | Misses | Use for estimates? |
|---|---|---|---|
| Random (hash of the id, `random_sample`) | anything, at its natural rate | rare cases at small n | yes |
| Stratified (`stratified_sample`, k per topic) | rare strata | nothing in particular | yes, weighted |
| Signal-triggered (check, thumbs-down, tool error, retry, slow) | failures with a symptom | silent failures | only weighted |
| Judge-triggered or judge-disagreement | judge errors, likely failures | what the judge cannot see | only weighted |

- Deterministic: decide inclusion from a hash of the request id, so reruns pick the same traces.
- Fold identical traces (same fingerprint) and keep the count.
- Interleave: about one random or stratified pick for every two triggered ones.
- Record each pick's inclusion probability; estimate with `weighted_rate` (Hajek: Σ y/p ÷ Σ 1/p).

## Drift

| Kind | Watch | Alert |
|---|---|---|
| Input | topic shares (tagger), new device or category names | PSI > 0.1 look, > 0.25 act; any new category |
| Output and metric | check failure rates, judge rate | p-chart (3σ around the reference rate, per-day n); Bernoulli CUSUM |
| System | model snapshot, prompt, tool versions on every trace | before/after two-proportion test; re-run the offline gate |

- PSI = Σ (a − e) · ln(a / e) over categories, with a small floor for empty ones.
- Bernoulli CUSUM: S = max(0, S + x·ln(p1/p0) + (1 − x)·ln((1 − p1)/(1 − p0))); alarm when S > h.
  Start with p1 = 2·p0, h = 4 to 5.
- Choose h by replaying: false alarms per normal week against delay on a known change. Re-tune when volume changes.
- Validate the topic tagger on questions it was not written on.
- Split every metric by app version, device, and model snapshot: segments find causes.

## Feedback biases

| Signal | Bias |
|---|---|
| Thumbs-down | sparse, from a few users; punishes visible annoyance (slowness), misses confident errors |
| Thumbs-up | rewards confident tone; weak evidence of correctness |
| Retry | a good failure pointer; also fires on impatience |
| Copy | ambiguous (useful, or pasted into a bug report) |
| Slow | weakly related to quality; worth watching on its own |

## Annotation app

```bash
uv run mediadoctor-lab09 annotate                    # the lab: store + queue + dashboard, then the app
uv run annotate serve --traces T.jsonl --modes M.toml --out DIR \
    [--queue Q.jsonl] [--dashboard D.json] [--compare NAME=labels.csv] [--port 8009]
uv run annotate kappa A.csv B.csv                    # Cohen's kappa between two label files
```

| Key | Action | Key | Action |
|---|---|---|---|
| `p` / `f` | pass / fail | `g` | golden candidate |
| `1`-`9` | toggle a mode | Enter, `s` | save and next |
| `m` | new mode | `j` / `k` | next / previous |
| `n` | note | `t` / `c` | tool outputs / raw attributes |
| `?` | help | Escape | leave a text box |

Exports: `/export/labels.csv`, `/export/taxonomy.csv`, `/export/golden.jsonl`, `/export/golden-flags.json`; pages
`/agreement` and `/dashboard`. Localhost only, no login, no secrets: add authentication and a privacy review before
sharing it.

## Agreement

- κ = (p_o − p_e) / (1 − p_e); report it per mode with the counts.
- Rare modes: high agreement can give low kappa (p_e near 1). Read the disputed traces and fix the definition.
- Have annotators label independently first, then discuss the disagreements and update the rubric.

## Closing the loop

1. New mode named in review, defined in the taxonomy (version it: labels v2).
2. A code check or judge for it, validated on labelled traces, then run on traffic.
3. Golden candidates: failing or flagged traces, one per distinct question, stable proposed split, near-duplicates
   flagged.
4. Human review, then into `data/golden/` with a manifest version bump; re-validate affected judges.

## Also

- Discover unnamed topics: summarise and embed questions, cluster, read the newest and fastest-growing clusters.
- Online A/B tests for changes that passed the offline gate: randomise by user, pre-register, no early stopping.
- Weighted queue rates get an interval too (`monitor.weighted_rate_ci`).

## Lab commands

```bash
uv run mediadoctor-lab09 simulate | monitor [--json F] | signals | tagger | judge | sample [--limit N]
uv run mediadoctor-lab09 agreement A.csv B.csv | score LABELS.csv
uv run mediadoctor-lab09 close-loop LABELS.csv [--flagged golden-NAME.json] [--out F]
```
