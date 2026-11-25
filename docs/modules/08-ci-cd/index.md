# 8. CI/CD for agents

**Goal:** turn the evals into a safety net that runs on every change.

**Estimated time:** 6 hours (lesson 1.5 h, lab 3 h, exercises and quiz 1.5 h)

By the end of this module you will be able to:

- structure an eval suite as pytest tests in two tiers: fast code checks on every pull request, and slower judge
  suites on a schedule or on request;
- gate prompt, model, and tool changes with paired tests from `evalkit.stats` instead of fixed thresholds, and
  explain what the gate can and cannot see at a given n;
- version a golden dataset with a manifest of hashes, and compare every change with a baseline committed on the base
  branch;
- run the record/replay workflow in CI, and decide when a change needs re-recorded fixtures;
- publish an experiment comparison (a Markdown diff of two runs) as a GitHub job summary and an artifact;
- check a dataset for leakage, contamination, and stale labels, and keep a held-out set that tuning never sees;
- set time and cost budgets for the CI jobs and for live re-recording.

Artifacts: the `eval-gate` workflow (`.github/workflows/eval-gate.yml`), the eval suite in `evals/`, the gate's
rules and budgets in `config/eval_gate.toml`, the golden manifest (`data/golden/manifest.json`), the committed
baseline (`evals/baseline.json`), the lab CLI (`uv run mediadoctor-lab08`), the new `evalkit.gate`, `evalkit.golden`,
and `evalkit.hygiene` modules, and the [CI/CD cheat sheet](../../cheatsheets/ci-cd.md).

## Intuition: presubmit, nightly, and the conformance stream

You already work in a world with two kinds of automated checks. Presubmit runs on every change: it builds, runs
unit tests, and lints, and it has to be fast and deterministic or people stop trusting it. The nightly device lab
runs the expensive things: long playback soaks, power, and performance on real hardware, with results someone reads
in the morning. And codec work has a third habit that maps almost exactly onto this module: conformance testing.
You decode a fixed set of reference bitstreams and compare the MD5 of every output frame with a checked-in value. The
streams never change without a version bump, and a mismatch is never "probably fine".

Evals in CI borrow all three. Replayed fixtures are the conformance streams: the same request always produces the
same recorded answer, so the suite is deterministic and free, and it needs no API key. Cheap code checks run on every
pull request, like presubmit. LLM judges, which cost money to re-record and carry their own error, run on a schedule
or on request, like the nightly lab. A live run that calls the model is a deliberate, separate job.

One thing is different from unit tests: the outcomes are rates over a sample, so a gate needs the statistics from
module 6. If a benchmark's frame rate drops from 60.1 to 59.8, you would not fail the build without knowing the
run-to-run spread; a pass rate that drops from 0.94 to 0.93 deserves the same care. If it drops from 0.94 to 0.79 on
the same cases, the gate should stop the merge and say which cases changed.

## Step 1: the eval suite as pytest tests, in two tiers

The course's unit tests live in `tests/` and run in the `ci` workflow. The eval suite is separate, in `evals/`, so it
can run on its own schedule with its own budget:

| File | Tier | What it asserts |
|---|---|---|
| `evals/test_golden.py` | fast | the golden manifest matches the files; the splits do not overlap; gate tiers never read the held-out split; no leakage, unreviewed contamination, or stale labels |
| `evals/test_replay.py` | fast | every request of the release configuration is recorded; the committed baseline describes this commit |
| `evals/test_gate_code.py` | fast | each code check (format, citations, investigated, and all of them together) does not regress against the base's baseline; the tier fits its budget |
| `evals/test_gate_judges.py` | `judges` | every judge call is recorded; no judge regresses; the tier fits its budget |

The tiers are a pytest marker. `uv run pytest evals -m "not judges"` runs the fast tier (11 tests, under a second
here); `uv run pytest evals -m judges` runs the judge tier (5 tests). Session-scoped fixtures in `evals/conftest.py`
replay the agent once per tier and share the run between tests, so a test per metric costs nothing extra and the CI
log names the metric that failed.

Which checks go in which tier follows from what each one costs and how much you trust it:

| | Code tier | Judge tier |
|---|---|---|
| Runs on | every pull request and every push to `main` | nightly at 03:15 IST, by hand, or a PR labelled `run-judges` |
| Cases | 119 (train and dev splits of the labelled set) | 30 (dev split) |
| Evaluators | format, citations, investigated: code, validated in module 5 at TPR 0.78 to 1.00 (TNR barely measurable: the labelled traces hold one citation failure and none of the other two) | false-premise, tool-grounding, next-step: LLM judges, TPR 1.00 on dev (TNR not measurable: no dev trace fails) |
| Replay time | about 0.4 s | about 0.7 s |
| Live re-record | 238 Sonnet calls, about $0.81 | 90 judge calls plus 60 agent calls, about $0.24 |

