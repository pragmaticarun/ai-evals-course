# 5. Evaluators you can trust: code checks and LLM judges

**Goal:** turn MediaDoctor's failure modes into automatic evaluators, and measure how far each one can be
trusted before you use its numbers.

**Estimated time:** 9 hours (lesson 2 h, lab 5 h, exercises and quiz 2 h)

By the end of this module you will be able to:

- decide, failure mode by failure mode, between a code check and an LLM judge;
- write a binary judge for one failure mode, with PASS and FAIL definitions, few-shot examples taken only from
  the train split, a critique, and a fixed output schema;
- validate a judge against human labels with TPR and TNR: iterate on dev, report once on test;
- correct a judge-measured pass rate for the judge's own errors, with a bootstrap confidence interval;
- run alignment sessions with a domain expert, and recognise criteria drift;
- spot the common judge pitfalls: position and verbosity bias, self-preference, leakage, and rating scales.

Artifacts: three judge specs (`config/judges/*.toml`, from the [judge prompt template](../../eval-templates/judge-prompt.md)),
a judge validation report (`runs/m5_validation.txt`), and a corrected pass-rate estimate with its interval.

## Intuition: a judge is a classifier

An LLM judge reads a trace and says PASS or FAIL. That makes it a binary classifier, and you already know how to
trust a classifier: you do not trust it until you have measured it on labelled data it was not tuned on.

Think of a hardware video decoder conformance suite. You would not accept a new decoder because its output "looked
fine" on the clips you used to debug it. You run it on the conformance streams, compare bit-exact against the
reference decoder, and report failures per stream. A judge gets the same treatment: the human labels from module 3
are the reference, the train/dev/test splits from module 4 keep you honest, and TPR and TNR are the conformance
report.

One more thing changes once you start: your own criteria. Reading the judge's critiques and arguing with them
sharpens what you meant by "fail". That is expected, and the process has to allow it.

## Step 1: code check or judge?

Start from the failure modes you have, not from the evaluators you could build. For each mode, ask: *can a
program decide this from the trace, without understanding language?*

| Failure mode (module 3 and 4) | What decides it | Evaluator |
|---|---|---|
| format-violation | the three labelled lines are present, in order | code check |
| fabricated-evidence | every `[tool:x]` cited was called and succeeded; every `[kb:y]` cited was retrieved | code check |
| skipped-investigation | the question names something to inspect, and no tool ran and the agent did not ask | code check |
| wrong-tool-args, redundant-steps | tool error status, repeated identical retrievals | code checks (module 2) |
| ignored-tool-output | does a claim in the answer contradict a tool result? | **judge** |
| accepted-false-premise | did the answer build on a wrong claim made by the user? | **judge** |
| vague-next-step | is the next step something an engineer can act on? | **judge** |
| wrong-api-detail | is the API level or method right? | judge with reference notes, or a lookup table |

Code checks are cheap, fast, deterministic, and never drift. Use them for everything they can decide, even
partially. A judge costs a model call per trace, can be wrong in ways that change when the model is updated, and
needs its own validation. Use one only where meaning matters.

!!! warning "Code checks need validating too"
    Against the labels on all 147 traces, two of the three checks show a gap. `check_investigated` fails 32 traces
    the expert passed: questions that mention a phone, file, or log without naming it, where the agent answered
    from the knowledge base and said what it had not checked. The check's definition ("the expected inspecting tool
    ran, or the agent said `send me ...`") was narrower than the expert's. Exercise 4 fixes it. And
    `check_citations` passes the one `fabricated-evidence` trace (`m4q067`): its invented decoder caps are stated
    in prose, with no `[tool:x]` citation for the check to verify. A check can only catch what its definition
    looks at.

## Step 2: one judge per failure mode, binary, with a critique

A judge that checks "is this a good answer?" mixes several failure modes, so when it fails you cannot tell why, and
when you fix one mode its score barely moves. Write **one judge per failure mode** and make each one answer a
narrow question.

Make the verdict **binary**. A 1 to 5 scale feels more informative, but nobody can say what separates a 3 from a 4,
two reviewers will not agree on it, and to use the score you have to pick a threshold anyway. The lab shows the
scale moving: every next step in dev and test is acceptable to a human, yet the 1 to 5 judge gives a 5 to 53% of
them on dev and 82% on test, so a threshold fitted on one split means something different on the other. (The
course data has no labelled vague next steps, so it cannot show what that does to the failures you care about;
exercise 2 discusses it.) If you want to track gradual progress, use several binary checks.

