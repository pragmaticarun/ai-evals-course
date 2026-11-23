# Lab 11: Experiments on accuracy, latency, and cost (offline)

**Time:** about 3.5 hours. **Needs:** the setup from [lab 1](../01-why-evals/lab.md), and modules 3, 5, 6, and 8.
**Does not need:** an API key (section 12 is optional and does).

You will rank MediaDoctor's failure modes by the expected value of fixing them, read a pre-registration, replay seven
configurations (two prompt fixes, Haiku alone, a Haiku-to-Sonnet cascade, a retry on a judge's FAIL, and prompt
caching) on 108 dev queries, compare each with its parent, plot the accuracy against cost frontier, write the
experiment log and a decision memo, and spend the one look at the held-out split. Keep your own files under
`runs/`, which git ignores.

!!! info "Synthetic-authored model behaviour, real everything else"
    The model's turns, token counts, and latencies were written by `scripts/author_module11_fixtures.py` and are
    labelled `"source": "synthetic-authored"`. The script draws each configuration's failures from a fixed table of
    rates per failure mode (the same random draw per query for every configuration, so comparisons are paired the
    way real ones are), and its latencies from a simple per-token model with jitter and a slow tail. It does not
    claim that Claude Sonnet 5.5 or Haiku 5.5 behave this way: on your own system, the rates are what you measure.
    The agent loop, tools, prompts, request bodies (including `cache_control`), checks, prices
    (`config/models.toml`), and statistics are real code. The reference labels in
    `data/labels/module11_reference.csv` record which failure the script put into each final answer.

## 1. Update and check

```bash
git pull
uv sync
uv run pytest -q tests/test_lab11.py
uv run mediadoctor-lab11 --help
```

## 2. Choose what to fix

```bash
uv run mediadoctor-lab11 ev
```

Read the table from Step 1 of the lesson. Then change the guesses: open a Python shell and edit `lab11.P_FIX` or
`lab11.EFFORT_DAYS` (for example, decide that ignored tool output is a hard mode for your team), and print
`lab11.ev_text()` again. Which ranks move? Write down, in one sentence each, why you would fix the top two first.

## 3. Read the configurations and the pre-registration

```bash
uv run mediadoctor-lab11 variants
```

```text
v1        parent -         claude-sonnet-5-5  prompt v1 cache off single   | baseline: the prompt MediaDoctor ships (config/release.toml)
v2        parent v1        claude-sonnet-5-5  prompt v2 cache off single   | prompt: check the user's claims before relying on them (module 6)
v3        parent v2        claude-sonnet-5-5  prompt v3 cache off single   | prompt: quote the tool value you rely on, never cite what did not run; two few-shot examples
v3-cache  parent v3        claude-sonnet-5-5  prompt v3 cache on  single   | prompt caching of tools + system prompt
haiku     parent v3-cache  claude-haiku-5-5   prompt v3 cache on  single   | model: Haiku 5.5 instead of Sonnet 5.5
cascade   parent v3-cache  claude-haiku-5-5   prompt v3 cache on  cascade  | routing: Haiku first; Sonnet when Haiku's answer fails a code check
retry     parent v3-cache  claude-sonnet-5-5  prompt v3 cache on  retry    | self-check: a Haiku judge reviews each answer; one retry with its critique on FAIL
```

Open `config/experiments/variants.toml`, `config/experiments/preregistration.toml`, and
`config/experiments/log.toml`. Before you run anything, answer for yourself: which experiments use a superiority
rule and which a non-inferiority rule, and why caching gets a rule of its own. Then read the v3 prompt in
`labs/mediadoctor/src/mediadoctor/experiments.py` (`SYSTEM_AGENT_V3`) and find the sentence aimed at each of the top
two failure modes.

The code you will use is in `mediadoctor.experiments` (building requests, running a task under a strategy, grading)
and `mediadoctor.lab11` (metrics, decisions, reports). A task is graded by module 5's code checks (format,
citations, investigated) and a reference check of the diagnosis (`experiments.check_correct`), which compares the
Likely cause with the fact each scenario's answer must state; it stands in for module 5's validated judges so the lab
can grade 750 answers offline.

## 4. Run one configuration

```bash
uv run mediadoctor-lab11 run v1 | head -8
uv run mediadoctor-lab11 run v1 | tail -1
```

