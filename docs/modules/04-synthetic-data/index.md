# 4. Starting with no data: synthetic queries

**Goal:** generate realistic, varied test traffic before MediaDoctor has real users, and know exactly what it can
and cannot tell you.

**Estimated time:** 6 hours (lesson 1.5 h, lab 3 h, exercises and quiz 1.5 h)

By the end of this module you will be able to:

- choose the *dimensions* along which real questions differ, and write rules that remove impossible combinations;
- generate *tuples* (one value per dimension) with full, random, stratified, or pairwise coverage, and say what
  each costs;
- turn tuples into natural-language queries with a cheap model, in a second step, and make them sound like people;
- find near-duplicates, measure diversity, and print coverage matrices that show missing slices;
- freeze a versioned dataset with train, dev, and held-out splits that do not leak into each other;
- seed the process with real queries once they arrive, and say why synthetic data is a starting point, not a
  ground truth.

Artifacts: dataset v1 (`data/datasets/module04_v1.jsonl` with its manifest), a coverage report, and the module 3
analysis repeated on the new dev split.

## Intuition: structure first, then phrasing

Ask a model for "50 diverse, realistic test questions about Android media playback" and you get fluent,
plausible questions that all come from the same imagined person: *How do I check at runtime whether a device has a
hardware AV1 decoder?*, *What is the difference between MediaCodec.reset() and release(), and when should I call
each?*, *Why does HDR10 content look grey on some devices but correct in Photos?* Each sentence is different, so a
duplicate check passes them. But almost every one is a clean, capitalised question from an expert developer, none
names a file, device, or log, and the topics arrive by chance: the course's naive set has one live-stream question
in 50, and 22 of its questions match none of MediaDoctor's eight topics.

If you have written test plans for a media player, you already know the fix. Nobody tests a decoder by asking for
"some videos". You list the axes that matter (codec, profile, resolution, container, device class), decide which
combinations to cover, and only then pick or make the clips. Synthetic queries work the same way:

1. **Dimensions**: write down the ways real questions differ, with a few values each.
2. **Tuples**: pick combinations of values, on purpose, so every slice you care about is present.
3. **Queries**: for each tuple, ask a model to write the one message that person would send.
4. **Checks**: remove near-duplicates, measure diversity and coverage, then freeze the set with splits.

The separation matters because the two steps fail differently. Choosing *what* to test is a coverage problem, and
code is good at it. Writing *how* a person would say it is a language problem, and a small model is good at it as
long as each call gets one concrete situation.