Ask for a **critique before the verdict**. The critique gives the model room to look at the evidence before it
commits, and it gives you something to read when the judge disagrees with a human. A critique that quotes the exact
words its verdict rests on is far easier to audit than "the answer is accurate".

Hamel Husain and Shreya Shankar make the case for binary, single-criterion judges and critiques in their writing;
see [Credits](../../credits.md).

## Step 3: write the judge prompt

MediaDoctor's judges live in `config/judges/` as TOML files, one per judge and version. `evalkit.judge` turns a
spec and one trace into a request for the **judge** model (`claude-haiku-5-5` in `config/models.toml`, the cheaper
model; the agent runs on Sonnet). A spec has:

| Field | Purpose | Example (next-step v1) |
|---|---|---|
| `criterion` | one sentence: what PASS looks like | "The answer's Next step is a concrete action the engineer can take now." |
| `pass`, `fail` | precise definitions, including the borderline cases you have decided | "...or the specific information to send back (for example 'send the device model')" is PASS |
| `context` | which parts of the trace the judge sees | `["question", "answer"]`: the tool output is irrelevant to actionability |
| `[[example]]` | few-shot examples: a trace id, a verdict, a critique | a request for details (PASS), a release-notes change (PASS), a specific limit and code change (PASS) |

```bash
uv run mediadoctor-lab05 show next-step     # the full prompt the judge model receives
```

Four rules for the content:

1. **Examples come from the train split only.** Dev is for measuring changes, test is for the final report. A
   few-shot example from dev makes your dev numbers too good; one from test makes the final report meaningless.
   `mediadoctor-lab05 leaks` checks every spec.
2. **Include the borderline cases.** The hard part of "actionable" is "send me the device model": is asking a
   next step? Decide, write it into PASS or FAIL, and add an example. Take FAIL examples from train too; in this
   course's data no train trace fails any judge's criterion, so every few-shot example in `config/judges/` is a
   PASS, and the FAIL side of each definition is carried by the prose alone.
3. **Give the judge only the context it needs.** The tool-grounding judge needs tool results; the next-step judge
   does not, and extra context can distract it. Test such choices against labels rather than guessing.
4. **Fix the output schema.** JSON with `critique` and `verdict`. `parse_verdict` accepts code fences and
   surrounding text, and anything it cannot parse is counted separately and treated as FAIL, never guessed.

## Step 4: validate against human labels

### The labelled set

The lab runs MediaDoctor on every dataset v1 query that matches a module 3 scenario: 147 traces, split the way
dataset v1 is split (89 train, 30 dev, 28 test). The reference labels in `data/labels/module05_reference.csv` give
each trace a verdict and failure modes. For one judge, the human label is per criterion: a trace is a human FAIL
for the tool-grounding judge if and only if it was tagged `ignored-tool-output`.

Only 3 of the 147 traces fail at all, all in train: one `assumed-unstated-detail`, one `fabricated-evidence`,
one `redundant-steps`. None is tagged with a judge's mode (`ignored-tool-output`, `accepted-false-premise`,
`vague-next-step`), and dev and test have no failures of any kind. Keep that in mind for everything below: it
means every judge's TNR on this data is 0/0, undefined.

!!! info "Synthetic data, generated by Claude subagents"
    The data is synthetic. The agent turns in the recorded fixtures were generated by Claude subagents from the
    module 3 scenarios, and the reference labels were written by Claude Opus annotators. Treat the numbers as a
    worked example of the method, not as measurements of a production system.

### TPR and TNR

Take PASS as the positive class:

- **TPR** (true positive rate): of the traces a human passed, the share the judge passed.
- **TNR** (true negative rate): of the traces a human failed, the share the judge failed.

Report both, with their counts, never just accuracy or agreement. A judge that passes everything agrees with the
humans on every passing trace; if 85% of traces pass, it scores 85% agreement and catches nothing. In this
course's data 144 of 147 traces pass, so "always PASS" would score 98%. TNR is usually the number that matters,
because catching failures is the judge's job, and it is usually measured on few traces; here, on none.

### Worked example: the tool-grounding judge

Version 1 of the tool-grounding judge has two few-shot examples from train, both PASS: an answer whose claims
match `codec_caps` and the log, and `m4q067`, whose diagnosis matches the tools but which adds a claim no tool
returned (a borderline case, below). On the dev split:

```text
$ uv run mediadoctor-lab05 judge tool-grounding --version v1 --split dev
tool-grounding@v1      dev   n=30 (human pass 30, fail 0)  TPR 1.00 (30/30)  TNR nan (0/0)  agreement 1.00
```

Agreement 1.00, and it means very little. No dev trace ignores its tool output, so TNR is 0/0: these 30 traces
say the judge does not fail good answers, and nothing about whether it catches bad ones. `disagreements` prints
nothing to read.

