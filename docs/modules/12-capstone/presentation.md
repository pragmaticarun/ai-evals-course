# Presenting to stakeholders

A ten-minute talk built from the eval report. The audience decides; it does not need the method. Use about six
slides, and keep the report open for questions.

## The outline

| # | Slide | Time | What it says (reference report) |
|---|---|---|---|
| 1 | **The ask** | 1 min | "Ship `retry` in place of `v1`, and fund the app 4.2.0 investigation." One sentence each. |
| 2 | **Why we believe it** | 2 min | The three summary numbers, each with its interval said aloud: 90% of tasks right instead of 67% (+23 points, at least +16); 51% cheaper per correct answer; held-out check consistent. |
| 3 | **What changed** | 1.5 min | The chain `v1` → `v2` → `v3` → `v3-cache` → `retry`, one line per step, and one example query that used to fail and now passes (an accepted false premise). |
| 4 | **What it does not fix** | 2 min | The production regression on 4.2.0 (16% evidence failures), the remaining injection vector, and the weakest topic. Name each owner. |
| 5 | **How sure we are** | 1.5 min | Data is synthetic until re-recorded live; judges are imperfect (the weakest fails only 60% of bad answers); the last step rests on five queries. What would change the decision. |
| 6 | **Next steps** | 1 min | The ordered list from section 9, with owners and the date of the next report. |

Leave the last minutes for questions. If there are none about uncertainty, ask one yourself: "the number I would
check first if I were you is...".

## Habits that help

- **Lead with the decision**, then the evidence. Barbara Minto's pyramid principle is the standard reference for
  this order; engineers default to the opposite (method, results, conclusion) and lose the room by slide three.
- **Say intervals in words.** "At least 16 points better, probably about 23" lands; "+0.231 [+0.157, +0.315]" does
  not, in a talk. Keep the bracket form on the slide for the people who want it.
- **Show one trace.** A real query, the old answer, the new answer. One concrete example does more than a table,
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