```text
case    ok  checks failed                 latency      cost calls
m4q001  NO  timeout                        15.55s  $0.00829 3
m4q002  NO  correct                         3.06s  $0.00481 2
m4q003  yes -                               4.93s  $0.00673 3
...
success 72/108 = 0.667 [0.573, 0.748]  cost/success $0.00880
```

m4q001's answer passed every check, and the task still failed: it took 15.55 s, past the 15 s timeout. Now look at
one task's trace, with timings and cache usage:

```bash
uv run mediadoctor-lab11 trace v3-cache m4q002 | grep -vE '^\s*(│|├|└)?\s*·'
```

```text
invoke_agent MediaDoctor  [+0ms, 3.51s]
├─ chat claude-sonnet-5-5  [+0ms, 1.35s]
├─ execute_tool codec_caps  [+1.35s, 2ms]
├─ execute_tool ffprobe  [+1.35s, 45ms]
└─ chat claude-sonnet-5-5  [+1.40s, 2.12s]

checks: {'format': True, 'citations': True, 'investigated': True, 'correct': False}
latency 3.51 s  cost $0.00276  calls 2  cache read 2058 / write 0 tokens
```

The answer is wrong (it adopts the user's false claim that the atlas-a1 decodes AV1 only in software, although
`codec_caps` says otherwise), the format and citations are fine, and both calls read the 1,029-token prefix from
the cache. Drop the `grep` to see every attribute, including the per-call `gen_ai.usage.cache_read.input_tokens`
and `evalkit.cost.usd`.

## 5. The report

```bash
uv run mediadoctor-lab11 report --out runs/m11/report.txt
```

The first table is in Step 3 of the lesson. Below it are each change against its parent (paired), the failure
modes in the final answers per configuration, the frontier, and the cascade's and the retry's counts. Find three
things before reading on: the configuration with the most timeouts, the one with the lowest p95, and the widest p95
interval. Then compute one cost per success by hand from the `run` output (total cost over successes) and check it
against the table.

## 6. Experiment 1: the prompt fixes (v2, then v3)

```bash
uv run mediadoctor-lab11 report --only v1 v2 v3
```

Both pass the superiority rule. Use the failure-mode table to say which mode each prompt fixed, and the discordant
counts to say how many queries each change fixed and broke. Then answer: v3 costs 20% more per success than v2. Is
v3 a good change by itself, before caching? (By the pre-registered rule, yes: its rule is about success. By cost per
success, it is worse. Notice how the next experiment changes that.)

## 7. Experiment 2: prompt caching (v3-cache)

Caching must not change a single answer. Check it directly:

```python
from mediadoctor import lab11

a, b = lab11.task_results("v3"), lab11.task_results("v3-cache")
print(sum(x.answer == y.answer for x, y in zip(a, b)), "of", len(a), "answers identical")
print("timed out under v3:", [r.case_id for r in lab11.run_rows("v3") if r.timed_out])
```

```text
108 of 108 answers identical
timed out under v3: ['m4q007', 'm4q165']
```

Then read the cost: in `trace v3-cache m4q001` (the very first task) the first call writes the prefix
(`cache_write.input_tokens = 1029`), and every later call in the run reads it. Explain, in two sentences, why caching
made v3's few-shot examples almost free.

## 8. Experiment 3: model tiering (haiku, cascade)

```bash
uv run mediadoctor-lab11 report --only v3-cache haiku cascade
```

Both fail the non-inferiority rule by a wide margin. For the cascade, find out what the router missed: list the
tasks where the cascade failed but v3-cache succeeded, and the reference label of the cascade's final answer.

```python
from collections import Counter

from mediadoctor import lab11

base = {r.case_id: r for r in lab11.run_rows("v3-cache")}
lost = [r for r in lab11.run_rows("cascade") if base[r.case_id].success and not r.success]
labels = lab11.reference_labels()
print(len(lost), Counter(labels[("cascade", r.case_id)] for r in lost))
print("escalated among them:", sum(r.escalated for r in lost))
```

You should find that every lost task carries a failure the code checks cannot see, and none of them was escalated.
Write the hypothesis for the next experiment (a better router) in the experiment-log format.

## 9. Experiment 4: retry on a judge's FAIL, and its latency

```bash
uv run mediadoctor-lab11 latency retry
```

```text
v3-cache  p50  5.14 s  p95  7.76 s  calls/task 2.48  mean ms/task: agent calls 5,293, tools 28
retry     p50  5.84 s  p95 10.42 s  calls/task 3.64  mean ms/task: agent calls 5,701, self-check 392, tools 29

Tasks that slowed most (retry minus v3-cache):
  m4q132   +5.44 s  (7.19 -> 12.63 s, retried)
  m4q114   +4.39 s  (3.08 -> 7.47 s, retried)
  ...
```