The method is still the one to learn. When dev has failures, you read every disagreement and look for a pattern.
A typical one for this judge: the user states a wrong fact ("the lumen-l3 has a hardware AV1 decoder"), the
answer repeats it, and the judge treats agreement with the user as agreement with the evidence. That is a gap in
the prompt, not random noise, and version 2 is written against it: it adds one sentence to the FAIL definition
(agreeing with the user does not make a claim true) and two few-shot examples from train where the user asserts
a claim the tool output contradicts and the answer sides with the tools. Both examples are PASS, because no train
trace repeats such a claim; a FAIL example of exactly this kind would help more, and you would have to collect or
write one. On dev:

```text
tool-grounding@v2      dev   n=30 (human pass 30, fail 0)  TPR 1.00 (30/30)  TNR nan (0/0)  agreement 1.00
```

The change did not make the judge stricter on good answers (TPR stays 1.00), and dev cannot say whether it
catches more. We stop iterating, and run the test split **once**:

```text
$ uv run mediadoctor-lab05 validate --split test
tool-grounding@v2      test  n=28 (human pass 28, fail 0)  TPR 1.00 (28/28)  TNR nan (0/0)  agreement 1.00
false-premise@v1       test  n=28 (human pass 28, fail 0)  TPR 1.00 (28/28)  TNR nan (0/0)  agreement 1.00
next-step@v1           test  n=28 (human pass 28, fail 0)  TPR 1.00 (28/28)  TNR nan (0/0)  agreement 1.00
```

This is the honest report, and it has to be read honestly: the three judges pass every good test answer, and their
ability to catch failures is **unmeasured**. A TNR from a handful of failures is already weak (3 of 5 is consistent
with a true TNR anywhere from about 0.25 to 0.9, 95% Wilson interval, module 6); from zero failures there is no
estimate at all. If that is not good enough, and for gating a release it is not, the fix is labelled failures, a
new dev round, and a *new* test set, not another look at this one. (The fixtures for tool-grounding v1 on test do
not exist; the test refuses to run it.)

Hamel Husain and Shreya Shankar recommend aiming for at least 50 passing and 50 failing labelled examples per
judge. Our test split has 28 passing and 0 failing per judge. When the agent fails as rarely as this one does,
failures have to be sought out: oversample traces that code checks or user signals flag, run adversarial queries
(module 4), or write labelled failing answers for the purpose.

## Step 5: correct the pass rate for judge error

A judge with imperfect TPR and TNR gives a biased pass rate. If the true pass rate is θ, the judge passes
θ × TPR of the traffic correctly and wrongly passes (1 − θ) × (1 − TNR), so

```text
observed = θ·TPR + (1 − θ)·(1 − TNR)      →      θ = (observed + TNR − 1) / (TPR + TNR − 1)
```

This is the Rogan-Gladen estimator from epidemiology, where it corrects disease prevalence measured with an
imperfect screening test. It only works when TPR + TNR > 1; at TPR + TNR = 1 the judge is a coin with a bias and
carries no information. `evalkit.judge.corrected_pass_rate` implements it, clipped to [0, 1].

The point estimate is not enough, because TPR and TNR are themselves estimates from a few labelled traces.
`bootstrap_corrected` resamples both the labelled test set and the judged traffic many times and recomputes the
corrected rate each time; the 2.5th and 97.5th percentiles give a 95% interval that includes uncertainty about the
judge.

The lab treats module 3's 100 traces as new, unlabelled traffic, runs the final tool-grounding judge on them (all
100 have tool output), and tries to correct with the test-split TPR and TNR:

```bash
uv run mediadoctor-lab05 estimate
```

On this data there is nothing to correct with. The judge passes all 100 traces (observed pass rate 1.000), the
module 3 reference labels agree (true pass rate 1.000), and the test split has no labelled failures, so TNR is
0/0 and TPR + TNR − 1 cannot be estimated. The command stops with an error (currently an `IndexError` from the
bootstrap, which finds no resample where the correction is defined) rather than printing a number. That is the
right outcome, even if the message could be clearer: a corrected rate here would be made up.

What the correction does when the labels allow it is in exercise 3, with a hypothetical labelled set of 25 traces
and 5 failures (TPR 0.90, TNR 0.60) and an observed rate of 0.82: corrected 0.84, with a 95% interval from about
0.12 to 1.00. With 5 labelled failures the judge's TNR is so uncertain that some resamples make it barely better
than chance, and the correction explodes. The interval is not a bug; it is the cost of 5 failures, stated
honestly, and it narrows as labelled failures grow. Module 6 builds on this with Wilson intervals, paired
comparisons, and sample-size planning.

