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
    `check_investigated` agrees with the labels on 136 of 137 traces. The one it misses is a question with no file,
    device, or log ("audio from our app continues over incoming calls"): the agent called nothing and answered from
    memory, and the check's definition only looked for file, device, and log tools. The check was precise; its
    definition was narrower than the expert's. Exercise 4 fixes it.

## Step 2: one judge per failure mode, binary, with a critique

A judge that checks "is this a good answer?" mixes several failure modes, so when it fails you cannot tell why, and
when you fix one mode its score barely moves. Write **one judge per failure mode** and make each one answer a
narrow question.

Make the verdict **binary**. A 1 to 5 scale feels more informative, but nobody can say what separates a 3 from a 4,
two reviewers will not agree on it, and to use the score you have to pick a threshold anyway. The lab shows what
happens: the threshold that matches human labels best on dev (score 3 or more) catches none of the failures on
test. If you want to track gradual progress, use several binary checks.

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
| `[[example]]` | few-shot examples: a trace id, a verdict, a critique | a vague next step (FAIL), a request for details (PASS), a specific API call (PASS) |

```bash
uv run mediadoctor-lab05 show next-step     # the full prompt the judge model receives
```

Four rules for the content:

1. **Examples come from the train split only.** Dev is for measuring changes, test is for the final report. A
   few-shot example from dev makes your dev numbers too good; one from test makes the final report meaningless.
   `mediadoctor-lab05 leaks` checks every spec.
2. **Include the borderline cases.** The hard part of "actionable" is "send me the device model": is asking a
   next step? Decide, write it into PASS or FAIL, and add an example.
3. **Give the judge only the context it needs.** The tool-grounding judge needs tool results; the next-step judge
   does not, and extra context can distract it. Test such choices against labels rather than guessing.
4. **Fix the output schema.** JSON with `critique` and `verdict`. `parse_verdict` accepts code fences and
   surrounding text, and anything it cannot parse is counted separately and treated as FAIL, never guessed.

## Step 4: validate against human labels

### The labelled set

The lab runs MediaDoctor on every dataset v1 query that matches a module 3 scenario: 137 traces, split the way
dataset v1 is split (71 train, 37 dev, 29 test). The reference labels in `data/labels/module05_reference.csv` give
each trace a verdict and failure modes. For one judge, the human label is per criterion: a trace is a human FAIL
for the tool-grounding judge if and only if it was tagged `ignored-tool-output`.

!!! info "Synthetic-authored, labelled as such"
    No API key was used to write the course. The agent traces are scripted from the module 3 scenarios, the
    reference labels are written from templates, and the judges' outputs are written by a script that follows each
    judge's labels except for documented, deterministic error patterns (`scripts/author_module05_fixtures.py`).
    Every fixture record carries `"source": "synthetic-authored"`. Treat the numbers as a worked example of the
    method, not as measurements of Claude.

### TPR and TNR

Take PASS as the positive class:

- **TPR** (true positive rate): of the traces a human passed, the share the judge passed.
- **TNR** (true negative rate): of the traces a human failed, the share the judge failed.

Report both, with their counts, never just accuracy or agreement. A judge that passes everything agrees with the
humans on every passing trace; if 85% of traces pass, it scores 85% agreement and catches nothing. TNR is usually
the number that matters, because catching failures is the judge's job, and it is usually measured on few traces.

### Worked example: the tool-grounding judge

Version 1 of the tool-grounding judge has two few-shot examples from train: one answer that contradicts
`codec_caps`, and one that agrees with it. On the dev split:

```text
$ uv run mediadoctor-lab05 judge tool-grounding --version v1 --split dev
tool-grounding@v1      dev   n=33 (human pass 27, fail 6)  TPR 0.96 (26/27)  TNR 0.33 (2/6)  agreement 0.85
```

Agreement 0.85 looks acceptable. TNR 0.33 says the judge misses two thirds of the failures it exists to catch.
Read the disagreements:

```text
$ uv run mediadoctor-lab05 disagreements tool-grounding --version v1
  m4q158  judge PASS, human FAIL: It matches what the user reported, and I found no statement in the answer
          ("The lumen-l3 has a hardware AV1 decoder that handles 4K60, so the stutter must come fro...") that
          the codec_caps and ffprobe output contradicts.
  ...
```

