# 7. Architectures: RAG, multi-turn, multi-agent, multimodal

**Goal:** adapt evals to retrieval, conversations, handoffs, and images.

**Estimated time:** 10 hours (lesson 2 h, lab 5 h, exercises and quiz 3 h)

By the end of this module you will be able to:

- evaluate retrieval on its own with recall@k, precision@k, MRR, and nDCG over a labelled relevance set, and compare
  chunking and ranking choices with a paired interval;
- evaluate RAG generation (faithfulness to the context, answer relevance, citation correctness) and split failures
  into retrieval failures and generation failures;
- run multi-turn sessions against a simulated user, score them at the session level and the turn level, and check
  the simulator before trusting it;
- treat a multi-step or multi-agent run as a trajectory: tools, arguments, order, final state, step efficiency, and
  a transition-failure matrix that shows where runs first break;
- evaluate answers about images (decoded video frames and spectrograms) with a validated vision judge.

Artifacts: a retrieval metrics report (`uv run mediadoctor-lab07 retrieval`), a multi-turn simulator
(`labs/mediadoctor/src/mediadoctor/chat.py`), a transition-failure matrix (`uv run mediadoctor-lab07 agents`), a
multimodal judge (`config/judges/frame-*.v1.toml`), the new `evalkit.retrieval` and `evalkit.trajectory` modules, and
the [architectures cheat sheet](../../cheatsheets/architectures.md).

## Intuition: score the parts, then the whole

A pass rate for a whole system tells you *whether* it works, not *where* it breaks. You already debug media
pipelines this way: when playback stutters you do not stare at the end-to-end frame rate, you check the demuxer, the
decoder queue, and the renderer separately, because each has its own failure signature and its own fix.

LLM systems have the same structure. A RAG system is a search engine feeding a writer. A chat assistant is a policy
over a conversation. A multi-agent system is a pipeline with handoffs. An image question has a perception step
before any reasoning. Each component gets its own eval, measured on its own labels, and the end-to-end eval stays
on top as the number that matters. The component evals tell you which fix moves that number.

Two rules carry over from earlier modules unchanged: look at the data first (module 3), and validate every judge
against labels before trusting it (module 5). Everything below is still binary pass/fail with intervals (module 6).

## Part A: RAG

### Step 1: a relevance set for retrieval