The same idea is implemented, with a clear write-up, in the open-source
[judgy](https://github.com/ai-evals-course/judgy) package from Hamel Husain and Shreya Shankar's course; see
[Credits](../../credits.md).

### A better use of the same labels: prediction-powered inference

The correction above learns the judge's error rates on one labelled set and applies them to different traffic. Its
interval explodes when few labelled traces fail, and it silently assumes the error rates transfer. A newer method,
**prediction-powered inference** (PPI; Angelopoulos et al., [arXiv 2301.09633](https://arxiv.org/abs/2301.09633)),
spends the same labelling budget differently: a person labels a small **random sample of the traffic itself**, the
judge scores everything, and the judge's mean on the unlabelled part is corrected by the average human-minus-judge
difference on the labelled part. **PPI++** ([arXiv 2311.01453](https://arxiv.org/abs/2311.01453)) adds a weight λ
that the data chooses: a judge that agrees with people pulls the interval in, a useless one is weighted toward 0,
where the estimate is simply the human labels' mean. It is never worse than ignoring the judge.

`evalkit.stats.ppi_mean` implements both. `uv run mediadoctor-lab05 ppi` compares them on module 3's 100 judged
traces, with 25 of them labelled (picked by a stable hash, so a random sample), next to the human labels alone and
Rogan-Gladen. On this data the comparison has nothing to separate: the 25 labels are all PASS and the judge passes
all 100 traces, so the human labels give 1.000 [0.867, 1.000] (Wilson), and PPI and PPI++ both give 1.000 with a
zero-width interval (PPI++ chooses λ 0.00, because the judge's verdicts do not vary). The command itself stops
at the Rogan-Gladen row, for the reason given above.

Two readings survive. PPI does not need labelled failures to run, because it never estimates TNR; it needs a
random sample of the traffic, which is a cheaper thing to have. But a zero-width interval from 25 unanimous
labels is not certainty either: it reflects a sample with no variation, and the Wilson interval on the labels
alone is the more honest statement of what 25 passes tell you. On traffic with failures, PPI++ is the method to
prefer when you can label a random sample of what you are measuring, because its λ weights the judge by how well
it agrees with people; keep the Rogan-Gladen correction for when the labels come from somewhere else, and say so.

## Aligning with the domain expert

Validation numbers say how often the judge disagrees with the labels. Alignment is what you do with each
disagreement. Sit down with the domain expert (in module 3's terms, the benevolent dictator) and sort every dev
disagreement into one of three piles:

1. **The judge is wrong.** Fix the prompt: a sharper definition, a missing borderline case, a few-shot example of
   the kind it gets wrong, or different context. The user-premise pattern behind tool-grounding v2 is this kind.
2. **The label is wrong.** It happens: the expert was tired, or read past a number. Fix the label, and note it.
3. **The criterion is unclear.** Both readings are defensible. Train trace `m4q067` diagnoses an AV1 stutter
   correctly from `ffprobe` and `codec_caps`, then adds that lumen-l3's "hardware AVC/HEVC decoders list
   1920x1080 at 60 fps", which no tool returned (only AV1 caps were queried). Is an *unsupported* claim a
   grounding failure, or only a *contradicted* one? Here the decision was made: the expert labelled it
   `fabricated-evidence`, not `ignored-tool-output`, and the tool-grounding spec carries it as a PASS example whose
   critique says "Unsupported is a different failure mode; this criterion passes." That is the pattern: the
   expert decides, writes the answer into PASS or FAIL, adds an example, and relabels if the decision changes
   earlier labels.

Keep the session short and regular, and keep a log of decisions next to the spec. Each decision is a small change
to the definition of the failure mode, and the log is how you know which labels were made under which definition.

## Criteria drift

Shreya Shankar and colleagues observed something in [Who Validates the Validators?](https://arxiv.org/abs/2404.12272)
that every team rediscovers: people need criteria to grade outputs, but grading outputs changes their criteria. A
reviewer starts with "the next step must be actionable", meets "send me the device model", decides that counts,
then meets "send me a log" on a question that already pasted one, and revises again. The paper calls this
*criteria drift* and argues that evaluation tools should expect it rather than fight it.

In practice:

- **Expect your first definitions to be wrong.** Write them, label 30 to 50 traces, then revise them before
  labelling the rest.
- **Version the spec and the labels together.** When a definition changes, relabel the traces it affects, or at
  least the dev and test splits.
- **Re-check old labels after big changes.** A judge that "got worse" may be agreeing with your new criterion and
  disagreeing with your old labels.

## Beyond one binary judge

The single-criterion binary judge is the default because it is the easiest to validate. Four newer patterns build
on it, and each still gets the TPR and TNR treatment above:

- **A panel of judges.** Several smaller judges from *different model families*, combined by majority vote, can
  agree with people more often than one large judge, at lower cost, and dilute any one model's self-preference
  (Verga et al., [Replacing Judges with Juries](https://arxiv.org/abs/2404.18796)). Validate the panel's vote, not
  each member; and report how often members disagree, because a split vote is a trace worth reading.
- **Rubrics with per-item criteria.** For long answers, write a checklist per case ("names the decoder instance
  limit", "does not suggest disabling DRM"), each criterion binary, and grade each one. This is how
  [HealthBench](https://arxiv.org/abs/2505.08775) grades: thousands of expert-written, case-specific criteria. It is
  module 5's method at a finer grain, so the same rules apply: definitions with borderline cases, validation per
  criterion, and no rolled-up score that hides which criterion failed.
- **A judge that thinks.** Turning thinking on (or effort up) for the judge model often helps on criteria that need
  checking several claims against evidence, and costs latency and tokens on every call. It is a new judge version:
  re-validate it. Keep the critique field either way, because it is what you read in alignment sessions.
- **A judge with tools (agent-as-a-judge).** For agents that change things, a judge that can inspect the
  environment (read the produced file, query the ticket tracker, rerun a test) checks outcomes a transcript cannot
  show (Zhuge et al., [Agent-as-a-Judge](https://arxiv.org/abs/2410.10934)). It is a more complex evaluator with
  more ways to fail, so it needs more labelled cases, not fewer. Module 7 covers grading the final state directly
  in code, which is cheaper wherever it is possible.

## Judge pitfalls

| Pitfall | What happens | What to do |
|---|---|---|
| Position bias | in A-versus-B comparisons, the judge prefers the answer in one position | prefer single-answer binary judges; for comparisons, judge both orders and count only consistent wins |
| Verbosity bias | longer, more detailed answers look more correct | criteria about specific claims, not overall quality; examples where a long answer fails |
| Self-preference | a model rates text in its own style higher | validate against human labels; consider a judge from a different model family for important judges |
| Leakage | few-shot examples from dev or test; the expected answer, the human label, or the reviewer's note in the prompt | examples from train only; `leakage_problems`; the judge sees what production would show it, nothing more |
| Rating scales | 1 to 5 scores with no agreed meaning; the threshold you choose on dev fails on test | binary verdicts; several binary checks for gradual progress |
| Unparsed output | "PASS" in prose, extra text around the JSON | a fixed schema, a tolerant parser, and a count of unparsed outputs |
| Silent model changes | a new model version moves TPR and TNR | pin the model ID in `config/models.toml`; revalidate when it changes |

Position and verbosity bias, and the self-enhancement effect, were measured systematically by Zheng et al. in
[Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena](https://arxiv.org/abs/2306.05685); Panickssery et al.
showed that models recognise and favour their own outputs in
[LLM Evaluators Recognize and Favor Their Own Generations](https://arxiv.org/abs/2404.13076). Our judge is Haiku
and the agent is Sonnet, from the same family, so self-preference is a live risk worth testing when you record
real runs.

## Checklist

- [ ] Every failure mode has an evaluator; code checks wherever a program can decide.
- [ ] One judge per failure mode, binary, critique first, JSON output.
- [ ] PASS and FAIL definitions include the borderline cases you have decided.
- [ ] Few-shot examples from train only; no reference answers or labels in the prompt.
- [ ] Judge context limited to what the criterion needs.
- [ ] TPR and TNR with counts on dev while iterating; on test once, at the end.
- [ ] Enough labelled failures to estimate TNR at all; say so when there are not.
- [ ] Corrected pass rate with a bootstrap interval, not a raw judge pass rate.
- [ ] Disagreements reviewed with the domain expert; decisions logged; specs and labels versioned together.
- [ ] Judge model ID pinned; revalidated when it changes.

## Summary

Use code for what code can decide, and a judge only where meaning matters. Each judge checks one failure mode, says
PASS or FAIL with a critique, and learns from train examples only. Measure it like a classifier: TPR and TNR on dev
while you improve it, once on test when you are done, and correct any pass rate it produces for its own errors,
with an interval wide enough to be honest. Then keep talking to the domain expert, because the criteria will move.

Next: [the lab](lab.md), then the [exercises](exercises.md) and [quiz](quiz.md). The
[cheat sheet](../../cheatsheets/judges.md) and the [judge prompt template](../../eval-templates/judge-prompt.md)
summarise the method.
