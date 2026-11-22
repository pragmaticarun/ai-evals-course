# 3. Error analysis

**Goal:** read traces systematically and turn what you see into a ranked list of failure modes.

**Estimated time:** 7 hours (lesson 1.5 h, lab 4 h, exercises and quiz 1.5 h)

By the end of this module you will be able to:

- review a trace in a fixed order and write a short, specific note about the first thing that went wrong
  (*open coding*);
- group those notes into failure modes with definitions someone else could apply (*axial coding*);
- tell apart tool-call errors, retrieval misses, and failures that compound over several steps;
- count and rank failure modes by how often they happen, how much they hurt, and how easy they are to fix;
- decide when you have read enough (*saturation*) and who should be doing the reading.

Artifacts: your annotation file (`runs/m3_labels.csv`), failure taxonomy sheet v1 (`runs/taxonomy.csv`), and a
Pareto chart (`runs/pareto.svg`).

## Intuition: triage before you fix

If you have worked on an Android app at scale, you have done this already. A crash dashboard with 4,000 reports
is useless until it is grouped by signature: *these 1,900 are the same `IllegalStateException` in the player
release path, these 300 are the OEM codec bug on one chipset*. Once grouped and counted, the next week's work is
obvious. Nobody fixes crashes in the order they arrived, and nobody decides the buckets before seeing the reports.

Error analysis is that triage for an LLM agent, with one difference: agent failures have no stack trace. An answer
that confidently names the wrong decoder looks exactly like an answer that names the right one. A person who knows
the domain has to read the trace and say what went wrong. So the work is:

1. **Look** at a sample of real (or realistic) traces, one at a time.
2. **Write down** what went wrong in each, in plain words. No categories yet.
3. **Group** the notes into a small set of named failure modes.
4. **Count** them and decide what to fix first.

The order matters. Teams that start from a generic list ("hallucination", "helpfulness", "toxicity") measure things
that may not be their problem and miss things that are. In the MediaDoctor traces below, the most damaging failure
is the agent *contradicting its own tool output*, which no generic checklist would name. The categories have to come
out of the traces.

This approach, including the open and axial coding vocabulary borrowed from qualitative research, is the core of
Hamel Husain and Shreya Shankar's teaching on evals; see [Credits](../../credits.md) for where to read it in their
own words.

## The trace set

Module 2 gave MediaDoctor tools and tracing. This module uses a larger set: **100 traces** covering 14 kinds of
question (stuttering AV1, HDR colours, slow progressive starts, A/V offset, codec exhaustion, live-stream recovery,
audio focus, Widevine levels, and API questions). They are run through the real agent loop and tools, and replayed
offline like module 2.

!!! info "Synthetic-authored, like the earlier modules"
    No API key was used to write the course. The model's side of each trace was written by hand, from scenario
    templates, to show realistic behaviour, including planted failures; the requests, tool calls, and tool results
    are produced by the real code. Every fixture record carries `"source": "synthetic-authored"`. The
    **reference annotations** in `data/labels/module03_reference.csv` are synthetic too: they are what a careful
    reviewer would write, generated with some variation in wording. Treat them as one expert's answer key, not
    ground truth. With an API key you can record real runs and do this analysis on Claude's actual behaviour (see
    the lab).

The question ids look like `[MD-4133]`, as if they came from a support queue. The trace ids you will use are
`m3t001` to `m3t100`, in the order you should review them.

## Step 1: read each trace the same way

Reading 100 traces sounds slow. It is about two hours if every trace is read in the same order and you write one
line per trace. The lab's review layout shows a trace like this:

```text
case m3t033   trace 4caafcf041c0   2 model calls   $0.0038
Q: [MD-4133] Why does progressive_late_moov.mp4 have a long startup delay when streamed progressively?

  [1] chat:plan                 in=598 out=38
  [2] execute_tool ffprobe      ERROR  args={"file": "late_moov.mp4"}  ->  Error: media file not found: ...
  [3] chat:answer               in=715 out=84

Answer:
  Likely cause: ffprobe shows the top-level boxes in the order ftyp, free, mdat, moov: the moov index ...
  Next step: Remux with ffmpeg -i in.mp4 -c copy -movflags +faststart out.mp4 to move moov to the front.
  Sources: [tool:ffprobe]
```

A reading order that works:

