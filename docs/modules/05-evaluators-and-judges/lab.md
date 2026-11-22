# Lab 5: Code checks and three validated judges (offline)

**Time:** about 5 hours, half of it labelling and reading. **Needs:** the setup from [lab 1](../01-why-evals/lab.md),
and modules 3 and 4. **Does not need:** an API key or network access.

You will label MediaDoctor traces, run three code checks and three LLM judges against your labels and the
reference labels, iterate on one judge using the dev split, report every judge once on the test split, and produce
a corrected pass rate with a bootstrap interval. Keep your own files under `runs/`, which git ignores.

!!! info "Synthetic-authored fixtures"
    The agent traces, the reference labels, and the judges' outputs were written for the course and recorded
    through the real code paths; every record is labelled `"source": "synthetic-authored"`. Section 9 shows how to
    run the judges on Claude with a key.

## 1. Update and check

```bash
git pull
uv sync
uv run pytest -q
```

## 2. The labelled trace set

```bash
uv run mediadoctor-lab05 labels
```

```text
train  71 traces, 44 failing   accepted-false-premise 10, assumed-unstated-detail 12, ...
dev    37 traces, 22 failing   accepted-false-premise 9, ..., ignored-tool-output 6, vague-next-step 4, ...
test   29 traces, 19 failing   accepted-false-premise 5, ..., ignored-tool-output 5, vague-next-step 4, ...
```

These are 137 runs of MediaDoctor on the dataset v1 queries that match a module 3 scenario. The splits are dataset
v1's, so a query's split never changes between modules.

## 3. Label the traces yourself (about 2 hours)

Write the traces to a file and label them with the module 3 annotation tool:

```bash
uv run python -c "
from evalkit.synth import write_jsonl
from mediadoctor.lab05 import run_traces
write_jsonl('runs/m5_traces.jsonl', run_traces())"
uv run mediadoctor-lab03 annotate --traces runs/m5_traces.jsonl --labels runs/m5_labels.csv --annotator "your name"
```

Label at least the 37 dev traces and the 29 test traces, ideally all 137. Use module 3's mode names where they fit
and module 4's two new ones (`accepted-false-premise`, `assumed-unstated-detail`). Then compare:

```bash
uv run mediadoctor-lab03 compare --labels runs/m5_labels.csv --reference data/labels/module05_reference.csv
```

Where you disagree with the reference, decide who is right and write it down. Your labels are the ground truth for
*your* judges; the reference is one expert's opinion.

## 4. Code checks

```bash
uv run mediadoctor-lab05 checks
```

```text
format        (format-violation     ) n=137 (human pass 133, fail 4)  TPR 1.00 (133/133)  TNR 1.00 (4/4)  agreement 1.00
citations     (fabricated-evidence  ) n=137 (human pass 133, fail 4)  TPR 1.00 (133/133)  TNR 1.00 (4/4)  agreement 1.00
investigated  (skipped-investigation) n=137 (human pass 133, fail 4)  TPR 1.00 (133/133)  TNR 0.75 (3/4)  agreement 0.99
```

Read the three check functions in `labs/mediadoctor/src/mediadoctor/lab05.py`. Code checks can run on all splits:
nothing is tuned on them. Find the trace `investigated` misses (exercise 4 asks you to fix it).

## 5. Read a judge prompt

```bash
uv run mediadoctor-lab05 show next-step
uv run mediadoctor-lab05 show tool-grounding
```

Open the specs in `config/judges/`. For each judge, note: which context it sees, which borderline cases its PASS
and FAIL definitions settle, and which trace each few-shot example comes from. Then check the examples:

```bash
uv run mediadoctor-lab05 leaks
```

Expected: `ok` for all four specs.

## 6. Iterate on the dev split

Run tool-grounding v1 on dev and read every disagreement:

```bash
uv run mediadoctor-lab05 judge tool-grounding --version v1 --split dev
uv run mediadoctor-lab05 disagreements tool-grounding --version v1 --split dev
```

Sort them: judge wrong, label wrong, or criterion unclear? Then compare `tool-grounding.v1.toml` with
`tool-grounding.v2.toml` (`diff config/judges/tool-grounding.v1.toml config/judges/tool-grounding.v2.toml`) and run
v2:

