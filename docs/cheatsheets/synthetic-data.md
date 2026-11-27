# Cheat sheet: synthetic data

## The pipeline

```text
failure hypotheses ──► DIMENSIONS (3-6 values each) + RULES (with reasons)
                                │
                                ▼
                    TUPLES   pairwise first (all value pairs), then stratified fill
                                │
                                ▼
                    QUERIES  one tuple per call, cheap model, concrete artefacts, real style examples
                                │                              (Message Batches: half price)
                                ▼
                    CHECKS   query matches tuple · near-dup (within same test case) · diversity · coverage
                                │
                                ▼
                    FREEZE   v1 + manifest (counts, thresholds, sha256) · grouped train/dev/test · 0 leaks
                                │
                                ▼
                    RUN & READ  agent on dev → traces → error analysis → failure rate by dimension
```

## Tuple strategies

| Strategy | Use when | Watch out |
|---|---|---|
| Full product | the valid space is small (under a few hundred) | grows multiplicatively with each dimension |
| Uniform sample | never on its own | small slices get almost nothing; gaps move with the seed |
| Stratified by one dimension | you need counts per value (rates per topic) | other dimensions are still left to chance |
| Pairwise (all-pairs) | always, as the base | one example per pair; no 3-way combinations |
| Seeded pairwise | real queries exist | `start=real_tuples`; generate only the gaps |

## Writing realistic queries

- Give the writer the tuple **and** concrete artefacts chosen by code: file, device, log lines, the false premise.
- Instructions by expertise: experts name APIs; novices describe symptoms, lower case, typos.
- Ban the tells: "I'm experiencing", "Could you please", "best practices", perfect grammar, lists of questions.
- Real formats: bug-ticket templates, forwarded customer messages, raw logcat pastes.
- `missing-detail`: refer vaguely ("our trailer", "a customer's phone"). `false-premise`: state the belief, never
  correct it.
- Three real queries as style examples, picked per tuple; choose them for style, not content.

## Checks and numbers (MediaDoctor v1)

| Check | Tool | v1 |
|---|---|---|
| valid tuples / feasible pairs | `lab04 dims`, `pair_coverage` | 1,342 / 242 |
| pair coverage | `lab04 tuples` | 242/242 with 200 tuples (34 pairwise) |
| query matches tuple | `lab04 check` | 10 flags in 200, 2 real defects |
| near-duplicates | `dedup(threshold=0.6, key=same test case)` | 0 of 200 dropped (closest pair 0.20) |
| diversity | `diversity_report` | top opener 10%, 4 LLM tells |
| coverage per split | `lab04 coverage` | dev 216/242, test 184/242 |
| leakage | `assign_splits(group_threshold=0.35)` + `leakage_pairs` | 0 (also 0 without grouping on these queries) |

## Splits

| Split | Use | Read it? |
|---|---|---|
| train | few-shot examples, prompt ideas | freely |
| dev | run often while improving | when it fails |
| test (held out) | report at milestones | no |

## Rules to remember

- Structure first, phrasing second.
- Coverage is a property of the tuples; check it with matrices, not a diversity score.
- Near-duplicates are a dimension value that did not make it into the words.
- Freeze and version; a changed dimensions file means a new version.
- Synthetic failure *rates* are not product quality; synthetic data finds failures, real data counts them.
- Replace synthetic with real queries as they arrive; keep synthetic for rare slices and known failures.

## Commands

```bash
uv run mediadoctor-lab04 dims
uv run mediadoctor-lab04 tuples --strategy pairwise
uv run mediadoctor-lab04 naive
uv run mediadoctor-lab04 generate --out runs/m4_v1.jsonl
uv run mediadoctor-lab04 check --dataset runs/m4_v1.jsonl
uv run mediadoctor-lab04 coverage --rows topic --cols evidence
uv run mediadoctor-lab04 gaps
uv run mediadoctor-lab04 agent --out runs/m4_traces.jsonl
uv run mediadoctor-lab03 signals --traces runs/m4_traces.jsonl --cases data/datasets/module04_v1.jsonl
uv run mediadoctor-lab04 by-dimension --dim ambiguity
EVALS_LLM_MODE=live uv run mediadoctor-lab04 generate --batch --out runs/m4_live.jsonl   # needs a key
```