Deterministic checks belong on every change because they are cheap and their verdicts are exact. Judges are
replayed here too, so in this repo the judge tier is just as fast; the split still matters because in a real
pipeline every new candidate's answers have to be judged live (new answers mean new judge requests), and because a
judge's errors make its tier a weaker gate (Step 2).

## Step 2: regression gates without fixed thresholds

The obvious rule is "block if the pass rate drops", perhaps with a tolerance: block if the candidate is more than 2
points below the baseline. Run `uv run mediadoctor-lab08 naive` to see it against the paired gate on the v1 to v2
change from module 6:

```text
metric               v1     v2   no-drop  2-pt tol.  5-pt tol.  paired gate
format            1.000  1.000      pass       pass       pass  pass
citations         1.000  0.975      fail       fail       pass  warn
investigated      0.782  0.832      pass       pass       pass  pass
all-code-checks   0.782  0.815      pass       pass       pass  pass
```

v2 changes little on these cases, and the rules disagree on the one metric that got worse. Three of 119 answers
lost their citations check and none gained it, a 2.5-point drop: the no-drop rule and the 2-point tolerance block
on it, the 5-point tolerance waves it through, and the paired gate warns, because three flips against none is
consistent with chance but the interval cannot rule out a drop larger than 5 points. Which fixed rule is "right"
depends on how many cases flip by chance, and the fixed rules do not know. That is the general pattern: a fixed tolerance is right for one combination of sample size and
run-to-run noise and wrong for the others. Exercise 1 simulates it at n = 100 with live-style noise: the no-drop rule
blocks 34% to 48% of changes that change nothing, and a 3-point tolerance blocks 1% to 10% of them depending on the
noise, while the paired gate stays near 1%.

The gate in `evalkit.gate` treats each metric as paired outcomes on the same cases (module 6) and decides with three
statuses:

- **fail**: the candidate is worse, McNemar's exact test on the discordant cases gives p < 0.05 after a Holm
  adjustment across the tier's metrics, and the drop is at least `min_effect` (0.02 here);
- **warn**: not shown to be worse, but the 95% paired bootstrap interval reaches below `-margin` (−0.05 here), so the
  run cannot rule out a drop you would care about;
- **pass**: otherwise.

The false-alarm rate of "fail" is controlled by alpha, whatever n is. What n controls is power: the chance of
catching a real drop. With 119 cases and the code tier's flip rate (v1 and v2 disagree on 12% of
cases), the gate catches a drop of about 9 points with 80% power. The judge tier's 30 cases are another matter: the
judges give v1 and v2 the same verdict on every one, so the tier offers no estimate of its own noise, and planning
with the code tier's 12% says 30 cases cannot reliably see any drop smaller than that disagreement rate (exercise
5). A warn is the gate saying so. Do not tune `margin` until warnings go away;
add cases, or read the flips.

A judge tier also inherits its judge's errors. On the dev split the human labels find no false-premise failure in
either prompt's answers, and one v2 failure of another kind: `m4q044` cites a knowledge-base document without having
searched (fabricated evidence). The citations code check catches it; the tool-grounding judge passes it, and every
judge passes every dev answer of both prompts. With no failing dev trace, module 5 could not even measure the
judges' TNR there, so a clean judge tier says little about whether failures are absent. On data with more failures,
the same comparison would show a judge with low TNR shrinking the visible difference between two prompts: comparing
the same judge on both sides cancels some of its bias, but a judge that misses most failures cannot show that they
went away. Code checks gate; judge tiers mostly inform, until the judge is good enough to gate.

!!! note "Must-pass cases"
    Some cases encode a past incident ("never tell users to disable DRM"). Those are tests, not samples: assert them
    exactly in `evals/` and fail on any regression, without statistics. Keep them few, or the suite turns back into a
    pile of fixed thresholds.

## Step 3: golden datasets, versions, and baselines

A gate compares against something fixed. Two files pin it down.

The **golden manifest** (`data/golden/manifest.json`) names the golden set (`mediadoctor-golden 1.0.1`) and lists the
SHA-256 of every file the gate's numbers depend on: the dataset, the reference labels from modules 5 and 6, the judge
specs, the recorded fixtures, a digest of each labelled answer, and the hygiene review. It also stores a digest of
each split's case ids (119 gate, 30 judge, 28 held out). `evalkit.golden.check_manifest` lists every difference, and
`evals/test_golden.py` fails the build on any of them. Changing a label, a judge spec, or a fixture is fine; doing it
silently is not. Bump the version with the change: major for new cases or splits, minor for relabels or re-recorded
runs, patch for fixes that change no outcome. Old numbers then come with the version they were measured on.

