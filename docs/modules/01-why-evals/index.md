# 1. Why evals

**Goal:** replace "it looked fine when I tried it" with a loop you can repeat: analyze, measure, improve.
**Estimated time:** 4 hours (lesson 1 h, lab 1.5 h, exercises and quiz 1.5 h).

By the end of this module you will be able to:

- explain why testing an LLM system differs from testing deterministic code, and what carries over;
- tell apart the three kinds of evaluator (code checks, model judges, human review) and know when to reach for each;
- describe the analyze, measure, improve loop and where engineers and product owners each fit in it;
- run the course's seed agent fully offline from recorded responses, and read your first eval numbers critically.

---

## Intuition: you are testing a distribution, not a function

You already know how to test a codec wrapper. Given this input buffer, you expect exactly these output bytes,
and a single mismatch is a bug. An LLM system breaks that contract in three ways:

1. **Many right answers.** "Use a SurfaceView" and "Switch the output to a SurfaceView instead of a TextureView" are both
   correct. Exact-match assertions on prose are almost always the wrong tool.
2. **Many ways to be wrong.** An answer can be badly formatted, cite the wrong document, be correct but useless, be
   fluent and confidently false, or leak something it should not. These are different *failure modes*, and they need
   different detectors.
3. **The output is a sample.** The same prompt can give different answers across runs and model versions. You are
   always measuring a rate over a set of inputs, never a single yes or no.

So the unit of testing shifts. In place of "does function f return y for x", you ask:
**on a representative set of inputs, how often does each failure mode occur, and is that rate going down?**
An *eval* is any repeatable procedure that answers part of that question.

Two habits from systems engineering carry over directly and matter more than any framework:

- **Look at the actual outputs.** For media work that means reading the logcat before guessing; here it means
  reading traces and answers before choosing metrics. Metrics picked before you have looked at the data tend to
  measure what is easy rather than what is broken.
- **Make runs reproducible.** A flaky test suite gets ignored. This course records every model response under a
  hash of the exact request and replays it, so a test run is deterministic and needs no API key.

## The loop: analyze, measure, improve

Hamel Husain and Shreya Shankar frame eval work as a cycle of analyzing, measuring, and improving
([credits](../../credits.md)). This course is organized around the same cycle, in our own words:

| Step | Question it answers | What you produce | Where in this course |
|---|---|---|---|
| **Analyze** | What is going wrong, and how often? | Notes on real outputs, then a ranked list of failure modes | Modules 2 to 4 |
| **Measure** | Can I detect each failure mode automatically and trust the number? | Code checks, validated judges, numbers with uncertainty | Modules 5 and 6 |
| **Improve** | Did my change fix the failure without breaking anything else? | Experiments with before and after numbers | Modules 7 to 11 |

The loop is never finished. Every improvement changes the outputs, which means new failure modes to analyze. CI
(module 8) and production monitoring (module 9) are what keep the loop turning without heroics.

!!! tip "The most common mistake"
    Jumping straight to "measure": adopting a generic metric such as "helpfulness 1 to 5" or an off-the-shelf
    hallucination score before reading any outputs. The number moves, nobody knows what it means, and nobody acts on it.
    Analyze first.

## Three kinds of evaluator

| Evaluator | Good for | Cost | Trust it when |
|---|---|---|---|
| **Code check** (assertion, regex, schema, unit test) | Format, required fields, citations that must exist, length, forbidden strings, valid tool arguments | Free and instant | Always, once the check itself is tested |
| **Model judge** (LLM-as-judge) | Fuzzy criteria a regex cannot express: "the next step is actionable", "the answer stays grounded in the cited doc" | Cents per case | Only after you have compared it with human labels (module 5) |
| **Human review** | Defining what good means, discovering new failure modes, labeling data that judges are validated against | Your time, the scarcest resource | It is the ground truth, but write down the criteria so it stays consistent |

Hamel's essay [Your AI Product Needs Evals](https://hamel.dev/blog/posts/evals/) describes a similar layering, from
cheap assertions up to human and model review and then A/B tests. The rule of thumb we use: **write a code check
whenever you can, a judge when you must, and spend human time on discovering failures and labeling, not on
re-grading the same thing every release.**

## Engineers and product owners

Evals are where engineering and product decisions meet, so it helps to be explicit about who owns what.
On a one-person project you hold both roles; it is still worth knowing which hat you have on.

| Activity | Engineer | Product owner / PM / domain expert |
|---|---|---|
| Decide what "good" means for users | Contributes examples | **Owns** it, and is the person whose judgment a judge must match |
| Read traces, name failure modes | Does it together with the domain expert | Does it, and has the final say on severity |
| Build tracing, datasets, checks, judges, CI | **Owns** | Reviews the criteria in judge prompts |
| Validate judges against labels | **Owns** the measurement | Supplies or reviews the labels |
| Decide whether a change ships | Presents numbers with uncertainty | **Decides** using them and the business trade-offs (accuracy, latency, cost) |