The self-check costs about 0.4 s on every task; a retry costs 3 to 5 s on the tasks it touches. Look at one retried
task with `uv run mediadoctor-lab11 trace retry m4q132`: find the judge's chat span (`mediadoctor.self_check =
true`), the critique it sent back (`mediadoctor.critique` on the root span), and the agent's second answer. Then read the retry line at the bottom of the
report (how many defects the judge caught, how many false alarms, how many retries ended correct).

## 10. The frontier

```bash
uv run mediadoctor-lab11 pareto --svg runs/m11/pareto.svg
```

```text
frontier: haiku ($0.00018, 0.639) -> cascade ($0.00048, 0.694) -> v3-cache ($0.00342, 0.852) -> retry ($0.00384, 0.898)
cheapest within 2 points of the best (point estimates): retry
```

Open the SVG in a browser (hover a point for its numbers). Which configurations are dominated, and by what?

## 11. The experiment log and the decision memo

```bash
uv run mediadoctor-lab11 log --out runs/m11/experiment_log.md
uv run mediadoctor-lab11 memo --out runs/m11/decision_memo.md
```

The log merges what was written before each run (`config/experiments/log.toml`) with what was measured, and applies
each experiment's rule. The memo applies the pre-registered decision rule: keep each change that passed its own test
(and whose parent was kept), recommend the most accurate kept configuration. Read the draft against the
[decision memo template](../../eval-templates/decision-memo.md) and edit it: add the owner, the date of the held-out
check (next section), and one sentence on what would change your mind. Keep it to one page.

## 12. The held-out check (once)

```bash
uv run mediadoctor-lab11 confirm retry            # refused: no --release
uv run mediadoctor-lab11 confirm retry --release  # the one look; appended to runs/m11/holdout_log.csv
```

```text
held-out (n=29): v1 0.828  retry 0.966 [0.828, 0.994]  paired diff +0.138 [+0.000, +0.310]
cost/success $0.00650 -> $0.00329; look logged in runs/m11/holdout_log.csv
```

Add the result to the memo as a consistency check: the held-out rate is inside the dev interval, and the paired
difference is positive but wide, as 29 queries must give. If it had come out clearly worse than dev, the right
response would be to find out why (an overfit prompt? a split that differs?), not to look again until it passes.

## 13. What do the evals themselves cost?

```bash
uv run mediadoctor-lab11 cost --runs 3
```

Three live runs of the dev suite with the recommended configuration cost about $1.25 at standard prices, or $0.62
through the Batch API. Batch fits a nightly or pre-release suite (results within 24 hours), not the per-push replay
gate, which costs nothing.

## Optional: record a few live runs

With `ANTHROPIC_API_KEY` set (never commit it), you can replace the scripted model with the real one for a handful
of dev queries. This records into `runs/`, so the course fixtures stay untouched; ten v3-cache tasks cost a few cents.

```python
from functools import cache
from pathlib import Path

from evalkit import LLM
from mediadoctor import experiments as X
from mediadoctor import lab11

out = Path("runs/m11/live-fixtures")
X.llm_for = cache(lambda ns: LLM(namespace=ns, mode="record", fixtures_dir=out, source="live"))
for c in lab11.split_cases("dev")[:10]:
    t = X.run_task(c, "v3-cache")
    print(
        c["id"],
        "ok" if t.graded_success else "FAIL",
        f"{t.latency_ms / 1000:.1f}s",
        f"${t.usage.cost_usd:.5f}",
        "cache read",
        t.usage.cache_read_tokens,
    )
```

Compare the real latencies and cache reads with the replay's. Expect the first call to write the cache and later
ones to read it only if they arrive within five minutes and the prefix is byte-for-byte identical.

## Checkpoint

You should have:

- your own expected-value ranking, with the guesses you changed;
- `runs/m11/report.txt`, and a sentence for each experiment that states the change, the paired difference with its
  CI, and the change in cost per success and p95;
- `runs/m11/pareto.svg`, with the dominated configurations named;
- `runs/m11/experiment_log.md` and an edited one-page `runs/m11/decision_memo.md`;
- one logged held-out look in `runs/m11/holdout_log.csv`.

Next: the [exercises](exercises.md).