The **baseline** (`evals/baseline.json`) is a saved run of the release configuration: per tier, per metric, the
outcome of every case, plus the configuration's fingerprint and the cost of the run. The configuration lives in
`config/release.toml` (`prompt = "v1"`); the fingerprint is a hash of everything about the agent's requests except
the conversation (model, limits, system prompt, tool definitions).

Two rules make the baseline trustworthy:

1. The gate reads the baseline from the **base branch** (`git show <base>:evals/baseline.json`), not from the pull
   request. A PR cannot move its own goalposts.
2. The PR must commit a baseline that matches its own behaviour (`evals/test_replay.py`). Once it merges, `main`'s
   baseline describes what `main` ships, and the next PR is compared with that. The baseline diff in the PR shows,
   case by case, which outcomes the change flipped, which is exactly what a reviewer should read.

## Step 4: record, replay, and when to re-record

Since module 1, every Claude call goes through `evalkit.llm.LLM`, which keys each request by the SHA-256 of its
canonical JSON. CI runs in replay mode: no key, no network, the same answer every time. The price of determinism is
that **any change to any byte of a request is a miss**: a reworded prompt, a new model ID, an edited tool
description, a different tool result in a later turn, or a reworded judge spec.

A miss is information, not a failure to paper over. The gate distinguishes it from a regression:

- `uv run mediadoctor-lab08 preflight` checks that the first request of every gate case is recorded. It is cheap
  and catches prompt, model, and tool changes before anything runs.
- A later turn can still miss when a tool result changed (a KB edit, a new probe cache), so the suite also catches
  misses during the replay and reports every case that missed.
- Either way, `gate` exits with code 3 and writes "needs re-recorded fixtures" to the summary instead of a pass or a
  fail.

When to re-record:

- **When the change is the point.** A new prompt, model, or tool means new behaviour, so record it, read it, and label
  what changed before trusting the gate. Recording does not happen in CI: run it locally with a key
  (`EVALS_LLM_MODE=record`) or with the manual `live-evals` workflow, which uploads the new fixtures as an artifact
  for you to review and commit. New recordings go to their own namespace (`mediadoctor-m8-agent`), and the replay
  chain also finds older modules' records, because keys are content hashes.
- **On a schedule, to catch drift.** A pinned model ID should not change behaviour, but serving stacks do. Re-record
  a sample monthly and compare it with the fixtures using the same paired test; a significant difference is drift,
  and the fixtures (and labels) should be refreshed.
- **Never to make CI green.** Re-recording until a flaky case passes is the eval version of retrying a flaky test
  until it passes.

Every re-record makes some labels **stale**: a label judged an answer that no longer exists. `data/golden/label_answers.csv`
stores a digest of each labelled answer; the hygiene check compares it with the replayed answers (Step 6).

## Step 5: experiment comparison reports

A gate's verdict is one bit; the reviewer needs the reasons. `mediadoctor-lab08` writes the same Markdown report in
three places: the GitHub job summary (`--summary "$GITHUB_STEP_SUMMARY"`), a file uploaded as a workflow artifact
(`--out`), and the terminal. `run` saves one configuration's results as JSON, and `diff` compares any two saved runs,
so the same report serves an experiment on your laptop and a PR in CI.

The report has four parts:

1. A headline (passed, passed with warnings, or blocked) and what was compared: the base's prompt, fingerprint, and
   where its baseline came from, the head's, and the golden version.
2. Per tier, a table with one row per metric: n, both rates, the paired difference with its interval, the flips in
   each direction, the adjusted p-value, and the status.
3. The flips to read first: each newly failing case with the first line of the new answer, and the newly passing
   ones. This is the part that turns a red X into a fix.
4. Cost and time: calls, tokens, the live cost of re-recording, the recorded latency, the replay time against its
   budget, and the rule in one sentence.

Keep the report in Markdown, keep it short, and put the details (the head run's JSON) in the artifact.

## Step 6: dataset hygiene

`uv run mediadoctor-lab08 hygiene` runs four checks, all of which `evals/test_golden.py` requires to be clean:

- **Leakage across splits.** A near-duplicate of a held-out case in the gate set lets tuning see the held-out set
  through the back door. Module 4 grouped similar queries (word-trigram Jaccard ≥ 0.35) into the same split, and the
  check confirms it held: the closest gate and held-out pair scores 0.204.
- **Judge examples.** A judge's few-shot examples must come from the train split (`evalkit.judge.leakage_problems`,
  module 5). None leak.