Two practical consequences. First, the person who labels ground truth should be someone who knows the domain; for
MediaDoctor that is a multimedia engineer, which is why this course is a good fit for you. Second, an eval
nobody outside engineering can read does not change decisions. The capstone (module 12) is a report written for the
product side.

## Meet MediaDoctor (seed version)

The running project is **MediaDoctor**, an assistant that answers Android and multimedia debugging questions:
HDR output, MediaCodec errors, AV1 support, live-stream errors in Media3, audio focus, A/V sync, Widevine levels, MP4
layout. In module 1 it is deliberately simple:

1. a naive keyword retriever picks the two best-matching notes from an 8-document knowledge base (`data/kb/`);
2. one Claude call (the `agent` model in `config/models.toml`) answers in a fixed format:

```text
Likely cause: ...
Next step: ...
Sources: [kb:<doc-id>]
```

Module 2 turns it into a tool-using agent with tracing. Keeping it simple now means the failures are easy to see.

## Worked example: the prompt change that looked like a fix

You run MediaDoctor on 20 realistic questions (`data/datasets/module01_queries.jsonl`) and add three code checks:

- `format`: the three labelled lines are present and in order;
- `cites_kb`: at least one `[kb:<id>]` citation, and every cited id exists in the knowledge base;
- `length`: at most 120 words.

With prompt **v1**, 16 of 20 answers pass all three checks. Reading the failures:

| Case | Failed check | What actually happened |
|---|---|---|
| q07 | length | A correct but rambling answer about a live-stream error, 142 words |
| q18 | length | Same pattern: a correct explanation of MP4 index placement, padded with background, 135 words |
| q15 | format | The `Next step:` line is missing |
| q11 | cites_kb | The answer honestly says the context does not cover the question and cites nothing |

Two long answers feel like the obvious problem, so you write prompt **v2**: "Be brief... keep the whole answer under
60 words." You rerun:

```text
== prompt v1 ==            == prompt v2 ==
  format     19/20           format     16/20
  cites_kb   19/20           cites_kb   16/20
  length     18/20           length     20/20
  ALL        16/20           ALL        15/20

fixed by v2:  q07, q18
broken by v2: q03, q09, q14
```

The two answers you were looking at got fixed. Three answers that used to be fine now drop their `Sources:` line,
which is why both `format` and `cites_kb` fail on them. Overall, v2 is *worse*: 15 of 20 against 16 of 20. Without
the fixed set of 20 cases you would have shipped v2, happy that the long answers were gone.

Three more lessons are hiding in the same run:

1. **q11 is not a prompt problem.** The retriever never fetched the audio-focus note, so the model had nothing to cite.
   The check fails for the right reason, but the root cause is upstream. Finding the first thing that went wrong is
   the core skill of error analysis (module 3), and retrieval gets its own evals in module 7.
2. **q05 passes every check and is wrong.** It says Android 10 made hardware AV1 decoding mandatory and advises shipping AV1 to
   every Android 10+ device. The knowledge base says the opposite: Android 10 added a *software* decoder, and hardware support
   depends on the SoC. Code checks verify shape, not truth. You only catch this by reading outputs, and later with a
   validated judge (module 5).
3. **20 cases is a small sample.** A one-case difference (16 vs 15) is well within noise. The per-case diff is
   the more useful view, because it names three answers to read, but it does not make the difference real: each
   case ran once, and module 6 shows that about half of a set of queries can flip between two runs of the *same*
   prompt. What the diff tells you is where to look. Reading q03, q09, and q14 shows the same cause in all three
   (the length instruction pushed out the `Sources:` line), which is evidence about the prompt; the count is not.
   Module 6 covers when an aggregate difference means something, and how to measure run-to-run flips.

!!! info "About the recorded responses"
    The module 1 fixtures were authored by hand in the exact Messages API response format, so that the lab runs with no
    API key and the planted failures are reproducible. Each record is labelled `"source": "synthetic-authored"`.
    When you re-record with your own key (`EVALS_LLM_MODE=record`), you get real Claude answers. They will differ,
    and the counts above will change, which is a good exercise in itself: rerun the comparison and read what changed.

## Summary

- Evaluate failure modes as rates over a representative set of inputs, not single outputs.
- Analyze before you measure; measure before you improve; then repeat.
- Code checks first, judges for fuzzy criteria (validated against humans), human time for discovery and labels.
- A fixed case set and a per-case diff catch regressions that an aggregate number or a spot check would hide.

The [eval loop cheat sheet](../../cheatsheets/eval-loop.md) puts this module on one page.

**Next:** the [lab](lab.md) runs this worked example on your machine.
