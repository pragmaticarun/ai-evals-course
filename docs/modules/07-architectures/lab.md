# Lab 7: Evaluating each architecture (offline)

**Time:** about 5 hours. **Needs:** the setup from [lab 1](../01-why-evals/lab.md), and modules 5 and 6.
**Does not need:** an API key or network access.

You will measure retrieval over a new knowledge base, attribute RAG failures to retrieval or generation, run a
simulated user against two chat prompts, score agent runs as trajectories, build a transition-failure matrix for a
planner-and-specialists version of MediaDoctor, and validate vision judges on video frames. Everything replays from
fixtures. Keep your own files under `runs/`, which git ignores.

!!! info "Synthetic-authored fixtures"
    Every model output in this lab (RAG answers, chat turns, simulated users, planner and specialist turns, judge
    verdicts, and vision answers) and every label was written for the course and recorded through the lab's real
    code paths by `scripts/author_module07_fixtures.py`. Records are labelled `"source": "synthetic-authored"`. The
    behaviour behind each label is documented in that script. The retrieval results are not synthetic: they are
    computed live from `data/kb_v2/` and the relevance labels. Section 9 shows how to record real runs.

## 1. Update and check

```bash
git pull
uv sync
uv run pytest -q tests/test_retrieval.py tests/test_trajectory.py tests/test_lab07.py
```

New files to skim: `labs/evalkit/src/evalkit/retrieval.py` and `trajectory.py` (the metrics), and in
`labs/mediadoctor/src/mediadoctor/`: `rag.py` (chunkers, BM25, RAG prompt), `chat.py` (chat agent and simulated
user), `multiagent.py` (planner and specialists), `vision.py` (image requests), and `lab07.py` (the evals).

## 2. Retrieval metrics

```bash
uv run mediadoctor-lab07 retrieval
```

```text
config                 recall@k [95% CI]   P@k   MRR  nDCG   hit       codec streaming     audio     video
fixed+keyword       0.64 [0.53, 0.74]    0.23  0.72  0.61  0.79        0.51      0.64      0.75      0.70
fixed+bm25          0.71 [0.61, 0.80]    0.25  0.79  0.70  0.88        0.58      0.79      0.81      0.70
section+keyword     0.74 [0.63, 0.83]    0.27  0.80  0.72  0.85        0.51      0.82      0.90      0.80
section+bm25        0.81 [0.72, 0.89]    0.30  0.85  0.80  0.94        0.62      0.93      0.96      0.80

fixed+keyword -> section+bm25, recall@5 (all queries, n=48): +0.17 [+0.09, +0.25]

fixed+keyword -> section+bm25, recall@5 (codec queries, n=14): +0.11 [-0.04, +0.29]
```

Try it by hand for one query before trusting the table:

```python
from evalkit.retrieval import ndcg_at_k, recall_at_k, reciprocal_rank
from mediadoctor import lab07, rag

q = next(q for q in rag.queries() if q.id == "r04")
for chunker, retriever in lab07.CONFIGS:
    ranked = lab07.ranked_sections(q, chunker, retriever)
    print(
        chunker,
        retriever,
        ranked[:3],
        recall_at_k(ranked, q.relevant, 5),
        reciprocal_rank(ranked, q.relevant),
        round(ndcg_at_k(ranked, q.grades, 5), 2),
    )
```

Then look at what the best configuration still misses:

```bash
uv run mediadoctor-lab07 misses --topic codec
```

Most codec misses have recall 0.5: one of two relevant sections, often from the same document, ranked below 5.
One (r11, "cloud gaming") retrieves nothing relevant at all: a vocabulary gap. Write down which misses a better
chunker could fix and which need something else (query rewriting, synonyms, embeddings).

Try `uv run mediadoctor-lab07 retrieval --k 3`: the context for generation is the top 3, so recall@3 is the number
that matters for part 3.

## 3. RAG generation and attribution

```bash
uv run mediadoctor-lab07 rag
```