- **Contamination.** An eval case's text appearing in something tuned against it (an agent prompt, a judge prompt with
  its examples, the knowledge base) inflates the score on that case. The check looks for shared runs of eight words
  in the prose of each judge-tier and held-out question (pasted log lines are removed: the same logcat is shared by
  design). On the current data it finds none. Findings, when there are some, are recorded in
  `data/golden/hygiene_review.csv` with a decision (accept, or watch and pick other judge examples at the next judge
  revision), and the check fails only on findings nobody has reviewed. That file still holds five decisions from an
  earlier version of the judge examples (questions about `av_offset_300ms.mp4` that shared a sentence or a premise
  with an example about the same clip); none of them matches a current finding, and they are the kind of entry to
  prune at the next golden version bump.
- **Stale labels.** Labels whose answer digest no longer matches the replayed answer. None, until something is
  re-recorded.

A fifth kind of contamination concerns public benchmarks: a model may have trained on them. This course's data is
written for it and private, so the risk is low; for public sets, prefer cases written after the model's training
cut-off and check for verbatim recall.

## Step 7: overfitting to the eval set

Every PR that reads the gate's flips and adjusts the prompt is tuning on the gate set. Over months the gate set
becomes a dev set: the prompt does well on those 119 cases for reasons that may not carry over. Three habits keep
an honest number available:

1. **A held-out split CI never reads.** The 28 test-split cases are not in any tier's `splits`. `evalkit.golden.HoldoutGuard`
   refuses to hand their ids to anything that is not a release evaluation, and `evals/test_golden.py` asserts it.
2. **Look rarely, and log every look.** `uv run mediadoctor-lab08 release --log` evaluates the release (or a candidate)
   on the held-out split and appends a line to `data/golden/holdout_log.csv`. For v1 the code checks pass 0.786 of
   the 28 cases together; v2 gets 0.893, consistent with the gate's small, non-significant improvement on
   all-code-checks (0.782 to 0.815). A large gap between gate and held-out numbers is
   the overfitting alarm.
3. **Rotate.** After a fixed number of looks (say five) or a quarter, move fresh, never-used cases into the held-out
   split and move the old held-out cases, whose results people have now seen, into the gate set
   (`evalkit.golden.rotate`), then bump the golden version.

How much this matters is debated: when Recht et al. rebuilt the ImageNet test set, the models' ranking survived years
of reuse. But an LLM eval set is small, binary, and tuned against much more aggressively per case, which is the
unfavourable setting, so keep the precautions.

## Step 8: cost and time budgets

CI that is slow or expensive gets switched off. `config/eval_gate.toml` sets the budgets, and the suite enforces them:

| Budget | Value | Measured |
|---|---|---|
| Replay time of one tier's eval step | 120 s | 0.4 s (code), 0.7 s (judges) |
| Live re-record of one tier | $2.00 | $0.81 (code: 238 Sonnet calls), $0.24 (judges) |
| Wall time of that re-record at 4 parallel calls | 30 min | 4.5 min (code), 1.6 min (judges) |

Costs come from the recorded token counts and the prices in `config/models.toml`; times come from the recorded
latencies. Module 5's judge records carry no latency, so for those calls a simple token-based estimate fills in
(`estimated_latency_ms` in `lab08.py`). The workflow adds job timeouts (10 and 15 minutes), cancels superseded runs on the same branch, caches the uv
environment, and never calls the API. The agent's Sonnet calls are most of the live cost; the judges are Haiku calls
that grade answers already recorded, which is why a judge tier is cheap to re-record but not free to run on every
push in a live pipeline.

## Worked example: a system-prompt PR, passed with a warning

Module 6 compared prompt v2, written against the false-premise failures of modules 3 to 5, with v1 and found almost
no difference: both pass 0.98 of the 147 labelled traces, with three cases flipping each way. Here is what happens
when someone ships v2 anyway.

**1. The pull request.** It changes `config/release.toml` from `prompt = "v1"` to `prompt = "v2"`. Replay of the
v2 runs succeeds (module 6 recorded them), but `evals/test_replay.py` fails at once: the committed baseline still
describes v1. The author runs `uv run mediadoctor-lab08 baseline --write` and commits `evals/baseline.json`. The
baseline diff (318 changed lines) shows the outcomes the change flipped.

**2. The gate.** In CI, the `code-gate` job compares the head with the baseline on the base branch. Every
`test_no_regression` test passes, because nothing is significantly worse, but the job summary is not a plain pass:

