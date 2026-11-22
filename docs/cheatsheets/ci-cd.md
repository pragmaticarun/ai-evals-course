# Cheat sheet: CI/CD for evals

CI is fast, deterministic, and free; live runs are a separate, deliberate job. Module 8; code in `evalkit.gate`,
`evalkit.golden`, `evalkit.hygiene`, `mediadoctor.lab08`, `evals/`, and `.github/workflows/eval-gate.yml`.

## Tiers

| Tier | When | Evaluators | Blocks merge |
|---|---|---|---|
| Fast (`pytest evals -m "not judges"`) | every PR and push | code checks, manifest, hygiene, replay coverage, baseline | yes |
| Judges (`pytest evals -m judges`) | nightly, by hand, or the `run-judges` label | validated LLM judges | on a significant regression; warns are information |
| Must-pass cases | with the fast tier | exact assertions on past incidents | any failure |
| Live re-record | by hand (`live-evals`), with a budget | the model itself | never: its output is reviewed and committed |

## The gate rule (per metric, paired on the same cases)

| Status | When |
|---|---|
| fail | worse, Holm-adjusted McNemar p < alpha, and the drop ≥ `min_effect` |
| warn | not shown worse, but the 95% paired interval goes below `-margin` |
| pass | otherwise |

- No fixed thresholds: their false-alarm rate depends on n and noise. Alpha controls the gate's; n controls its power.
- Size n with `n_paired(discordant, diff)`; read what n can see with `mdd_paired(n, discordant)` (module 6).
- A warn means "cannot rule out a drop you care about": add cases or read the flips; do not widen the margin.
- A judge's errors shrink differences: gate on code checks, inform with judges, until the judge is good enough.

## Golden data and baselines

- Manifest: version + SHA-256 of every file the numbers depend on (dataset, labels, judge specs, fixtures, answer
  digests, hygiene review) + a digest of each split's ids. CI fails on any difference.
- Version: major = new cases or splits; minor = relabels or re-recorded runs; patch = no outcome changes.
- Baseline: a saved run of the release config (per-case outcomes per metric + config fingerprint).
  Read it from the **base branch**; each PR commits its own new baseline.

## Record and replay

| Change | Replay misses | Then |
|---|---|---|
| prompt, model ID, tool definitions, max_tokens | every agent request (preflight finds them) | re-record, read flips, relabel, bump |
| a tool result (KB edit, probe cache) | later turns of affected cases (full replay finds them) | as above |
| judge spec | every judge request | re-record judges, re-validate the judge |
| labels | none | bump the manifest; re-read numbers |
| nothing, but time passed | none | re-record a sample monthly to detect drift |

Never re-record to make CI green. Gate exit codes: 0 pass or warn, 1 blocked, 3 replay misses.

## The comparison report

Headline · what was compared (prompts, fingerprints, baseline source, golden version) · per-tier table (n, rates,
paired diff + CI, flips −/+, adjusted p, status) · flips to read first · cost and time vs budget · the rule.
Write it to `$GITHUB_STEP_SUMMARY`, upload it and the run JSON as an artifact.

## Hygiene

| Check | Finds | Fix |
|---|---|---|
| cross-split similarity | near-duplicates across gate and held-out | group similar cases into one split (module 4) |
| judge examples | few-shot examples outside train | take examples from train only |
| n-gram contamination (8 words, prose only) | eval text in prompts, judge examples, KB | replace the source text, move the case, or record a reviewed decision |
| stale labels | labelled answers that changed | relabel, then bump the manifest |

## Overfitting

- Every PR tunes on the gate set: keep a held-out split that no tier and no tuning script reads (`HoldoutGuard`).
- Look at it for release decisions only; log each look; rotate after N looks or each quarter (`golden.rotate`).
- Alarm: gate numbers rising while held-out numbers stay flat.

## Budgets and workflow hygiene

- Budgets: replay seconds per job, live cost and wall time per re-record (`config/eval_gate.toml`).
- `timeout-minutes`, a concurrency group per branch and tier with `cancel-in-progress`, dependency caching.
- `permissions: contents: read`; event values via `env:`; `EVALS_LLM_MODE: replay`; the API key only in the live job.
- The gate report runs with `if: always()`, so a failing test still produces the summary and artifact.