```text
baseline (fixed+keyword): pass (correct and faithful) 27/48 = 0.56 [0.42, 0.69]
    retrieval hit@3 (an answering passage in context): 36/48 = 0.75 [0.61, 0.85]
    citations valid 46/48, cite a relevant passage 34/48
    attribution: pass 27, generation failure 9, retrieval failure 12, pass despite miss 0
    pass rate when retrieval hit: 0.75 (the ceiling if retrieval were perfect)
improved (section+bm25): pass (correct and faithful) 29/48 = 0.60 [0.46, 0.73]
    retrieval hit@3 (an answering passage in context): 40/48 = 0.83 [0.70, 0.91]
    citations valid 46/48, cite a relevant passage 35/48
    attribution: pass 29, generation failure 11, retrieval failure 8, pass despite miss 0
    pass rate when retrieval hit: 0.72 (the ceiling if retrieval were perfect)

faithfulness judge vs labels (PASS = positive): n=96 (human pass 71, fail 25)  TPR 0.94 (67/71)  TNR 0.68 (17/25)  agreement 0.88
answer-relevance judge vs labels (PASS = positive): n=96 (human pass 81, fail 15)  TPR 0.94 (76/81)  TNR 0.87 (13/15)  agreement 0.93

baseline -> improved, paired: n=48  A 0.562  B 0.604  diff +0.042 95% CI [-0.042, +0.125]  discordant: only A 1, only B 3  McNemar p=0.625
```

Each system answers all 48 queries from its top 3 passages (`rag.RAG_SYSTEM`). Read the four attribution cells as in
the lesson, then open a few answers of each kind:

```python
from mediadoctor import lab07

for run_id in ("baseline:r04", "improved:r04", "improved:r02"):
    r = lab07.rag_runs()[run_id]
    print(run_id, "hit" if r.hit else "miss", lab07.rag_labels()[run_id]["note"])
    print("   context:", [c.id for c in r.context])
    print("   ", r.answer.replace("\n", " | "))
    print("   citations:", lab07.citation_checks(r))
    print("   faithfulness judge:", lab07.rag_verdicts("faithfulness")[run_id].critique)
```

`baseline:r04` is the lesson's worked example. `improved:r02` is a judge miss: the answer appends "This behaviour
was introduced in Android 9 (API 28)", which no passage says, and the faithfulness judge passed it.

Two things to notice. The citation check separates *valid* (the id was in the context) from *supports* (the cited
passage is relevant); an answer can cite validly and still lean on the wrong passage. And the faithfulness judge's
TNR of 0.68 means it misses about a third of unfaithful answers: before you use it to compare systems, apply the
module 6 correction or improve it.

## 4. Multi-turn sessions with a simulated user

```bash
uv run mediadoctor-lab07 chat
```

```text
Session level
  v1: resolved 9/16 = 0.56 [0.33, 0.77]; gave up early 4; mean user turns 1.12
      opening lacked a needed fact (11): asked first 2, resolved 4; had everything (5): resolved 5
  v2: resolved 12/16 = 0.75 [0.51, 0.90]; gave up early 3; mean user turns 1.81
      opening lacked a needed fact (11): asked first 9, resolved 7; had everything (5): resolved 5
  resolved (code check) agrees with the labels on 32/32 sessions

Turn level (any turn in the session)
  v1: re-asked a known fact 0, needless question 0, more than one question in a turn 0
  v2: re-asked a known fact 3, needless question 2, more than one question in a turn 0

v1 -> v2 resolved, paired by scenario: n=16  A 0.562  B 0.750  diff +0.188 95% CI [-0.062, +0.438]  discordant: only A 1, only B 4  McNemar p=0.375

gave-up-early judge vs labels (PASS = kept going): n=32 (human pass 25, fail 7)  TPR 0.92 (23/25)  TNR 0.86 (6/7)  agreement 0.91

Simulated user checks (validate the simulator before trusting the sessions)
  c07-v2: code: turn 3: volunteered 'code' without being asked | label: volunteered a fact that was not asked for
  c13-v2: code: turn 3: volunteered 'clip' without being asked; turn 3: did not give the asked fact (decoders) | label: contradicted its own facts
```