1. **Question, then answer.** Would you, as the expert, accept this answer? Decide *pass* or *fail*, nothing in
   between. A binary verdict forces a decision; a 1 to 5 score lets you avoid one.
2. **If it fails, walk the steps from the top** and stop at the first step whose output is wrong: a bad tool
   argument, an error nobody handled, irrelevant documents, or a final answer that does not follow from what the
   tools returned. That is the **first upstream failure**.
3. **Write one line** about what you saw. Then move on.

Here the answer is *correct* about faststart, but the ffprobe call failed, so the agent never saw the box order it
quotes. The first thing that went wrong is step 2, the tool call with the wrong file name; everything after it is
built on nothing.

!!! tip "Pass the obvious, fail the specific"
    Spend your time on failures. If an answer is right, grounded, and useful, mark it pass and move on in seconds.
    If you cannot decide, it is usually a fail with a note saying what bothered you.

## Step 2: open coding

**Open coding** means writing free-text notes about each failing trace, in your own words, without forcing them into
categories. Good notes are:

| Good note | Weak note | Why |
|---|---|---|
| says lumen-l3 supports Main 10 + HDR10; codec_caps: profiles [Main], hdr_types [] | hallucination | Says *what* is wrong and *where the evidence is*. "Hallucination" is a conclusion, and covers five different problems. |
| search_kb('sound continues when phone rings') returned av-sync, not audio-focus | bad retrieval | Records the query and the result, so you can later tell a query problem from a retriever problem. |
| ffprobe called on 'late_moov.mp4', errored, answer still cites [tool:ffprobe] | wrong | Names the step and the consequence. |
| next step 'Check the codec documentation.' is not actionable | answer could be better | Points to the exact line. |

Three habits keep notes useful. Note **what you observed, not the fix** (the fix comes later, and often is not what
you expect). Note the **first** failure, and mention later ones only if they are independent. And **do not look at
the reference labels** until you have done your own pass; the point is to see what *you* see.

## Step 3: axial coding

Once you have 30 to 50 notes, read them all together and group them. This is **axial coding**: you look for notes
that describe the same underlying problem, give each group a name, and write a one-sentence definition that someone
new could apply to a trace without asking you.

Here is a sample of the reference notes for the first 30 traces, and where they ended up:

| Note (open code) | Failure mode (axial code) |
|---|---|
| says moov is at the front; ffprobe boxes are ftyp, free, mdat, moov (moov last) | ignored-tool-output |
| answer contradicts the tool output: reads NO_MEMORY as Java heap OOM; log says 'max instances reached' | ignored-tool-output |
| says lumen-l3 is L1; codec_caps shows widevine_security_level L3 | ignored-tool-output |
| uses the hdcpLevel property for security level; that's HDCP, should be securityLevel | wrong-api-detail |
| says isHardwareAccelerated() is API 21; it is API 29 | wrong-api-detail |
| retrieval missed behind-live-window: query 'player crashes when reopened' pulled audio-focus | retrieval-miss |
| wrong file name 'faststart.mp4' -> tool error -> agent gave up and guessed | wrong-tool-args |
| 3 search_kb calls returning the same docs before answering; answer itself ok | redundant-steps |
| no tool calls although the question names atlas-a1 / av1_2160p60.mkv; generic answer | skipped-investigation |

The first 30 traces have 16 failures that collapse into **6 modes**: ignored-tool-output (5), retrieval-miss (4),
wrong-api-detail (3), wrong-tool-args (2), redundant-steps (1), skipped-investigation (1).

Decisions you will face while grouping:

- **Split or merge?** Split when the fix differs. "Wrong API level" and "wrong method" both get fixed the same way
  (ground the answer in the knowledge base), so they share *wrong-api-detail*. "Contradicts the tool" is fixed
  differently from "never called the tool", so those are two modes.
- **Name the behaviour, not the topic.** "HDR problems" is a topic; failures inside it differ. *ignored-tool-output*
  covers HDR, Widevine, and box order alike.
- **Write the definition before you count.** If you cannot write one sentence that separates two modes, merge them.
- **Expect the definitions to change.** Reading more traces sharpens what you think "wrong" means. Shankar and
  co-authors call this *criteria drift*: graders' criteria shift as they see outputs. Re-label earlier traces when
  a definition moves.

