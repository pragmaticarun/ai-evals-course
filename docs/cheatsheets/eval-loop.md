# Cheat sheet: the eval loop

## The loop

```text
 ┌──────────► ANALYZE ──────────┐
 │  read outputs, name failure   │
 │  modes, rank them             ▼
IMPROVE                        MEASURE
 change one thing, compare    checks and judges you trust,
 per case, ship with numbers  numbers with uncertainty
 ▲                               │
 └───────────────────────────────┘
```

## Choosing an evaluator

| If the failure is... | Use | Notes |
|---|---|---|
| Checkable by rule (format, schema, ids, length, forbidden strings) | Code check | Write it first; test the check itself |
| Fuzzy but specific ("next step is actionable", "grounded in the cited doc") | Binary pass/fail LLM judge | One judge per failure mode; validate against human labels (module 5) |
| Unknown ("what goes wrong with DRM questions?") | Human review | Read traces; this is discovery, not measurement |
| A weak proxy (absolute words, length spikes) | Flag for review | Do not gate CI on proxies |

## Before you change a prompt or model

1. Fix the case set first, and keep it in git.
2. Run the baseline, then the change, on **the same cases**.
3. Look at the per-case diff (fixed and broken), not only the totals.
4. Read every newly broken case.
5. Treat small differences on small sets as noise until module 6 says otherwise.

## Replay commands

```bash
uv run pytest -q                                    # offline, like CI
uv run mediadoctor-lab01 compare v1 v2              # per-case diff
EVALS_LLM_MODE=record uv run mediadoctor-lab01 run  # re-record (needs ANTHROPIC_API_KEY)
```

## Red flags

- A metric was chosen before anyone read outputs.
- A 1 to 5 score nobody can explain the difference between 3 and 4 on.
- A judge nobody has compared with human labels.
- "It looked fine when I tried it."
