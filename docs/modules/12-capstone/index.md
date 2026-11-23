# 12. Capstone: the eval report

**Goal:** run the whole eval loop on MediaDoctor, from module 1's baseline to an evidence-based improvement, take a
fresh slice through it, and write the result up as a report a stakeholder can act on.

**Estimated time:** 8 hours (lesson 1 h, lab 4.5 h, exercises and self-assessment 1.5 h, presentation 1 h)

By the end of this module you will be able to:

- run every stage of the loop in one command and explain what each stage contributes to a decision;
- choose a slice by evidence, run error analysis on it, read its judges, and say what an experiment on it can and
  cannot show at its sample size;
- write an eval report that follows the [eval report template](../../eval-templates/eval-report.md): a decision,
  three numbers with intervals, scope, data, taxonomy, validated evaluators, results, risks, a recommendation, and a
  reproducible appendix;
- review someone else's report and find its weakest claims;
- present the result to stakeholders in ten minutes;
- publish the report on the course site.

Artifacts: **your capstone eval report** (`uv run mediadoctor-capstone report`), published on your copy of this
site; the fully worked [reference report](../../capstone/index.md); the [grading rubric and self-review
checklist](rubric.md); the [extension options](extensions.md); and a [stakeholder presentation outline](presentation.md).

!!! info "Synthetic-authored model behaviour, real everything else"
    Every number in this module comes from the fixtures earlier modules recorded. The model turns in them were
    written by the course's fixture scripts and are labelled `synthetic-authored`, so the rates show how the method
    behaves, not how Claude Sonnet 5.5 or Haiku 5.5 behave on your system. The pipeline, checks, judges' prompts,
    prices, and statistics are real code. [Make it your own](extensions.md) shows how to re-record live.

## Intuition: an eval only matters if it changes a decision

Every earlier module produced a number. None of them, alone, tells a product owner what to do on Monday. The report
is where the numbers become a decision: ship this, fund that, stop doing the other thing. A media engineer already
knows this shape. A codec comparison is not a table of BD-rate numbers; it is "switch the 1080p ladder to AV1 for
devices with hardware decode, keep HEVC elsewhere, here is the saving, here is the device list we did not test".
The table is the appendix.

So write the report backwards. Start with the decision you are asking for. Keep the three numbers that justify it,
each with an interval, because a decision maker who sees "+23 points" will act on it, and one who sees "+23
[+16, +32]" can also see how sure you are. Then add only what someone needs in order to trust those three numbers:
what you tested, on what data, with which evaluators, how well those evaluators agree with people, and what you did
not test. Everything else goes in the appendix with the commands to reproduce it.

## Step 1: run the whole loop

```bash
uv run mediadoctor-capstone run
```

```text
 1  baseline        ok    v1 passes all three checks on 16/20 queries
 2  tracing         ok    8 traces, 53 spans; weakest trace check evidence_is_real 7/8
 3  error analysis  ok    52/100 traces fail; top mode ignored-tool-output (11)
 4  synthetic data  ok    182 queries; value pairs covered 242/242
 5  judges          ok    tool-grounding TPR 0.90 TNR 0.60 on test (n=25)
 6  statistics      ok    v1->v2 +0.051 [-0.044, +0.146]; 19/37 queries flaky
 7  architecture    ok    best retrieval section+bm25 recall@5 0.81
 8  CI gate         ok    gate pass; mediadoctor-golden 1.0.1, manifest problems 0
 9  monitoring      FLAG  evidence_fail CUSUM alarm +19.7 h after the rollout
10  red team        ok    ASR 0.633 -> 0.033 with guardrails v2, benign FPR 0.050
11  improvement     ok    retry: success 0.898, cost/success $0.00428

11 stages replayed; 1 flagged for the report
```

Each line replays one module's recorded artifacts through that module's own code (`mediadoctor.capstone` imports
`lab01` to `lab11`; nothing is copied). It takes a few seconds and needs no API key. Read it as the table of
contents of your evidence. The stages are not independent: the taxonomy (3) chose what the experiments (11) tried to
fix; the judges (5) and statistics (6) decide how far you can trust the experiment's numbers; the gate (8) is how
the change will ship; monitoring (9) and the red team (10) are what the change does not address.

The flagged stage matters most. Monitoring found a regression in production after the app 4.2.0 rollout, and
nothing in the improvement experiment touches it. A report that leads with "+23 points" and leaves this out would be
correct and misleading.

## Step 2: choose a slice by evidence

A whole-system number hides where the system is weak. The capstone asks you to take one **slice**, a subset of
queries that share something (a topic, a device family, a persona), through the loop again.

```bash
uv run mediadoctor-capstone slices
```