The scenarios are in `data/sessions/module07_chat.json`: an opening message, the facts the user knows, which of
them the opening already gives, and which a diagnosis needs. Read the two prompts (`chat.CHAT_V1`, `chat.CHAT_V2`)
and the simulator's instructions (`chat.USER_SYSTEM`), then read sessions:

```bash
uv run mediadoctor-lab07 session c05-v2    # a retention failure: asks again for the start times
uv run mediadoctor-lab07 session c04-v2    # a needless question: the opening already had the box order
uv run mediadoctor-lab07 session c13-v2    # the simulated user contradicts its own facts
uv run mediadoctor-lab07 session c06-v2    # asks, gets the answer, then gives up
```

The turn checks (`chat.turn_checks`) are keyword heuristics: which facts a question asks about, and whether the user
had already given them. Heuristics like these need the same validation as a judge; the test suite checks them
against the labels for all 32 sessions, and exercise 2 compares a regex with the session-level judge.

## 5. Single-agent trajectories (module 5's traces)

```bash
uv run mediadoctor-lab07 trajectories
```

```text
all expected tools called     96/100   outcome pass rate: when true 0.35, when false 0.00
no unexpected tools           87/100   outcome pass rate: when true 0.33, when false 0.38
no tool errors               100/100   outcome pass rate: when true 0.34, when false nan

mean step efficiency (minimal model calls / actual): 0.88
```

No new fixtures here: the same 137 traces from module 5, read as trajectories against dataset v1's
`expected_tools`, with the 37 missing-detail queries left out (their right trajectory is a question). Calling the
right tools is necessary, not sufficient. "No unexpected tools" does not predict the outcome at all here, which
is worth knowing before you put tool precision on a dashboard.

## 6. Planner and specialists: the transition-failure matrix

```bash
uv run mediadoctor-lab07 agents
```

```text
Planner + specialists on 53 dev and test queries: pass 35/53 = 0.66 [0.53, 0.77]

Transition-failure matrix (failed runs only): row = last state that succeeded, column = first state that failed

last ok \ failed        answer  codec_caps     handoff        plan
start                        .           .           .           4
evidence                     6           .           .           .
handoff                      .           5           .           .
logcat_grep                  .           1           .           .
plan                         .           .           2           .

Handoff and tool errors (all runs): wrong route 4, brief lost a name 2, tool call errors 13
step efficiency, passed runs: mean 0.98 (n=35, below 1.0: 5)
step efficiency, failed runs: mean 1.00 (n=18, below 1.0: 0)
```

The reference trajectory for each query is in `data/labels/module07_agents.csv` (expected route and tools, from the
module 3 scenarios, plus the outcome label). `lab07.states` turns a run into states and decides which succeeded:
the plan matches the expected route; each brief contains every file, device, and log name from the question; each
tool call ran without an error; the expected evidence was gathered; the answer passed. Step through one failure:

```bash
uv run mediadoctor-lab07 run m4q010
```

```text
[plan    ] planner    {"route": ["device"]} ...
[handoff ] planner   device {"to": "device"} The user asks: our thumbnail grid crashes while scrolling on the lumen-l3 ...
[tool    ] device    logcat_grep {"log": "thumbs_codec_exhaustion.txt", ...} ...
[tool    ] device    codec_caps {"device": "Lumen L3", "mime": "video/avc"} ERROR Error: device profile not found: 'Lumen L3.json'. ...
[findings] device      Findings: The tool call failed, so there is no evidence to report.
[answer  ] planner     Likely cause: Thumbnail grids often run out of memory when bitmaps are not recycled. ...

states: [('plan', True), ('handoff', True), ('logcat_grep', True), ('codec_caps', False), ('evidence', False), ('answer', False)]
first failure: ('logcat_grep', 'codec_caps'); model calls 4, minimal 4
```