Retrieval is a search problem, so evaluate it with search metrics, separately from the answer
([Husain and Shankar, *How should I approach evaluating my RAG system?*](https://hamel.dev/blog/posts/evals-faq/how-should-i-approach-evaluating-my-rag-system.html)).
You need queries paired with the passages that answer them.

MediaDoctor's module 1 knowledge base had eight short documents, too few to make retrieval interesting, so this
module adds a second edition: `data/kb_v2/`, 25 documents and 57 sections on codecs, streaming, audio, and video.
(The agent from earlier modules still searches `data/kb/`; changing it would invalidate every recorded trace.) The
relevance set `data/labels/module07_relevance.csv` has 48 queries, 12 to 14 per topic, each labelled at the
*section* level with a grade: 2 = this section answers the query, 1 = related and useful. Grades on sections rather
than documents keep the labels independent of how you chunk.

How to build one for your own system: sample real queries if you have them, otherwise write queries from the
documents (pick a fact, write the question it answers, then phrase it the way a user would, without the document's
words). Label every section that answers it, not only the one you started from. Include queries that use different
vocabulary from the documents ("cloud gaming" for low-latency decoding), because those are the ones that fail.

### Step 2: the metrics

For one query, take the ranked list of retrieved section ids and the labels:

| Metric | Question it answers | Formula (one query) |
|---|---|---|
| recall@k | Did the top k contain what we need? | relevant ids in top k / all relevant ids |
| precision@k | How much of the top k is useful? | relevant ids in top k / k |
| hit@k | Did at least one answering passage make it? | 1 if any, else 0 |
| reciprocal rank | How high is the first relevant id? | 1 / rank of the first relevant (0 if none); its mean is MRR |
| nDCG@k | Are the best passages near the top? | DCG of the ranking / DCG of the ideal ranking, gain = grade, discount log2(rank+1) |

Average each over queries and put a bootstrap interval on the mean (resample queries, as in module 6). Which one to
report depends on how the context is used: a generator that reads the top 3 passages needs recall@3 and hit@3; a
search box people scan cares about MRR and nDCG. Precision@k is usually low and that is fine: with one or two
relevant sections per query, a perfect top 5 has precision 0.2 to 0.4.

`evalkit.retrieval` implements them in under 100 lines; repeated ids count once, so retrieving the same section
twice earns nothing. References: [precision and recall](https://en.wikipedia.org/wiki/Precision_and_recall),
[mean reciprocal rank](https://en.wikipedia.org/wiki/Mean_reciprocal_rank),
[discounted cumulative gain](https://en.wikipedia.org/wiki/Discounted_cumulative_gain).

### Step 3: compare chunking and ranking

The lab compares two chunkers and two retrievers over `data/kb_v2/`:

- **fixed**: 40-word windows over the raw text, so headings and sections fall wherever they fall;
- **section**: one chunk per `##` section, prefixed with the document and section titles;
- **keyword**: count of distinct query words in the chunk (module 1's retriever);
- **bm25**: [Okapi BM25](https://en.wikipedia.org/wiki/Okapi_BM25) over lightly stemmed words.

A fixed-size chunk is credited to the section it overlaps most, so both chunkers are scored against the same labels.

| Config | recall@5 [95% CI] | MRR | nDCG@5 | codec | streaming | audio | video |
|---|---|---|---|---|---|---|---|
| fixed + keyword | 0.64 [0.53, 0.74] | 0.72 | 0.61 | 0.51 | 0.64 | 0.75 | 0.70 |
| fixed + bm25 | 0.71 [0.61, 0.80] | 0.79 | 0.70 | 0.58 | 0.79 | 0.81 | 0.70 |
| section + keyword | 0.74 [0.63, 0.83] | 0.80 | 0.72 | 0.51 | 0.82 | 0.90 | 0.80 |
| section + bm25 | 0.81 [0.72, 0.89] | 0.85 | 0.80 | 0.62 | 0.93 | 0.96 | 0.80 |

Both changes help, and they add up. Section chunks keep a heading with its text, so a query about "Diagnostics"
lands on the diagnostics section instead of a window that starts mid-sentence. BM25 down-weights words that appear
everywhere ("decoder", "Android") and stemming matches "decoders" to "decoder". The paired difference on the same
48 queries, fixed+keyword to section+bm25, is **+0.17 recall@5 [+0.09, +0.25]**.

Read that number with module 6's and module 8's rules, because it breaks two of them. It compares the best of four
configurations with the worst, chosen after looking (four configurations make six possible pairs), and it is
measured on the same 48 queries that picked the winner, so it is optimistic. Here the interval is far from zero and
both design choices have a mechanism you can read in the `misses`, so the conclusion "section + BM25 is better" is
safe. The *size*, 17 points, is not established. For a decision that rests on the size, split the relevance set
before comparing (choose on one part, report on the other), or adjust for the comparisons you made (Holm, module 6).

Read the topic columns with module 6 in mind. Codec queries went from 0.51 to 0.62, but that difference is measured
on 14 queries and its interval is [−0.04, +0.29]. The overall gain is real; the codec gain is not established. The
`misses` command shows why codec stays hard: "frames out immediately for cloud gaming" shares no words with the
low-latency decoding section, and "a TV box" none with tunneled playback. No amount of chunking fixes a vocabulary
gap; query rewriting, synonyms, or embedding search might, and the relevance set is how you would find out.

Chunk size is a design choice to test, not a default. [Husain and Shankar's FAQ on chunk sizes](https://hamel.dev/blog/posts/evals-faq/how-do-i-choose-the-right-chunk-size-for-my-document-processing-tasks.html)
makes the point that the right size depends on the task; the relevance set is how you measure it.

**Beyond keyword search.** Production RAG systems rarely stop at BM25, and each step up is one more configuration
for the same relevance set:

- **dense retrieval**: embed queries and chunks, rank by similarity
  ([Karpukhin et al., DPR](https://arxiv.org/abs/2004.04906)); it closes vocabulary gaps like "cloud gaming", and
  can miss exact identifiers such as `c2.android.av1.decoder` that BM25 finds;
- **hybrid**: run both and merge the rankings (for example reciprocal rank fusion), usually better than either;
- **reranking**: retrieve 20 to 50 candidates cheaply, then reorder them with a model that reads query and passage
  together ([Nogueira and Cho](https://arxiv.org/abs/1901.04085)); measure recall@k *before* the reranker, since it
  cannot rank what was never retrieved, and nDCG after;
- **contextual chunks**: prepend a model-written sentence of document context to every chunk before indexing it
  ([Anthropic: contextual retrieval](https://www.anthropic.com/research/contextual-retrieval)), the general form of
  this lab's "prefix the section title".

Each adds cost per query and latency, so report them next to recall, as module 11 does. And **relevance labels
themselves can be drafted by a model**: have a judge propose which sections answer each query, then have a person
accept or correct them. Validate the drafter like any judge (its TPR and TNR on a sample a person labelled from
scratch) before you let it label the rest; a drafter that misses relevant sections makes every retriever's recall
look higher than it is.

### Step 4: evaluate generation

Retrieval metrics say whether the right passages reached the model. Generation evals say what it did with them.
Three checks cover most of it (the split follows Jason Liu's
[There Are Only 6 RAG Evals](https://jxnl.co/writing/2025/05/19/there-are-only-6-rag-evals/), which the FAQ above
also recommends):

| Check | Compares | Evaluator | Fails when |
|---|---|---|---|
| Faithfulness (groundedness) | answer vs context | LLM judge, `config/judges/faithfulness.v1.toml` | the answer states a fact the passages do not contain, even a true one |
| Answer relevance | answer vs question | LLM judge, `config/judges/answer-relevance.v1.toml` | the answer addresses a different problem, or only declines |
| Citation correctness | cited ids vs context and labels | code | a cited id was not in the context, or none of the cited passages is relevant |

Faithfulness is about the context, not about truth: an answer from general knowledge that happens to be right still
fails, because next time the general knowledge will be wrong and nothing in the system will notice. Citation
correctness needs no model at all, so it is a code check.

Both judges are binary and get the module 5 treatment: label, measure TPR and TNR, then decide. In the lab's data
the generator rarely misbehaves, which makes the judges hard to validate. The labels mark only 1 of 96 answers as
unfaithful (`baseline:r34`, which states a fact from a passage that was not retrieved), and the faithfulness judge
passed it along with all the others: TPR 1.00 (95/95), TNR 0/1. With a single negative, TNR is not measured at all.
The judge has never been shown to catch an unfaithful answer, so do not use it to compare systems yet. To validate
it you need more unfaithful examples, either from a system that fails more often or written on purpose (append one
unsupported detail to a grounded answer). The answer-relevance judge has the opposite problem. The labels call all
96 answers relevant, but the judge fails 14 of them, and every one of the 14 is a faithful abstention ("the
passages do not cover this"). That is a disagreement about the criterion, not noise. Decide whether a polite
"not in the passages" counts as relevant, then fix the labels or the judge prompt (module 5's alignment step).

### Step 5: separate retrieval failures from generation failures

For each answer you know two things: did retrieval put an answering passage in the context (a hit), and did the
answer pass (correct and faithful)? That gives four cells:

| | answer passed | answer failed |
|---|---|---|
| **retrieval hit** | pass | **generation failure**: the model had what it needed |
| **retrieval miss** | pass despite a miss (luck or general knowledge) | **retrieval failure**: fix search first |

In the lab, with the top 3 passages as context:

| System | pass | generation failures | retrieval failures | pass rate when retrieval hit |
|---|---|---|---|---|
| baseline (fixed + keyword) | 36/48 = 0.75 | 0 | 12 | 1.00 |
| improved (section + bm25) | 40/48 = 0.83 | 0 | 8 | 1.00 |

Retrieval failures fell from 12 to 8, and the end-to-end pass rate rose from 0.75 to 0.83. The paired difference is
+0.08, CI [−0.02, +0.19]: 5 queries passed only with the improved system and 1 only with the baseline. The split
gives a clear answer. Every failure in both systems is a retrieval failure. Whenever an answering passage reached
the generator, the answer passed. When none did, the generator declined or hedged instead of inventing an answer,
so it never passed despite a miss either. The next fix is still retrieval: the codec vocabulary gaps from step 3
(r07, r11, r13) are among the improved system's eight failures. Without the split you would see "+8 points, not
significant" and might start rewriting the prompt, which these numbers say would not help. On a system whose
generator also fails, the same table would show whether those failures outnumber the retrieval failures, and so
which fix to try first.

### Worked example: a wrong answer about MediaCodec diagnostics

Query r04: *"What does the diagnosticInfo string in a codec exception tell me?"*

The baseline answered: *"The passage says to log `diagnosticInfo` from the exception and that it names something,
but the text is cut off before saying what it names. I can't say more than that from the passages provided."* and
cited `[kb:mediacodec-errors@40]`. It did not answer the question, so it fails. Before touching the prompt, check
each component:

1. **Retrieval.** The context held three 40-word windows: one from the MediaCodec errors document, one on fixing
   blocking artifacts, and one on listing codecs. The first is the interesting one. It is mostly the "Common causes"
   section and ends mid-sentence inside "Diagnostics": *"Log `diagnosticInfo` from the exception; it names"*. The
   rest of the sentence, the part that answers the question, is in the next window, which did not rank. A chunk is
   credited to the section it mostly covers, so this counts as a miss for the answering section,
   `mediacodec-errors#3`: hit@3 = 0. This is a retrieval failure, caused by where the chunk boundary fell.
2. **Generation.** Given no answering passage, the model noticed that the passage was cut off and declined to
   guess. Given that context, this was the right behaviour: the answer is faithful, and the faithfulness judge
   passed it, correctly. Nothing here needs fixing in the generator.
3. **Citations.** The citation was *valid* (the id was in the context) but did not point to a relevant passage.
   Validity alone would have passed it.

With section chunks and BM25, the "Diagnostics" section ranked first, and the answer became *"It names the failing
component, such as `c2.qti.avc.decoder`, so log it from the exception."*, citing `[kb:mediacodec-errors#3]`.
Across all 48 queries, recall@5 went from 0.64 to 0.81; on the 14 codec queries from 0.51 to 0.62, which, as
step 3 showed, is not yet a demonstrated gain. One fixed query is an anecdote; the table is the evidence.

## Part B: multi-turn conversations

### Step 6: conversation level first, then turns

A conversation can fail at the end (the user never got an answer) or in the middle (the assistant forgot something,
asked a pointless question). Score both, in that order:

- **Session level**: did the conversation reach the user's goal? For MediaDoctor: a diagnosis that names the right
  cause. Also: did it give up while the user could still have helped?
- **Turn level**: did each assistant turn behave? Did it ask for something the user already said (context
  retention)? Ask when nothing was missing (needless clarification)? Ask several things at once?

[Husain and Shankar's FAQ on multi-turn traces](https://hamel.dev/blog/posts/evals-faq/how-do-i-debug-multi-turn-conversation-traces.html)
recommends exactly this order: a pass/fail on the whole conversation, then the first upstream failure; and, when you
find one, try to reproduce it as a single-turn test before debugging the conversation machinery.

### Step 7: a simulated user

You cannot ask real users to replay a conversation every time you change a prompt. A simulated user is a second
model that plays the user: it gets a persona, the opening message, and the facts the user knows (the clip's
format, the log line, what the device supports), with rules: reveal a fact only when asked, never invent one.

`labs/mediadoctor/src/mediadoctor/chat.py` runs sessions of at most three user turns. The chat agent has no tools,
so it must ask for missing facts. Sixteen scenarios: eleven where the opening lacks a fact the diagnosis needs, five
where it has everything. Two chat prompts: v1 answers immediately; v2 asks first when a detail is missing.

| | resolved | gave up early | asked when a fact was missing | mean user turns |
|---|---|---|---|---|
| v1 (answer first) | 16/16 = 1.00 [0.81, 1.00] | 3 | 0 of 11 | 1.00 |
| v2 (ask first) | 15/16 = 0.94 [0.72, 0.99] | 0 | 9 of 11 | 1.56 |

"Resolved" in this table is the lab's code check: the final answer names the scenario's cause. On these sessions
the code check points the wrong way. It disagrees with the labels on 4 of 32 sessions. Three are v1 sessions
(`c05-v1`, `c06-v1`, `c13-v1`) that answered without asking and listed several possible causes. The list contains
the right cause, so the regex counts the session as resolved. The labels count it as no diagnosis and as giving up
early. The fourth, `c16-v2`, names the cause (1.5 Mbps CBR is far too low for 1080p60) in words the regex does not
match. By the labels, v1 resolves 13 of 16 and v2 all 16. By the code check, v1 looks better (paired difference
−0.06, CI [−0.19, 0.00]). With 16 scenarios neither difference is established, but the lesson is clear: validate the
session-level check against labels before you compare prompts with it. Here a keyword match rewards hedging.

At the turn level, neither prompt re-asked a fact the user had given, asked a needless question, or asked more than
one thing at once. v2's cost is only the extra turn: 0.56 more user turns per session. With a weaker agent the same
turn checks would show the other side of the clarification trade-off, where asking fixes assumed details and adds
friction (re-asked facts, questions about things the opening already said).

"Gave up early" is a session-level property. No single turn shows it; you have to see that the assistant ended the
conversation ("I can't tell from this description; contact the vendor") when one question would have unlocked it.
The lab's `gave-up-early` judge reads the whole transcript. Against labels it passes every session: TPR 1.00 (29/29)
and TNR 0.00. It catches none of the 3 give-ups, because they do not read like give-ups. They are confident-sounding
hedges that offer a list of causes and a diagnostic step instead of asking. A judge prompt written for the
"contact the vendor" kind of give-up misses this kind, and on 3 positives you cannot tell how well any fix works.

### Step 8: check the simulator before blaming the agent

A simulated user is a model too, and it can fail in two ways:

- it volunteers a fact nobody asked for, so the agent never has to ask, and the session looks better than a real one
  would;
- it contradicts its own facts ("It supports everything we've tried, Main10 included"), and the agent's wrong answer
  follows from that.

Code checks on the simulator's turns (did it answer what was asked, did it add facts) look for both. In the lab's
recorded sessions they flag nothing, and the labels record no simulator fault either. The simulated users, generated
by Claude subagents, kept to their rules. To see that the check works, give `c07-v2`'s simulated user a reply that
states every fact it knows. The agent asked only for the log, and the check reports
`turn 3: volunteered 'code' without being asked` (the test suite does exactly this). A clean result means something
only if the check is known to catch faults. When it does flag sessions, count those faults as eval-harness bugs,
exclude or fix the sessions, and report how many you dropped.

Those checks catch a simulator that breaks its rules; they do not show that it talks like your users. A simulator
that is too cooperative (answers every question fully, never gets annoyed, never pastes the wrong log) makes every
agent look better than it will be. Once real conversations exist, compare the two: sample real and simulated
sessions on the same scenarios, have a reviewer who does not know which is which label them, and check that the
agent's pass rate and the turn-level failure counts are similar on both. Until then, treat simulated session
results as an upper bound and say so. An alternative that
avoids simulation is **N−1 testing**: replay the first N−1 turns of a real conversation and evaluate only the next
turn; it is less flexible but uses real user language (both approaches are described in the FAQ above).

## Part C: multi-step and multi-agent systems

### Step 9: trajectories

A run of a tool-using agent is a trajectory: the ordered steps it took. Evaluate it in two layers
([Husain and Shankar, *How do I evaluate agentic workflows?*](https://hamel.dev/blog/posts/evals-faq/how-do-i-evaluate-agentic-workflows.html)):

1. **Outcome** (always first): did the final state meet the goal? For MediaDoctor, the module 5 labels.
2. **Process**: the right tools (tool recall and precision against the expected tools), valid arguments (no tool
   errors), a sensible order (expected steps appear as a subsequence), and no wasted steps
   (**step efficiency** = minimal steps / steps taken).

Scored this way, module 5's traces (the 108 outside the missing-detail slice, where the right move is to ask) fail
so rarely that the process metrics have little to locate. Only 2 of the 108 runs failed. 104 called every expected
tool and 102 of those passed. The 4 that skipped an expected tool all passed too: they were expected to grep a log
and answered from the knowledge base instead. 7 runs called an unexpected tool, and 6 of them passed. Here a
trajectory deviation is not a failure. It marks a different path that a person should look at once, and it may mean
the expected tools in the dataset are too narrow. On a system that fails more often, the same columns show whether
skipped tools go with failed answers, which is how process metrics help locate problems. Either way, the outcome
decides.

**Agents that change things: grade the final state.** MediaDoctor mostly answers questions, so its outcome is an
answer. Agents that act (file a ticket, edit a config, book a refund, drive a browser) have a better outcome to
check: the state of the world afterwards. Run them in a sandbox seeded with a known state, and assert on the state in
code after the run: the ticket exists with these fields, the config file parses and has this value, nothing else
changed. This is how current agent benchmarks such as [τ²-bench](https://arxiv.org/abs/2506.07982) grade, with a
simulated user on one side and a database whose final state is compared with the expected one. State checks are
cheaper and more exact than any judge, they catch the agent that *says* it did the task without doing it, and they
make pass^k (module 6) meaningful for actions: did the agent reach the right state every time? Module 10's action
tools are a small version of this: the red-team success checks read what the tools really did, not what the answer
claims. For long-horizon or computer-use agents, add checkpoints (intermediate states the run must pass through)
so a failure can be located the way the transition-failure matrix below locates it.

### Step 10: a planner, specialists, and handoffs

Module 7 splits MediaDoctor into a team (`labs/mediadoctor/src/mediadoctor/multiagent.py`): a planner routes each
question to one or two specialists (media: ffprobe; device: codec_caps and logcat_grep; knowledge: search only) and
writes a brief. Specialists see only the brief, never the user's message. The planner then writes the answer from
their findings.

Every boundary is a new way to fail:

- **routing**: the planner picks the wrong specialist, or drops one;
- **handoff**: the brief loses a detail (the file name, the device), so the specialist guesses;
- **tool arguments**: a specialist calls a tool with a malformed argument;
- **synthesis**: the answer ignores or contradicts the findings.

### Step 11: the transition-failure matrix

For each failed run, walk its states in order (plan, each handoff, each tool call, "evidence complete", answer)
against the reference trajectory, and record two things: the **last state that succeeded** and the **first state
that failed**. Count the pairs in a matrix: rows are the last success, columns the first failure. The technique is
from [Husain and Shankar's FAQ on multi-step workflows](https://hamel.dev/blog/posts/evals-faq/how-do-i-evaluate-complex-multi-step-workflows.html).

On 47 dev and test queries the team passed 45 (0.96 [0.86, 0.99]). The 2 failures:

```text
last ok \ failed        answer
evidence                     2
```

Read it by columns. There is one column: both failures are synthesis. The evidence was complete, and the planner
wrote a generic answer that restates the knowledge base's audio-focus note without answering what was asked
(`m4q028`, `m4q081`). No run failed at routing, at a handoff, or on a tool argument. A matrix this small says only
"look at the synthesis step". On a team that fails more often, the columns spread out and show which boundary to fix.

The states that did not fail are still worth a look. The planner chose a route different from the reference 11
times, usually by adding a knowledge or device specialist, and all 11 runs passed, at a mean step efficiency of 0.77:
extra specialists cost model calls but did not hurt the answer. Three passing runs (`m4q052`, `m4q163`, `m4q192`)
never gathered the reference's expected evidence (for example, no ffprobe call), and the labeller still passed them.
The reference trajectory is one good path, not the only one. When a run passes on another path, update the reference
before you count that deviation as an error.

Fix upstream first: a routing or handoff failure makes everything after it fail too, so the first failure is the one
to count and fix, as in module 3's error analysis.

## Part D: images

### Step 12: questions about media

MediaDoctor's users send screenshots, frames, and spectrograms. Claude reads images in the Messages API as `image`
content blocks next to the text ([Anthropic: vision](https://platform.claude.com/docs/en/build-with-claude/vision)).
Two eval patterns apply:

- **a vision judge**: an image in, PASS/FAIL on one criterion out. The lab has one per video artifact: blocking
  (blocky, macroblocked areas) and banding (visible steps in gradients);
- **an answer about an image**, scored like any answer: MediaDoctor names the defect in an audio spectrogram
  (none, dropout, clipping, noise), and a code check compares it with the label.

Labels come cheap here because you make the images. `scripts/make_module07_images.sh` uses FFmpeg to render 16
frames at 320×180 (clean test patterns; H.264 at quantiser 51 and 40 with deblocking off for severe and mild blocking;
gradients reduced to 3 or 5 bits per channel for severe and mild banding) and 6 spectrograms of test tones (clean,
muted for 300 ms or 100 ms, gain past full scale before 16-bit conversion). The recipe *is* the label
(`data/labels/module07_images.csv`). The whole set is under 500 KB.

| Judge | severe detected | mild detected | false alarms |
|---|---|---|---|
| frame-blocking | 3/3 | 3/3 | 4/10 (all four banded frames) |
| frame-banding | 3/3 | 3/3 | 2/10 (two severely blocked frames) |

Both judges detect every artifact at both severities, and an overall "detects 6 of 6" is all you would see without
the false alarms. The blocking judge flags all four banded frames (`banding_severe_a/b/c`, `banding_mild_a`), so as
it stands it cannot tell banding from blocking. Report by severity and with intervals: three frames per cell give
very wide intervals ([0.44, 1.00] for 3/3, and the 4/10 false alarms come from just 10 clean frames), so the real
result is "needs about 30 to 40 frames per severity" (exercise 5). Then read the disagreements. The banding judge's
alarm on the severely blocked gradient is arguably correct, because heavy quantisation of a gradient also produces
bands. The blocking judge's alarms on 3-bit and 5-bit gradients are harder to defend and point at its criterion.
Recipe labels can be incomplete; disagreement review (module 5) applies to images too.

Keep the fixtures small: `evalkit` now replaces base64 image data in a request with its SHA-256 and length before
hashing and storing it. A changed image still changes the key, but the 38 vision records take 65 KB instead of
repeating every image.

## Checklist

- [ ] Retrieval has its own labelled set and its own metrics, with intervals; per-topic numbers read with their n.
- [ ] Generation is judged for faithfulness and relevance with validated judges; citations are checked in code.
- [ ] Each RAG failure is attributed to retrieval or generation before choosing a fix.
- [ ] Conversations are scored at the session level first, then per turn (retention, needless questions).
- [ ] The simulated user is checked for leaked or invented facts; faulty sessions are reported, not hidden.
- [ ] Multi-step runs are scored on outcome first, then trajectory: tools, arguments, order, efficiency.
- [ ] Failed multi-agent runs are summarised in a transition-failure matrix; fixes start at the hottest upstream cell.
- [ ] Vision judges are validated per artifact and per severity, on images whose labels you control.
- [ ] Image fixtures store hashes, not image data.

## Summary

Every architecture adds components, and every component needs its own eval: search metrics for retrieval,
faithfulness and relevance for generation, session and turn checks for conversations, trajectories and a
transition-failure matrix for multi-step and multi-agent runs, and validated vision judges for images. The
end-to-end pass rate stays the headline; the component evals tell you which fix will move it, and the intervals from
module 6 tell you whether it did.

Next: [the lab](lab.md), then the [exercises](exercises.md) and [quiz](quiz.md). The
[architectures cheat sheet](../../cheatsheets/architectures.md) collects the metrics and checks.