This is the approach Hamel Husain and Shreya Shankar teach for starting evals without traffic: define dimensions
from your failure hypotheses, write some tuples by hand, then generate tuples and queries in two separate steps
(see their FAQ entry on [generating synthetic data](https://hamel.dev/blog/posts/evals-faq/what-is-the-best-approach-for-generating-synthetic-data.html)
and [Credits](../../credits.md)). This module builds that idea into code and adds coverage, deduplication, and
split checks.

## Step 1: choose dimensions

A dimension is useful if changing its value is likely to change whether MediaDoctor gets the answer right. Start
from failure hypotheses, not from a list of everything you could vary. Module 3 gave us real hypotheses: the agent
ignores tool output, cites tools it never called, and retrieves the wrong note. Questions that push on those are the
ones with evidence to inspect, and the ones that give the agent a reason to skip it.

MediaDoctor's dimensions live in `config/synth/mediadoctor.toml`:

| Dimension | Values | Why it might change the outcome |
|---|---|---|
| `persona` | app-developer, media-engineer, qa-tester, support-agent | Vocabulary and framing: a bug ticket, a relayed customer complaint, a precise API question |
| `topic` | av1-playback, hdr-colour, mp4-startup, av-sync, codec-limits, live-stream, audio-focus, drm-resolution | Which tools and knowledge-base notes are needed |
| `goal` | diagnose, how-to, check | "Why is it broken", "how do I", "will this work on X" need different answers |
| `evidence` | none, media-file, device, file+device, log | Whether there is something the agent *must* inspect |
| `expertise` | expert, intermediate, novice | Experts name APIs; novices describe symptoms, with typos |
| `ambiguity` | clear, missing-detail, false-premise | Does the agent ask, guess, or repeat a wrong belief? |

Three rules of thumb kept this list short:

- **Each dimension is one kind of variation.** "Hard question" is not a dimension; it mixes expertise, evidence,
  and ambiguity, and you could not tell which one caused a failure.
- **Values are things you can write a query for.** "Novice" is concrete (lower case, typos, symptoms). "Typical
  user" is not.
- **Three to six values.** More values multiply the space faster than they add insight. You can split a value
  later if failures cluster inside it.

`ambiguity` deserves a note, because it is the dimension people forget. Real users leave things out ("our
trailer stutters on the test phone") and state wrong beliefs as facts ("the lumen-l3 has a hardware AV1 decoder,
so it's not that"). A synthetic set made only of clear, well-posed questions will make any agent look good.

### Rules: not every combination makes sense

The full product is 4 × 8 × 3 × 5 × 3 × 3 = 4,320 tuples, and many are nonsense. There is no log for an audio-focus
question in our data. A Widevine level is a property of a device, not a clip. "Check whether this works" needs a
device to check against. A support agent relaying a customer report does not write expert-level questions.
Rather than filter by hand, write the constraints down as data:

```toml
[[exclude]]
when = { topic = "audio-focus" }
forbid = { evidence = ["media-file", "device", "file+device", "log"] }
reason = "audio focus has no clip, device table, or log in the data"

[[exclude]]
when = { goal = "check" }
forbid = { evidence = ["none", "media-file", "log"] }
reason = "a compatibility check needs a device to check against"
```

Nine rules leave 1,342 valid tuples. `uv run mediadoctor-lab04 dims` lists them with their reasons. Writing the
reason forces a decision about each rule: some exclusions are facts about the world, some are facts about *your
data* (we have no DRM log, but real users might paste one), and the second kind should be revisited when real
traffic arrives.

## Step 2: generate tuples

You will not write a query for each of 1,342 tuples, and you do not need to. The question is which few hundred to
keep. `evalkit.synth` offers four strategies:

| Strategy | What it guarantees | Cost here |
|---|---|---|
| `full_product` | every valid combination | 1,342 tuples |
| `sample_tuples` | nothing; uniform over valid tuples | any n |
| `stratified_sample(by=...)` | roughly equal counts per value of one dimension | any n |
| `pairwise_tuples` | every *pair* of values that can co-occur appears at least once | 34 tuples |

Pairwise (all-pairs) coverage comes from combinatorial testing: most bugs depend on one value or on the
interaction of two, rarely on a specific combination of six. Covering all feasible value pairs (242 here) gets you
most of the value of the full product at a tiny fraction of the size. The greedy algorithm in `pairwise_tuples` is
simple: take an uncovered pair, find the valid tuple containing it that covers the most other uncovered pairs, and
repeat.

### Worked example: what a random sample misses

Draw 50 tuples uniformly from the valid set and print topic against evidence:

```text
$ uv run mediadoctor-lab04 tuples --strategy sample --n 50
sample: 50 tuples, value pairs covered 216/242 (89%)
topic                  none  media-file      device file+device         log  total
av1-playback              3           3           2           4           x     12
hdr-colour                3           1           2           3           x      9
mp4-startup               2           3           x           x           x      5
av-sync                   3           4           x           x           x      7
codec-limits              2           x           2           x           4      8
live-stream               1           x           x           x           1      2
audio-focus               3           x           x           x           x      3
drm-resolution            0           x           4           x           x      4

1 possible cells with no examples; x = excluded by a rule
```

`x` marks combinations a rule removed; a `0` is a real gap. Three things stand out:

- **Topics with few valid tuples get few samples.** AV1 and HDR have many valid combinations (devices, files, both),
  so uniform sampling gives them 21 of 50. Audio focus has only `none` evidence, so it gets 3, and live streams 2.
  Audio focus is the one topic with no file or device to inspect, which makes it the topic where an agent is most
  likely to answer from memory. Uniform sampling under-tests exactly that slice.
- **A whole cell is missing**: no DRM question without a device ("why is our DRM content capped at SD on some
  phones?"), which is the most common way a support agent would ask it.
- **26 of 242 value pairs never occur.** At 200 tuples it is still 239 of 242, and audio focus still gets only 5.

Now compare the pairwise set: 34 tuples, all 242 pairs, every cell non-zero. The course dataset uses both: the 34
pairwise tuples first, then a sample stratified by topic up to 200, so each topic gets about 25:

```text
$ uv run mediadoctor-lab04 tuples
course: 200 tuples, value pairs covered 242/242 (100%)
```

!!! tip "Write 20 tuples by hand first"
    Before you generate anything, write about 20 tuples yourself and try writing the query for each. You will find
    combinations that make no sense (they become rules) and values that are too vague to write for (they get
    split or renamed). The beta queries in `data/synth/beta_queries.jsonl` are what such a first pass looks like.

## Step 3: turn tuples into queries

Each tuple becomes one request to the cheaper model (`claude-haiku-5-5`, the `synth` role in
`config/models.toml`). The request is built by `mediadoctor.synth_spec.build_synth_request`:

- the **system prompt** says what to write and how people write: experts are precise and name APIs; novices are
  vague and misspell words; mention given names exactly unless the tuple says `missing-detail`; paste given log lines
  verbatim; state the premise as a belief and do not correct it; no greetings, no "Could you please", one to four
  sentences. It ends with three real messages as style examples;
- the **user message** is the tuple as JSON, plus the concrete things it needs: which clip and device, which log
  lines to paste, and for `false-premise` the specific wrong belief.

The concrete artefacts are chosen by code, not by the model (`artefacts_for`, `premise_for`). That keeps every
query *answerable*: a question that names `av1_2160p60.mkv` refers to a file the agent's `ffprobe` tool can read,
and a false premise is one the tools or notes can disprove. If the model invents a device name, the query tests
the agent on something no tool knows about, and every answer is a failure for the wrong reason.

Here is a tuple and the query written for it:

```json
{"persona": "app-developer", "topic": "audio-focus", "goal": "how-to", "evidence": "none",
 "expertise": "novice", "ambiguity": "false-premise", "premise": "AudioFocusRequest works from API 21"}
```

```text
i want my app to stop the music when another app plays audio. i was going to use AudioFocusRequest since it works
from api 21 right, how do i set it up? is there a simple example
```

A novice, lower case, the goal described in plain words, a wrong belief stated as fact with a hopeful "right", and
a real question underneath. (`AudioFocusRequest` needs API 26.) This is `m4q021` in dataset v1.

### Making queries sound like people

Model-written queries have tells. Watch for them and put the opposite into the prompt:

| Tell | What people actually do |
|---|---|
| "I'm experiencing an issue with..." | Start with the symptom: "4k av1 stutters on the lumen" |
| "Could you please help me understand..." | Ask directly, or don't ask at all and paste a log |
| Perfect grammar and capitals | Lower case, missing punctuation, typos, run-on sentences |
| One generic question per message | A bug-ticket template, a forwarded customer complaint, three sentences of context |
| Every question names the API | Novices describe what they see, not what causes it |
| Logs summarised | Logs pasted raw, with timestamps and PIDs |

Real queries are the best style guide. Three of the beta queries go into every prompt as examples, chosen by hash
so different tuples see different examples. Do not let the examples carry *content*: if all three are about AV1,
the model drifts toward AV1. Choose them for style.

### Batching

Two hundred independent requests do not need to be sent one at a time. The [Message Batches
API](https://platform.claude.com/docs/en/build-with-claude/batch-processing) takes them all in one call, at half the
price, and returns results within 24 hours (usually much sooner). `evalkit.synth.create_many` wraps it: in record or
live mode with `use_batch=True` it creates the batch, polls until it ends, and reads the results by `custom_id`; in
record mode it saves each result under the same fixture key a single call would use, so replays cannot tell the
difference. In replay mode (the default) it reads fixtures and never needs a key.

!!! info "How the course fixtures were written"
    The responses in `fixtures/recorded/mediadoctor-synth.jsonl` were generated by Claude subagents (Haiku, the
    synth model), one per tuple from the same request the lab builds, and recorded through the real `create_many`
    batch path. Every record is labelled `"source": "subagent-authored"`. The data is synthetic; the lab shows how
    to record your own with a key.

## Step 4: deduplicate, measure diversity, check coverage

### Near-duplicates

Two queries can come from different tuples and still say the same thing, for example when the persona framing for
an app developer and a media engineer comes out identical. Exact-match dedup misses these. `evalkit.synth.dedup`
compares word 3-gram sets (*shingles*) with Jaccard similarity and keeps the first of each group above a threshold.
Two details matter:

- **Ignore pasted logs.** Two different questions that paste the same logcat excerpt would otherwise look 80%
  similar. `similarity` strips lines that start with a logcat timestamp before comparing.
- **Only compare queries that test the same thing.** "How should we recover a live stream after the app was in
  the background? I can grab logs if needed" and the same sentence followed by the actual log are 70% similar, but
  they are different test cases: one tests whether the agent asks for the log, the other whether it reads it. The
  course compares queries only within the same `evidence` and `ambiguity` values (`DEDUP_WITHIN` in `lab04`).

At threshold 0.6, none of the 200 course queries is dropped: the most similar pair scores only 0.20. Writing one
query per call, with a concrete tuple, gives text varied enough that no two share much phrasing. Do not skip the
check for that reason. A template writer, a model that repeats itself, or two tuples whose difference never makes
it into the words produce pairs above 0.8, and each such pair is useful to read: a dimension value that did not
make it into the text. Exercise 2 asks you to choose and justify the threshold.

### Diversity

`diversity_report` gives a few numbers that are cheap and hard to fool yourself with:

| | naive prompt (50) | dataset v1 (200) |
|---|---|---|
| words per query | 8 to 20, mean 14.1 | 14 to 60, mean 37.8 |
| most common opening | "how do" (36%) | "how do" (10%) |
| queries with LLM-style tells | 0 | 4 |
| distinct words / bigrams | 0.431 / 0.795 | 0.147 / 0.570 |
| queries naming a file, device, or pasting a log | 0 | 82 |
| fewest mentions of a topic (keyword tagger) | live-stream, 1 | audio-focus, 15 |

Read the distinct-n row carefully: the naive set scores *higher*. Distinct-n is the share of unique words or
bigrams, and short sentences have few repeats. The structured set repeats file names, device names, and pasted log
lines on purpose. Lexical diversity is not coverage. That is why the coverage matrix, not a diversity score, is the
main check. The tells row cuts the other way: four v1 queries say "can you help me", which the prompt asked the
writer to avoid. Four in 200 is tolerable, but it is the kind of drift the counts are there to catch.

### Coverage

`coverage_matrix` prints counts for any two dimensions, marks excluded cells with `x`, and counts the real gaps.
Print several pairs, not just one: topic × evidence, persona × expertise, goal × ambiguity. Coverage drops after
dedup and again within each split, so check the split you will evaluate on:

```text
$ uv run mediadoctor-lab04 coverage
...
train 120 queries, value pairs covered 242/242
dev    42 queries, value pairs covered 216/242
test   38 queries, value pairs covered 184/242
```

## Step 5: freeze, split, and do not leak

A dataset you keep changing cannot measure progress. Freeze it: write the rows, a manifest with counts,
thresholds, the hash of the dimensions file, and the file's SHA-256. Version it (`v1`), and make the next change a
`v2` with its own manifest.

Split it before you look at results:

- **train**: queries you may read freely, use as few-shot examples, and use to tune prompts;
- **dev**: queries you run often while improving the agent, and read when they fail;
- **test** (held out): queries you run rarely, read never, and report once per milestone.

The trap with synthetic data is **leakage through near-duplicates**. If a test query is a rewording of a train
query, tuning on train quietly tunes on test. `assign_splits` first groups queries whose similarity is at least
0.35 (lower than the dedup threshold, on purpose) and assigns each group to one split by hash. `leakage_pairs`
checks the result: dataset v1 has 0 similar pairs across splits. On these queries grouping happens not to matter,
since no two reach 0.35 and splitting each query independently gives the same assignment; on a more repetitive set
(templates, or a model that reuses its phrasing) independent splitting leaves near-copies on both sides.
Exercise 4 runs the comparison.

## Step 6: run it, and read what comes back

A dataset is only useful once something runs on it. The lab runs the module 2 agent on the 30 dev queries that
match a module 3 scenario and reads the traces with the module 3 tools. The reference labels (written by Claude
Opus annotators, like module 3's) break the result down by the dimension this module added:

```text
$ uv run mediadoctor-lab04 by-dimension --dim ambiguity
ambiguity         failing  modes
clear              0/13
false-premise      1/12    {'redundant-steps': 1}
missing-detail     0/5
```

The agent handles the hard slices well on this data. Eleven of the twelve false-premise questions pass, and the one
failure (`m4q021`) is not about the premise: the answer corrects "AudioFocusRequest works from API 21" and is right,
but the agent ran a second knowledge-base search that returned the same note. All five missing-detail questions
pass. No trace trips an automatic signal from module 3 (`signals` flags 0 of 30), so even that one failure is found
only by reading.

That is a real result, and the method is what makes it one: because `ambiguity` is a dimension, you can say the
agent was tested on 12 wrong beliefs and 5 under-specified questions in this slice and did not repeat or guess,
rather than hoping such questions were in the set. On an agent that does repeat a user's wrong belief, or picks a
device the user never named, the same table shows it at once as a failing row with its own mode, a failure that a
set of clear, well-posed questions would never trigger. With one failure in 30, no dimension shows a pattern; the
next step is more false-premise and missing-detail queries, not a conclusion.

## Seeding with real queries

Once real queries arrive, they change the process in three ways:

1. **Measure them against your dimensions.** Tag each real query with dimension values and print the same coverage
   matrix. The ten beta queries cover 106 of 242 pairs and never use `goal=check` or `ambiguity=false-premise`.
   Either real users do not ask those (drop or down-weight them), or the beta group is not representative (keep
   them). Values that real users need and your dimensions lack become new values or new dimensions.
2. **Generate only the gaps.** `pairwise_tuples(space, start=real_tuples)` starts from the pairs real queries
   already cover; 25 generated tuples complete the set (`uv run mediadoctor-lab04 gaps`).
3. **Use them as style examples.** Real phrasing in the prompt beats any list of instructions.

Over time the dataset should become mostly real, with synthetic queries kept for rare slices and known failures.

## Pitfalls: what synthetic data cannot tell you

- **It does not tell you how often anything happens.** Our tuples are spread evenly on purpose; real traffic is
  not. "11 of 12 false-premise questions pass" is a fact about the agent on these premises, not about users. Do not
  report synthetic pass or failure rates as product quality.
- **It is not ground truth.** The model writing the queries has its own blind spots, and it is often the same
  family as the agent you are testing. In specialised domains it misses the quirks that matter; the FAQ entry on
  [when synthetic data is unreliable](https://hamel.dev/blog/posts/evals-faq/are-there-scenarios-where-synthetic-data-may-not-be-reliable.html)
  lists the main cases.
- **Generated queries can be wrong.** A writer can "helpfully" correct the premise it was asked to state, name the
  file a `missing-detail` query was meant to hide, or answer a different tuple altogether: two v1 queries
  (`m4q030`, `m4q132`) are about a different topic from their tuple. Check this in code (the lab does) and read a
  sample, because the code check also raises false alarms.
- **Your dimensions are your hypotheses.** Coverage of your dimensions is not coverage of reality. If real users
  ask about subtitles, nothing here will tell you.
- **Read the traces anyway.** The point of synthetic queries is to get traces to read before users arrive. Module 3's
  method applies unchanged.

## Checklist

- [ ] Dimensions come from failure hypotheses; each is one kind of variation with 3 to 6 concrete values.
- [ ] Impossible combinations are rules with written reasons, not hand filtering.
- [ ] Tuples cover all feasible value pairs; small slices are stratified up, not left to chance.
- [ ] Concrete artefacts (files, devices, logs, false premises) come from code and exist in the test environment.
- [ ] Queries are written one tuple per call by the cheap model, with real style examples.
- [ ] Near-duplicates removed within the same test case; pasted logs ignored for similarity.
- [ ] Coverage matrices printed for several dimension pairs and for each split.
- [ ] Frozen with a manifest and hash; grouped splits; 0 leakage pairs.
- [ ] A sample of queries read by a person; generated queries checked against their tuples.
- [ ] Real queries, when they arrive, are tagged, compared, and used to seed the next version.

## Summary

Write dimensions, not prompts. Choose tuples so coverage is a property of the code, write each query in a separate
cheap call with concrete artefacts, and check the result with coverage matrices rather than a diversity score.
Freeze the set with grouped splits, run the agent on it, and read the traces. Synthetic data gets you started and
targets the slices you worry about; it never tells you what real users do.

Next: [the lab](lab.md), then the [exercises](exercises.md) and [quiz](quiz.md). The
[cheat sheet](../../cheatsheets/synthetic-data.md) and the [dimensions sheet](../../eval-templates/dimensions-sheet.md)
template summarise the method.
