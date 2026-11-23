# Cheat sheet: evaluators and judge validation

## Choose the evaluator

```text
failure mode ──► can a program decide it from the trace? ── yes ──► CODE CHECK (validate once against labels)
                         │
                         no (needs meaning)
                         ▼
                 LLM JUDGE: one mode, binary, critique first, cheap judge model
                         ▼
                 validate: TPR/TNR on dev ─► iterate ─► test ONCE ─► corrected rate + CI
```

## A judge spec

| Part | Rule |
|---|---|
| criterion | one sentence, one failure mode, phrased as what PASS looks like |
| PASS / FAIL | precise; write down every borderline case you have decided |
| context | only what the criterion needs (question / tools / answer) |
| examples | 2 to 4, train split only, at least one FAIL and one tricky PASS, each with a critique |
| output | JSON with `critique` and `verdict` (PASS or FAIL); count unparseable outputs, never guess |
| model | the `judge` role in `config/models.toml`, pinned; revalidate when it changes |

## Metrics (PASS = positive)

| | judge PASS | judge FAIL |
|---|---|---|
| human PASS | TP | FN |
| human FAIL | FP | TN |

- **TPR** = TP / (TP + FN): good answers the judge passes.
- **TNR** = TN / (TN + FP): bad answers the judge catches. Usually the one that matters, and the noisiest.
- Report both with counts. Agreement alone hides a judge that passes everything.
- Aim for at least 50 human passes and 50 human failures per judge before trusting a number.

## Correction

```text
observed = θ·TPR + (1 − θ)·(1 − TNR)
θ        = (observed + TNR − 1) / (TPR + TNR − 1)      needs TPR + TNR > 1; clip to [0, 1]
```

Bootstrap: resample the labelled test pairs **and** the judged traffic; percentile interval of the corrected θ.

## The splits

| Split | Judge work |
|---|---|
| train | few-shot examples; read freely |
| dev | run every change; read every disagreement |
| test | run once at the end; report; a later change needs new test labels |

## Alignment session (each disagreement)

1. Judge wrong → fix the definition, add an example, change the context.
2. Label wrong → fix the label, log it.
3. Criterion unclear → the domain expert decides; write it into PASS/FAIL; relabel what it affects.

## Pitfalls

| Pitfall | Defence |
|---|---|
| leakage (dev/test examples, expected answer in prompt) | train-only examples; `leakage_problems`; production-equivalent context |
| 1–5 scales | binary verdicts; several binary criteria for gradual progress |
| position bias | single-answer judges; both orders for comparisons |
| verbosity bias | claim-specific criteria; long-but-wrong FAIL examples |
| self-preference | human validation; different model family for key judges |
| criteria drift | expect it; version specs and labels together |
| overfitting dev | few dev failures fit easily; confirm on test once |

## Newer patterns

- **PPI++** (`stats.ppi_mean`): label a random sample of the traffic you measure; correct the judge's mean by the
  human-minus-judge gap. Never worse than the labels alone; much narrower than Rogan-Gladen with few failures.
- **Panel of judges** from different model families, majority vote; validate the vote, read split votes.
- **Rubrics**: per-case binary criteria for long answers; validate per criterion; no rolled-up score.
- **Thinking judge** or **agent-as-a-judge** (with tools): new judge versions; re-validate, need more labels.

## Commands

```bash
uv run mediadoctor-lab05 ppi [--labels 50]           # human labels vs Rogan-Gladen vs PPI / PPI++
uv run mediadoctor-lab05 checks
uv run mediadoctor-lab05 show tool-grounding
uv run mediadoctor-lab05 leaks
uv run mediadoctor-lab05 disagreements tool-grounding --version v1 --split dev
uv run mediadoctor-lab05 validate --split dev
uv run mediadoctor-lab05 validate --split test      # once
uv run mediadoctor-lab05 estimate
```
