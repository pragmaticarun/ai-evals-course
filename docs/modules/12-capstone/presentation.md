# Presenting to stakeholders

A ten-minute talk built from the eval report. The audience decides; it does not need the method. Use about six
slides, and keep the report open for questions.

## The outline

| # | Slide | Time | What it says (reference report) |
|---|---|---|---|
| 1 | **The ask** | 1 min | "Keep `v1`: none of the six changes we tested earned its place. Fund the app 4.2.0 tool-error investigation." One sentence each. |
| 2 | **Why we believe it** | 2 min | The three summary numbers, each with its interval said aloud: `v1` answers 66% of the 119 dev questions (57% to 74%); the best change we rejected, the v3 prompt, gains 6 points, anywhere from 0 to 12, and on 28 held-out questions gains nothing (anywhere from 11 points worse to 11 better); `v1` is over both guardrails, 15.8 s at p95 against 12 s, and $0.0104 per correct answer against a $0.01 limit (by a hair: the interval reaches $0.009). Say that no change is shown to help, not that none could. |
| 3 | **What we tried** | 1.5 min | The six changes, one line each, with the rule's verdict, and the one that meets the guardrails (`cascade`: as good as `v1` within the noise, 82% cheaper per correct answer) as the next experiment. |
| 4 | **What it does not fix** | 2 min | The production tool-error rise on 4.2.0 (36% of requests, none on 4.1.3), the injection vector guardrails v2 still miss, and the weakest topic (DRM, 7 of 14), where every failure is a question that never names the phone and the grading checks count a request for the device as a failure. Name each owner. |
| 5 | **How sure we are** | 1.5 min | Data is synthetic until re-recorded live; the judges' validation sets hold almost no failures, so how often they pass bad answers is unknown; the `v3` rejection rests on its guardrails and its rejected parent, not on its interval. What would change the decision. |
| 6 | **Next steps** | 1 min | The ordered list from section 9, with owners and the date of the next report. |

Leave the last minutes for questions. If there are none about uncertainty, ask one yourself: "the number I would
check first if I were you is...".

## Habits that help

- **Lead with the decision**, then the evidence. Barbara Minto's pyramid principle is the standard reference for
  this order; engineers default to the opposite (method, results, conclusion) and lose the room by slide three.
- **Say intervals in words.** "Somewhere between no gain and 12 points, probably about 6" lands; "+0.059 [+0.000,
  +0.118]" does not, in a talk. Keep the bracket form on the slide for the people who want it.
- **Show one trace.** A real query, the old answer, the new answer (or, as here, an answer the checks mark wrong
  because the question never named the phone). One concrete example does more than a table,
  and it gives the audience a picture of what "a failure" means.
- **Put the bad news in the middle**, on its own slide, with an owner. Hiding it in the appendix costs you the next
  meeting.
- **One chart, if any:** the accuracy against cost frontier from module 11 (`runs/m11/pareto.svg`) shows the choice
  in one picture.
- **Anticipate the three questions:** "How sure are you?", "What did you not test?", "What happens if we wait?".

## What not to show

The full taxonomy, the judge prompts, the statistics, and the per-module details. They are in the report, and the
report is linked from the last slide. A stakeholder who wants to check a number should be able to find it there in
a minute, which is what the appendix is for.