```text
dev success per topic, v1 -> retry (paired 95% CI; small n, read the intervals)

topic              n      v1   retry  diff [95% CI]
audio-focus       12   0.417   0.667  +0.250 [+0.000, +0.500]
av-sync           13   0.769   1.000  +0.231 [+0.000, +0.462]
av1-playback      18   0.611   0.944  +0.333 [+0.111, +0.556]
codec-limits      16   0.812   0.875  +0.062 [+0.000, +0.188]
drm-resolution    15   0.867   1.000  +0.133 [+0.000, +0.333]
hdr-colour        19   0.421   0.789  +0.368 [+0.158, +0.579]
live-stream        9   0.778   1.000  +0.222 [+0.000, +0.556]
mp4-startup        6   0.833   1.000  +0.167 [+0.000, +0.500]

weakest slice under retry: audio-focus
```

Two ways to choose. **By weakness:** the topic where the candidate still does worst (audio focus, 8 of 12), because
that is where the next fix pays. **By risk:** a topic where a wrong answer costs most, such as DRM and Widevine
questions, where a wrong security level sends a customer to the wrong team. The reference report takes the first;
the lab asks you to take the second, so that you meet the opposite problem: a slice that looks solved (15 of 15)
on too few queries to say so.

Look at the intervals before the point estimates. With 6 to 19 queries per topic, only two topics (AV1 and HDR) show
an improvement whose interval excludes zero. The others may have improved too; this data cannot tell.

## Step 3: error analysis on the slice

Module 3's method, scaled down. Read every failing trace in the slice (four, for audio focus under `retry`), write
a note on the first thing that went wrong, and map it to the taxonomy:

```bash
uv run mediadoctor-lab11 trace retry m4q099
```

In the reference report, three of the four survivors are **ignored tool output** and one is a format violation. Two
facts from the report explain why: every audio-focus question in the dataset has no attached evidence (module 4's
`evidence` dimension is `none` for all 12), and the self-check judge flagged all five defective first answers on
this slice, yet only one retry ended correct. On this slice the judge finds the problem and the retry does not
repair it. That is a finding about the fix, not about the judge, and it points at the next experiment: give the
agent a tool or KB section that answers audio-focus questions, instead of asking it to try again.

Be honest about the size: 1 of 5 retries against 6 of 15 overall is not evidence that retries work worse here. It is
a lead, which is all a 12-query slice can give you.

## Step 4: evaluators you can vouch for

Every evaluator in the report needs its validation next to it, in the same table: what it detects, what it was
validated on, its TPR and TNR. Two habits from modules 5 and 7 carry the weight:

- report TPR and TNR, not accuracy: a judge that passes everything on a set that is 85% good is 85% "accurate";
- correct judge-measured rates for judge error when the judge's numbers are the headline, and show the corrected
  interval. In the reference report, the tool-grounding judge's raw pass rate 0.820 becomes 0.840 [0.236, 1.000]:
  25 labelled traces cannot pin a judge's error rate down, and the report says so instead of quoting 0.82.

For a slice, check the judge on the slice too. Judges that are good on average can be poor on one topic.

## Step 5: results with intervals, per case, and per dollar

The template's Results section has four parts, and the reference report shows each:

1. **A table per configuration**: success with a Wilson interval, p50 and p95 latency, cost per task, and cost per
   successful task with a bootstrap interval, plus the pre-registered verdict.
2. **Paired steps**: each kept change against its parent, with the fixed and broken counts. "+0.046 [+0.009,
   +0.093], 5 fixed, 0 broken" says more than "+4.6 points": one broken query would have taken the interval to zero.
3. **The per-case diff**: which queries changed and how they had failed. A reviewer who sees that 12 of the 25 fixes
   were accepted false premises knows which change did the work.
4. **Cost and latency from traces**, median and p90 per trace, with the most expensive traces by id, next to the
   trace-check pass rates, so that a quality gain bought with a latency regression is visible on the same page.