```bash
uv run mediadoctor-lab05 disagreements tool-grounding --version v2 --split dev
```

TNR goes from 0.33 to 1.00 and TPR from 0.96 to 0.89. Do the same reading for the other two judges on dev:

```bash
uv run mediadoctor-lab05 disagreements false-premise
uv run mediadoctor-lab05 disagreements next-step
```

The false-premise judge has a pattern in its misses (exercise 5). Write what a v2 would change in
`runs/m5_notes.md`, but do not run it on test.

## 7. Report on the test split, once

When you have stopped changing the judges:

```bash
uv run mediadoctor-lab05 validate --split dev  > runs/m5_validation.txt
uv run mediadoctor-lab05 validate --split test >> runs/m5_validation.txt
uv run mediadoctor-lab05 checks >> runs/m5_validation.txt
```

```text
tool-grounding@v2      test  n=25 (human pass 20, fail 5)  TPR 0.90 (18/20)  TNR 0.60 (3/5)  agreement 0.84
false-premise@v1       test  n=29 (human pass 24, fail 5)  TPR 0.96 (23/24)  TNR 0.60 (3/5)  agreement 0.90
next-step@v1           test  n=29 (human pass 25, fail 4)  TPR 0.92 (23/25)  TNR 1.00 (4/4)  agreement 0.93
```

This file is your judge validation report. Add one line per judge saying whether you would use it, and for what:
gating a release, a dashboard trend, or only pointing reviewers at traces. Then try running v1 on test:

```bash
uv run mediadoctor-lab05 judge tool-grounding --version v1 --split test
```

It fails with a missing fixture: v1 was never run on test, by design. Once you have looked at test results, any
further change to a judge needs a fresh test set.

To validate against *your* labels instead of the reference (label every dev trace first), point the code at your file:

```bash
uv run python -c "
from mediadoctor import lab05
mine = lab05.annotations('runs/m5_labels.csv')
v = lab05.validate('tool-grounding', None, 'dev')
from evalkit.judge import confusion
print(confusion(lab05.human_pass('ignored-tool-output', list(v.verdicts), mine), {k: x.passed for k, x in v.verdicts.items()}))"
```

## 8. Corrected pass rate with a confidence interval

```bash
uv run mediadoctor-lab05 estimate
```

```text
observed pass rate 0.820 on 89 unlabelled traces; corrected 0.840, 95% CI [0.236, 1.000] (...)
true pass rate from the module 3 reference labels: 0.876
```

The judge has not seen module 3's traces before; we treat them as new traffic. Answer in your notes: why is the
corrected rate higher than the observed one? (Hint: which is larger, the share of good answers the judge fails,
or the share of bad answers it passes?) Why is the interval so wide, and what would you do about it?

## 9. Compare with a 1 to 5 judge

```bash
uv run mediadoctor-lab05 likert --split dev
uv run mediadoctor-lab05 likert --split test
```

The table shows how scores spread over human PASS and FAIL. Pick a threshold on dev, then look at what it does on
test, next to the binary judge. Exercise 2 asks you to make the argument with numbers.

## 10. Optional: run the judges on Claude

With an API key, record real judge outputs for your own labels and compare:

```bash
EVALS_LLM_MODE=live uv run mediadoctor-lab05 validate --split dev
```

Judge requests are small: 2,000 to 5,000 input tokens with the few-shot examples, under 200 output tokens. At Haiku
prices the three judges on the dev split cost a few cents. Expect different numbers from the synthetic ones, and
expect the first prompt to need a round of the dev-split loop above.

## Checkpoint

- [ ] `runs/m5_labels.csv` with at least the dev and test traces labelled
- [ ] Your disagreement notes for each judge on dev, sorted into judge wrong / label wrong / criterion unclear
- [ ] `runs/m5_validation.txt`: TPR and TNR with counts for each judge on dev and on test, and each code check
- [ ] A corrected pass rate with its interval, and a sentence on how many more labels you would need
- [ ] A filled [judge prompt template](../../eval-templates/judge-prompt.md) for a judge of your own