Four of the five disagreements are the same: the user stated a wrong fact ("the lumen-l3 has a hardware AV1
decoder"), the answer repeated it, and the judge treated agreement with the user as agreement with the evidence.
That is a gap in the prompt, not random noise. Version 2 adds one sentence to the FAIL definition (agreeing with the
user does not make a claim true) and two few-shot negatives of exactly this kind, both from train:

```text
tool-grounding@v2      dev   n=33 (human pass 27, fail 6)  TPR 0.89 (24/27)  TNR 1.00 (6/6)  agreement 0.91
```

TNR rose to 1.00, and TPR fell from 0.96 to 0.89: the judge became stricter, and now fails three correct answers
for claims it calls "unsupported" rather than contradicted. That trade is a decision for the domain expert
(see alignment, below). We stop iterating, and run the test split **once**:

```text
$ uv run mediadoctor-lab05 validate --split test
tool-grounding@v2      test  n=25 (human pass 20, fail 5)  TPR 0.90 (18/20)  TNR 0.60 (3/5)  agreement 0.84
false-premise@v1       test  n=29 (human pass 24, fail 5)  TPR 0.96 (23/24)  TNR 0.60 (3/5)  agreement 0.90
next-step@v1           test  n=29 (human pass 25, fail 4)  TPR 0.92 (23/25)  TNR 1.00 (4/4)  agreement 0.93
```

Test TNR is 0.60, not the 1.00 seen on dev. Partly that is what tuning on dev does: six dev failures were enough to
fit, not enough to generalise. Mostly it is sample size: 3 of 5 is consistent with a true TNR anywhere from
about 0.25 to 0.9, and 6 of 6 with anything above about 0.6 (95% Wilson intervals, module 6). This is the honest number, and it is the one to report. If it is not good enough,
the fix is more labelled failures, a new dev round, and a *new* test set, not another look at this one. (The
fixtures for tool-grounding v1 on test do not exist; the test refuses to run it.)

Hamel Husain and Shreya Shankar recommend aiming for at least 50 passing and 50 failing labelled examples per
judge. Our 5 test failures per judge are far below that, and the next section shows what it costs.

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

The lab treats module 3's 100 traces as new, unlabelled traffic, runs the final tool-grounding judge on the 89 that
have tool output, and corrects with the test-split TPR and TNR:

```text
$ uv run mediadoctor-lab05 estimate
judge tool-grounding@v2 on test: n=25 (human pass 20, fail 5)  TPR 0.90 (18/20)  TNR 0.60 (3/5)  agreement 0.84
observed pass rate 0.820 on 89 unlabelled traces; corrected 0.840, 95% CI [0.236, 1.000] (1913 bootstrap draws, judge error from 25 labelled traces)
true pass rate from the module 3 reference labels: 0.876
```

Because module 3 has reference labels, we can check: the corrected 0.840 is closer to the true 0.876 than the raw
0.820, and the interval contains it. But the interval runs from 0.24 to 1.00. With 5 labelled failures the judge's
TNR is so uncertain that some resamples make it barely better than chance, and the correction explodes. The
interval is not a bug; it is the cost of 5 failures, stated honestly. Exercise 3 shows how it narrows with more
labels. Module 6 builds on this with Wilson intervals, paired comparisons, and sample-size planning.

The same idea is implemented, with a clear write-up, in the open-source
[judgy](https://github.com/ai-evals-course/judgy) package from Hamel Husain and Shreya Shankar's course; see
[Credits](../../credits.md).

## Aligning with the domain expert

Validation numbers say how often the judge disagrees with the labels. Alignment is what you do with each
disagreement. Sit down with the domain expert (in module 3's terms, the benevolent dictator) and sort every dev
disagreement into one of three piles:

1. **The judge is wrong.** Fix the prompt: a sharper definition, a missing borderline case, a few-shot example of
   the kind it gets wrong, or different context. The tool-grounding v1 misses were this kind.
2. **The label is wrong.** It happens: the expert was tired, or read past a number. Fix the label, and note it.
3. **The criterion is unclear.** Both readings are defensible. Tool-grounding v2 fails `m4q004`, saying it could
   not find the decoder claim ("Main10HDR10") in the tool output. That part is a judge error: `codec_caps` lists
   it. But the same answer also blames "most likely a TextureView compositing through the GPU", which no tool
   checked. Is an *unsupported* claim a grounding failure, or only a *contradicted* one? The expert decides,
   writes the answer into PASS or FAIL, adds an example, and relabels if the decision changes earlier labels.

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