An LLM can help here by proposing groupings of your notes, but treat its output as a suggestion: you know which
differences matter for the fix.

The result is a definitions file, `data/labels/module03_modes.toml` in the reference, with a severity, a fixability,
and an expected detector for each mode. Module 5 turns the top modes into evaluators; the `detector` field is your
first guess at which ones a code check can catch and which need a judge.

## Three kinds of failure worth special attention

### Tool-call errors

Not every tool error is a failure. The `errors` command lists all 12 failed tool calls in the set and what happened
next:

| What happened after the error | Traces | Verdict |
|---|---|---|
| Retried with the right name and continued | 4 | **pass**: the error message listed valid names and the agent used it |
| Gave up and hedged ("I could not inspect ..., so this is a guess") | 3 | fail: wrong-tool-args |
| Cited the tool anyway, as if it had worked | 5 | fail: wrong-tool-args *and* fabricated-evidence |

All 12 come from near-miss names: `late_moov.mp4`, `Lumen L3`, `atlas_a1`, `live_resume.log`. That is a strong hint
about the fix: the tool, not the model, is the cheapest place to act (accept unambiguous near-misses, or return a
"did you mean" in the error).

### Retrieval misses

The `retrieval` command checks each `search_kb` call against the document the case needs. 56 of 63 retrievals
return it; 7 do not, and in each of those the answer follows the wrong document. For example, `'sound continues when
phone rings'` matches nothing about audio focus in the naive keyword retriever and returns the A/V sync note, so the
agent diagnoses clock drift for a phone-call problem.