Everything after `codec_caps` failed too, but only the first failure is counted: fixing it is what changes the
outcome. Look at one run per matrix cell (the `note` column in the labels file says what was planted) and decide on
one fix per cell.

## 7. Images: vision judges and spectrogram answers

```bash
uv run mediadoctor-lab07 vision
```

```text
frame-blocking: detects the artifact 4/6 = 0.67 [0.30, 0.90]; leaves other frames alone 9/10 = 0.90 [0.60, 0.98]
    severe  detected 3/3
    mild    detected 1/3
    false alarms: banding_severe_b.png
frame-banding: detects the artifact 4/6 = 0.67 [0.30, 0.90]; leaves other frames alone 9/10 = 0.90 [0.60, 0.98]
    severe  detected 3/3
    mild    detected 1/3
    false alarms: blocking_severe_gradient.png

Spectrogram answers (code check: the Defect line matches the label)
  ...
  spec_dropout_1000.png  label dropout   answer none      WRONG
  spec_clipping_440.png  label clipping  answer clipping  ok
  spec_clipping_1000.png label clipping  answer noise     WRONG
  correct 4/6 = 0.67 [0.30, 0.90]
```

Open the images in `data/media/frames/` (any image viewer) next to `data/labels/module07_images.csv` and judge a
few yourself before reading the judge's verdicts. The mild cases are the hard ones for people too: the 100 ms
dropout is a thin line in the spectrogram.

The judge specs reuse module 5's format (`config/judges/frame-blocking.v1.toml`, `frame-banding.v1.toml`) with a
vision prompt (`vision.VISION_JUDGE_SYSTEM`). Look at what a request contains and what the fixture stores:

```python
import json

from evalkit.fixtures import compact_request
from mediadoctor import lab07, vision

req = vision.judge_request(lab07.spec("frame-blocking"), "blocking_mild_testsrc.png")
print(len(json.dumps(req)), "bytes sent")
print(json.dumps(compact_request(req)["messages"][0]["content"][0], indent=1))
```

To regenerate the images (needs FFmpeg): `bash scripts/make_module07_images.sh`. The script is deterministic on one
FFmpeg build, but a different FFmpeg or x264 version can change a few bytes, which changes the fixture keys; the
images are committed so you never need to.

## 8. The report

```bash
uv run mediadoctor-lab07 report --out runs/m7_report.md
```

It collects every table above in one Markdown file. Add a short section at the top: for each architecture, the one
component eval you would watch, and the next fix the numbers point to.

## 9. Optional: record real runs

With an API key, any part can be recorded live (`EVALS_LLM_MODE=record`). For example, the RAG answers and both
judges on them:

```bash
EVALS_LLM_MODE=record uv run python -c "
from mediadoctor import lab07
lab07.rag_runs()
lab07.rag_verdicts('faithfulness')
"
```

That is 96 Sonnet calls of about 600 input tokens plus 96 Haiku judge calls, well under a dollar at the prices in
`config/models.toml`. Recording overwrites the synthetic records with the same keys; `git checkout fixtures/`
restores them. Real outputs need real labels: label at least the disagreements with the old labels before reading the
numbers. The chat sessions are the most expensive part (each turn re-sends the conversation), and a real simulated
user will produce new transcripts, so its sessions need new labels too.

## Checkpoint

- [ ] `uv run pytest -q tests/test_retrieval.py tests/test_trajectory.py tests/test_lab07.py` passes
- [ ] The retrieval table, with your reading of the overall and the codec intervals
- [ ] For the improved RAG system, the next fix (retrieval or generation) and the numbers behind it
- [ ] Two chat sessions you read in full, with the session-level and turn-level verdicts you would give
- [ ] The transition-failure matrix with one proposed fix per non-empty column
- [ ] The vision judges' per-severity results and how many frames you would need to trust them
- [ ] `runs/m7_report.md` with your summary at the top