Then the architecture-specific evaluation (module 7's retrieval and RAG numbers), the gate status (module 8), the
monitoring signals (module 9), and the red-team rates (module 10). Each gets two or three sentences and a table; the
reader needs to know that they were measured and what they say about this decision, not every detail.

## Step 6: risks, recommendation, appendix

**Risks and caveats** are where a report earns trust. Name the sample size and what it can detect, judge error,
where the data came from, the metric definitions that differ between modules (module 6's v1 → v2 difference of
+0.051 and module 11's +0.093 measure different things), the failure modes the experiment did not re-measure, and
the distribution shift monitoring found. A stakeholder who later discovers a caveat you knew about stops reading
your reports.

**The recommendation** follows from a rule, not from enthusiasm. The capstone applies module 11's: ship when the dev
interval excludes zero and the one held-out look does not reverse the direction. Next steps are concrete, owned, and
ordered: the 4.2.0 regression first, because it is hurting users now.

**The appendix** makes the report reproducible: the commands, the inputs fingerprint, the golden-set version, and
every trace or case id quoted. Someone who doubts a number should be able to check it in a minute.

## Step 7: spend the held-out look, then publish

```bash
uv run mediadoctor-capstone report --out runs/capstone/report.md            # dev only, as often as you like
uv run mediadoctor-capstone check runs/capstone/report.md                   # self-review against the template
uv run mediadoctor-capstone report --release --out runs/capstone/report.md  # once: reads the held-out split
```

`--release` runs module 8's `HoldoutGuard` and appends the look to `runs/capstone/holdout_log.csv`. If you already
spent the look in lab 11, the replay gives the same numbers, so this is a copy of that look rather than new
information; on a live system you would quote the logged result instead of looking again. Then copy the report
into `docs/capstone/`, add it to the nav, and build the site with `uv run zensical build --strict` (the
[lab](lab.md) has the steps).

## Worked example: the reference report

The [reference report](../../capstone/index.md) is generated by `uv run mediadoctor-capstone report --release --date
2026-11-23` and is checked in CI against a fresh run, so every number on it is current. Read it with the template
beside you:

- **Decision requested** is one paragraph: replace `v1` with `retry`, and fund the follow-ups, starting with the
  4.2.0 regression.
- **Summary** has exactly three bullets, each with intervals: better answers (+0.231 [+0.157, +0.315] on 108 dev
  queries, 25 fixed and 0 broken; held out 0.966 against 0.828), cheaper per success ($0.00428 against $0.00880,
  −51%), and what the change does not fix (the 4.2.0 evidence failures at 16.1%, and audio focus at 8 of 12).
- **Failure taxonomy** shows module 3's ranked modes and then before and after for the four modes module 11
  labelled: accepted false premises fell from 17 to 5 of 108, the largest and most certain change.
- **Evaluators** puts seven evaluators in one table, including the self-check judge inside the retry step (TPR 0.99,
  TNR 0.88) and module 10's injection detector.
- **Results** includes the slice deep-dive: every configuration on audio focus, the modes, the four survivors by
  id, and what 12 queries can detect.
- **Risks** lists eight, including the two that would change the decision if they were wrong: synthetic data, and
  the latency headroom (p95 10.4 s against a 12 s guardrail).

Then read it as a reviewer. [Exercise 2](exercises.md) asks for its three weakest claims; find them before you look.

## Checklist

- [ ] The report opens with the decision requested, in one paragraph.
- [ ] The summary has three bullets, and every number in them has an interval.
- [ ] Scope names the system version, models, prompt versions, dates, and what was out of scope.
- [ ] Data says how every set was built (real, synthetic, or both) and where coverage is thin.
- [ ] The taxonomy has counts and severity, before and after.
- [ ] Every judge appears with its TPR and TNR and what it was validated on; judge-measured headline rates are
      corrected.
- [ ] Results are paired, with fixed and broken counts, a per-case diff, and cost and latency per successful task.
- [ ] The slice deep-dive states what its sample size can and cannot detect.
- [ ] Risks include sample size, judge error, data provenance, distribution shift, and what was not tested.
- [ ] The recommendation follows from a stated rule; next steps are concrete and ordered.
- [ ] The appendix has the commands, the inputs fingerprint or git sha, and every quoted id.
- [ ] The held-out split was read once, and the look is logged.
- [ ] `uv run mediadoctor-capstone check` passes, and the report builds on the site with `--strict`.

## Summary

The capstone runs the whole loop and turns it into a decision. `mediadoctor-capstone run` replays all eleven
earlier modules in seconds; `slices` finds where the candidate is weakest; `report` writes an eval report that
follows the template, with real numbers from every module's artifacts and a slice deep-dive; `check` reviews it
against the template; and `--release` spends the one held-out look. On MediaDoctor the evidence supports shipping
`retry` (+23 points, −51% cost per success), names what it does not fix (a production regression on app 4.2.0, one
remaining injection vector, and audio-focus questions with no evidence to ground on), and says what each slice is
too small to show. That last part is the difference between a report that sells and one that informs.

Continue with the [lab](lab.md), the [exercises](exercises.md), the [self-assessment](quiz.md), the
[rubric and checklist](rubric.md), [Make it your own](extensions.md), and the
[presentation outline](presentation.md). When you are done, the [study plan](../../start-here.md) has suggestions for
what to do next.