```text
## Eval gate: ⚠️ passed with warnings

| Metric | n | Base | Head | Head − base (95% CI) | Flips −/+ | p (adj.) | Gate |
|---|---|---|---|---|---|---|---|
| format | 119 | 1.000 | 1.000 | +0.000 [+0.000, +0.000] | 0/0 | 1.000 | ✅ pass |
| citations | 119 | 1.000 | 0.975 | -0.025 [-0.059, +0.000] | 3/0 | 0.750 | ⚠️ warn |
| investigated | 119 | 0.782 | 0.832 | +0.050 [+0.000, +0.109] | 3/9 | 0.584 | ✅ pass |
| all-code-checks | 119 | 0.782 | 0.815 | +0.034 [-0.034, +0.092] | 5/9 | 0.848 | ✅ pass |

- citations: -0.025 [-0.059, +0.000], p(adj.)=0.750: cannot rule out a drop larger than 0.05
```

The flips table lists the three newly failing citations cases (`m4q003`, `m4q044`, `m4q131`), and they share one
pattern: each answer cites a knowledge-base document that `search_kb` never returned in that run. v2's new
sentence tells the model to check claims "against the tool output or the knowledge base", and in these answers it
appeals to the KB without looking it up. Format is unchanged, and investigated moves the other way (9 cases gained,
3 lost), which is not significant either. Labelled `run-judges`, the PR also gets the judge tier: every judge passes
every one of the 30 dev answers on both sides, so it shows no change at all, although the human labels fail one of
those dev answers (`m4q044`). The code check sees what the judge tier does not.

**3. The decision, the fix, and a replay miss.** A warn does not fail the job, so the merge is a reviewer's call.
Three flips against none could be chance, but each one is a fabricated citation, so the reviewer asks for a fix
first. The author adds one sentence to v2: cite a `[kb:...]` document only if `search_kb` returned it. The gate now
stops before evaluating anything:

```text
## Eval gate: ⛔ needs re-recorded fixtures

119 agent runs not recorded (e.g. m4q001, m4q002, m4q003). The change alters the requests, so the replayed suite
cannot evaluate it. ...
```

That is the correct answer: no recorded output says what the new prompt does. The next steps are to record the 119
runs (about $0.81 with the live-evals workflow or locally), read the flips, label the changed answers, bump the
golden manifest, rewrite the baseline, and push again. The course stops here because it uses no API key; the lab
shows the commands.

Two details made this a good outcome. A naive "pass rate must not drop" rule, or a 2-point tolerance, would have
blocked step 2 on three flips without saying whether three flips mean anything; the paired gate says it cannot tell
at this n and lists the cases to read. On data with more such failures, the same gate would block and the same
flips table would show why. And the held-out split played no part: nobody tuned the fix on it, so it can still
judge the fix once it is recorded.

## Checklist

- [ ] The eval suite is pytest tests in `evals/`, split by a marker into a fast tier (every PR) and a judge tier
      (schedule, label, or by hand).
- [ ] CI replays fixtures: no API key, no network, deterministic. Live runs are a separate, manual workflow.
- [ ] Gates use paired tests with a multiple-comparison adjustment, a minimum effect, and a warn margin; no fixed
      thresholds.
- [ ] The golden set has a version and a manifest of hashes; any change to its files fails CI until the version is
      bumped.
- [ ] The baseline is read from the base branch; each PR commits its own new baseline.
- [ ] Replay misses stop the gate with a distinct status; re-recording is a reviewed, labelled change.
- [ ] Each run publishes a Markdown comparison: metrics with intervals, flips to read, cost and time.
- [ ] Hygiene checks for leakage, contamination, and stale labels run in CI; findings are reviewed, not ignored.
- [ ] A held-out split is never read by CI or tuning; looks are logged, and the split is rotated.
- [ ] Each job has a time budget and a timeout; live re-recording has a cost budget.

## Summary

CI for evals is ordinary CI with two additions. Replayed fixtures make the suite fast, free, and deterministic, at
the price of treating every request change as a miss that has to be recorded and labelled deliberately. And because
the outcomes are rates, the gate is a paired test with honest power, not a threshold. Around those sit the habits
that keep the numbers meaning something: a versioned golden set, a baseline that a PR cannot edit for itself, hygiene
checks, a held-out split that stays held out, and budgets that keep the jobs cheap enough to leave switched on.

Next: [the lab](lab.md), then the [exercises](exercises.md) and [quiz](quiz.md). The
[CI/CD cheat sheet](../../cheatsheets/ci-cd.md) collects the rules and commands.