When you see a miss, ask one question: **would a better query have found the document?** If yes, the problem is
query formulation (the model's step, fixable by prompt or query rewriting). If no, it is the retriever or the
knowledge base (coverage, ranking, chunking), which module 7 measures properly. Record which one in your note.

### Compounding failures

In a multi-step trace, one early mistake can produce several visible symptoms. In `m3t050`, `codec_caps` is called
with `"Lumen L3"`, fails, the agent probes the clip, and then states the lumen-l3's decoder limits as if it had read
them. Two modes apply (*wrong-tool-args* and *fabricated-evidence*), but there is one first upstream failure: the
tool call. Record the first failure in `first_upstream`, and tag independent failures too. Fixing upstream often
removes downstream symptoms, so the `first_upstream` counts tell you *where* in the pipeline to work:

| First upstream step | Failing traces |
|---|---|
| `chat:answer` (the final answer misuses good evidence) | 24 |
| `chat:plan` (skipped tools, redundant calls) | 13 |
| `retrieval` | 7 |
| `execute_tool ...` (bad arguments) | 8 |

Multi-step traces also fail on cost rather than correctness. The five traces with redundant searches cost $0.0136
on average, against $0.0059 for passing traces: 2.3 times more for the same answer.

## Step 4: count and prioritise

With every failing trace coded, count how many traces show each mode (a trace with two modes counts once for each).
The reference result for all 100 traces:

| # | Failure mode | Traces | Severity | Priority (traces × severity) | Fixability | Most common first upstream |
|---|---|---|---|---|---|---|
| 1 | ignored-tool-output | 11 | 3 | 33 | medium | chat:answer |
| 2 | fabricated-evidence | 8 | 3 | 24 | easy | execute_tool ffprobe |
| 3 | skipped-investigation | 8 | 2 | 16 | easy | chat:plan |
| 4 | wrong-tool-args | 8 | 2 | 16 | easy | execute_tool ffprobe |
| 5 | wrong-api-detail | 8 | 2 | 16 | medium | chat:answer |
| 6 | retrieval-miss | 7 | 2 | 14 | medium | retrieval |
| 7 | redundant-steps | 5 | 1 | 5 | easy | chat:plan |
| 8 | vague-next-step | 3 | 1 | 3 | easy | chat:answer |
| 9 | format-violation | 2 | 1 | 2 | easy | chat:answer |

52 of 100 traces fail. How to read the table:

- **Frequency alone is not priority.** A wrong decoder claim sends an engineer down the wrong path for a day; a
  missing `Sources:` line costs nobody anything. Severity (1 annoying, 2 misleading or costly, 3 harmful or
  trust-breaking) is a judgement call, which is why the domain expert makes it.
- **Fixability breaks ties and finds quick wins.** *fabricated-evidence* is rank 2 and easy: the module 2
  `evidence_is_real` check catches all 8 today and can block them. *wrong-tool-args* is rank 4 and easy (fix the
  tool). Together they touch 11 of the 52 failing traces, and both fixes fit in an afternoon. *ignored-tool-output* is rank 1 but needs prompt
  work and a judge to measure it, which is what modules 5 and 11 are for.
- **The Pareto chart is flatter than the usual 80/20.** The top three modes cover 45% of occurrences, not 80%. That is
  common for a young agent: many separate problems, none dominant. When the chart is flat, severity and fixability
  decide; when one bar towers, frequency does.

The priority formula is deliberately simple. Some teams use count × severity ÷ effort, or weight by how many users
ask that kind of question. Whatever you use, write it down in the taxonomy sheet so the ranking can be argued with.

## When to stop: saturation

You stop reading when new traces stop teaching you anything: no new failure modes and no changes to the definitions.
Qualitative researchers call this **theoretical saturation**. The reference curve for this trace set:

```text
traces reviewed  distinct modes
             10    4  ####
             20    6  ######
             30    6  ######
             40    7  #######
             50    9  #########
             60    9  #########
             70    9  #########
             80    9  #########
             90    9  #########
            100    9  #########

last new mode appeared at trace 48; 52 traces since then without a new mode
```

Notice traces 20 to 30: no new modes for ten traces in a row. Stopping there would have looked reasonable, and would
have missed **fabricated-evidence**, the rank 2 mode, first seen at trace 33. Rare, severe modes show up late. Two
rules of thumb follow:

- Read **at least 100 traces** on a first pass (the number Husain and Shankar recommend), spread across the kinds of
  question you get.
- Then keep going until **about 20 consecutive traces** add no new mode and change no definition.

Saturation is not permanent. A new prompt, model, tool, or user group brings new failures. Repeat the analysis after
every significant change; it gets faster each time because the definitions exist.

## Who should label?

One person who knows the domain should own the verdicts and the definitions: Husain calls this role the
**benevolent dictator**. For MediaDoctor that is someone who can tell whether `c2.android.av1.decoder` at
1920x1080 and 30 fps really explains a 4K stutter, which a general annotator cannot. One owner keeps the
definitions consistent; others can review traces, argue about definitions, and flag disagreements, but one person
decides.

Avoid two common substitutes. **Crowd or generalist annotators** can check format but not whether an API level is
right. **An LLM labelling on its own** has the same blind spots as the agent it is judging, and you have no way to
know its error rate yet. Module 5 builds LLM judges and measures them against the expert's labels; that is only
possible because the expert's labels exist.

## Automatic signals: a reading aid, not a label

The lab's `signals` command flags traces using cheap checks from module 2: tool errors, citations without a
successful tool call, no tool calls, repeated retrievals, step budget, retrieval misses, and format. On this set:

| | Traces |
|---|---|
| Flagged by at least one signal | 34 |
| Failing traces with **no** signal | 22 (ignored-tool-output, wrong-api-detail, vague-next-step) |
| Flagged but passing (recovered tool errors) | 4 |

Signals are useful for choosing what to read first, and several will become evaluators. But 22 of the 52 failures,
including all 11 of the top-ranked mode, are invisible to them. Only reading finds those.

## Checklist

- [ ] At least 100 traces reviewed, pass or fail each, in a fixed order
- [ ] A specific note on every failure, naming the first upstream step
- [ ] Failure modes with one-sentence definitions, severity, and fixability
- [ ] Every failing trace coded with at least one mode; definitions updated as they drifted
- [ ] A ranked list and a Pareto chart, with the priority rule written down
- [ ] Saturation reached: about 20 traces in a row with nothing new
- [ ] One named owner for the labels

## Summary

Error analysis is triage: look at the traces, write down what went wrong in plain words, group the notes into
failure modes that come from your data, count them, and fix what matters most. Label the first upstream failure,
keep tool errors that recovered separate from those that did not, and ask of every retrieval miss whether a better
query would have helped. Rank by frequency and severity, use fixability to find quick wins, and keep reading until
nothing new appears. One domain expert owns the result.

**Next:** the [lab](lab.md). Then module 4 generates more varied test questions, so the next error analysis is not
limited to what users happened to ask.
