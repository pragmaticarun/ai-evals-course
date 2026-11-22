# Lab 4: Build dataset v1 from synthetic queries (offline)

**Time:** about 3 hours. **Needs:** the setup from [lab 1](../01-why-evals/lab.md) and the module 3 tools.
**Does not need:** an API key or network access.

You will define test dimensions in a config file, generate tuples with different strategies, turn them into
queries (replayed from fixtures), remove near-duplicates, print coverage matrices, freeze dataset v1 with splits,
and then run the module 2 agent on the new dev split and read the traces with the module 3 tools. Keep your own
files under `runs/`, which git ignores.

!!! info "Synthetic-authored fixtures"
    The query writer's responses were written by a template writer (`scripts/module04_writer.py`) and recorded
    through the real batch code path; the agent's responses on the dev slice were scripted from the module 3
    scenarios. All are labelled `"source": "synthetic-authored"`, and so are the reference labels. Section 9 shows
    how to generate your own with a key.

## 1. Update and check

```bash
git pull
uv sync
uv run pytest -q
```

## 2. The dimensions file

Open `config/synth/mediadoctor.toml`. Each `[[dimension]]` has a name, a description, and values; each
`[[exclude]]` rule removes tuples that match all of its `when` conditions and any of its `forbid` values.

```bash
uv run mediadoctor-lab04 dims
```

Expected: `full product 4320; valid after 9 rules: 1342`, followed by the rule reasons. For each rule, decide
whether it is a fact about the world or a fact about *our test data*. (Hint: "no log captures exist for these
topics" is the second kind.) Write your answers in `runs/m4_notes.md`; you will need them in exercise 1.

## 3. Compare tuple strategies

```bash
uv run mediadoctor-lab04 tuples --strategy sample --n 50
uv run mediadoctor-lab04 tuples --strategy sample --n 200
uv run mediadoctor-lab04 tuples --strategy pairwise
uv run mediadoctor-lab04 tuples                    # the course mix: pairwise, then stratified by topic
```

Expected first lines: `216/242 (89%)`, `239/242 (99%)`, `34 tuples ... 242/242 (100%)`, and `200 tuples ...
242/242 (100%)`. In the 50-sample matrix, find the topic with the fewest tuples and the empty cell. Then look at
the stratified mix: how many audio-focus tuples does it have, compared with 5 in the 200-sample?

Try another seed (`--seed 7`) for the random sample. Do the gaps move? They will; that is the problem with relying
on chance.

## 4. The naive baseline

```bash
uv run mediadoctor-lab04 naive
```

This replays the response to a single prompt: "Generate 50 diverse, realistic test questions ...". Note the
opening words, the LLM-style tells, the topic counts from the keyword tagger, and `queries naming a file, device,
or pasting a log: 0/50`. Read the 50 questions themselves:

```bash
uv run python -c "from mediadoctor.lab04 import naive_queries; print('\n'.join(naive_queries()))"
```

Would MediaDoctor be able to fail any of these in an interesting way? Most can be answered with a paragraph of
general advice, which is the one thing it is already good at.

## 5. Generate the queries

```bash
uv run mediadoctor-lab04 generate --out runs/m4_v1.jsonl
```

This builds the 200 tuples, sends one request per tuple (replayed; with a key and `--batch`, as one Message Batch),
removes near-duplicates within the same evidence and ambiguity values, assigns grouped splits, and prints a report:

```text
200 queries generated, 18 dropped as near-duplicates, 182 kept
  dropped t026 (similarity 0.96 to t023)
  ...
splits: {'train': 88, 'dev': 45, 'test': 49}; near-duplicate pairs across splits: 0
```

Look at one request before going further. This is exactly what the synth model receives:

```bash
uv run python -c "
import json
from mediadoctor.lab04 import load_default_space, make_tuples
from mediadoctor.synth_spec import build_synth_request
req = build_synth_request(make_tuples(load_default_space())[20])
print(req['system']); print(json.dumps(json.loads(req['messages'][0]['content']), indent=1))"
```

Now read at least 30 queries in `runs/m4_v1.jsonl`, with their tuples next to them. For each, ask: would a real
person write this? Does it match its tuple? Note anything that sounds generated.

## 6. Check queries against their tuples

Reading finds what code cannot; code finds what tired eyes skip. Run the built-in checks:

```bash
uv run mediadoctor-lab04 check --dataset runs/m4_v1.jsonl
```

```text
m4q022  does not mention hdr10_hevc_1080p.mp4
182 queries checked, 1 problems
```

Open `m4q022`. The tuple has `evidence=media-file`, but the writer used a template with no file in it, so the
question says "our HDR10 videos". The query is still realistic, but it is now an `evidence=none` test case filed
under the wrong label. This defect is left in v1 on purpose, so the check has something to find. In a real dataset,
regenerate or relabel it before freezing.

## 7. Coverage report

```bash
uv run mediadoctor-lab04 coverage --dataset runs/m4_v1.jsonl > runs/m4_coverage.txt
uv run mediadoctor-lab04 coverage --dataset runs/m4_v1.jsonl --rows persona --cols expertise >> runs/m4_coverage.txt
uv run mediadoctor-lab04 coverage --dataset runs/m4_v1.jsonl --rows goal --cols ambiguity >> runs/m4_coverage.txt
```

Each command also prints pair coverage per split: dev covers 202 of 242 pairs, test 183. Which pairs does the test
split miss? (`evalkit.synth.pairs_of` and `feasible_pairs` will tell you.) A held-out set that misses a slice cannot
report on it.

## 8. Freeze, and compare with the course's v1

The course's frozen copy is `data/datasets/module04_v1.jsonl`, with `module04_v1.manifest.json` beside it. Check
that your run produced the same file:

```bash
sha256sum runs/m4_v1.jsonl data/datasets/module04_v1.jsonl
grep sha256 data/datasets/module04_v1.manifest.json
```

All three hashes match, because every step is seeded and replayed. If you change the dimensions file, the
`space_sha256` in your manifest changes too, and the result is a new version, not a new v1.

## 9. Feed the dev split to the agent and the module 3 tools

```bash
uv run mediadoctor-lab04 agent --out runs/m4_traces.jsonl
```

This runs the module 2 agent on the 37 dev queries that match a module 3 scenario. Now use the module 3 tools on
the new traces, pointing them at the new dataset with `--cases`:

```bash
uv run mediadoctor-lab03 signals   --traces runs/m4_traces.jsonl --cases data/datasets/module04_v1.jsonl
uv run mediadoctor-lab03 retrieval --traces runs/m4_traces.jsonl --cases data/datasets/module04_v1.jsonl
uv run mediadoctor-lab03 annotate  --traces runs/m4_traces.jsonl --labels runs/m4_labels.csv --annotator "your name"
```

Label all 37 the module 3 way: verdict, a note on the first thing that went wrong, the step. Do it before reading
the reference. Then compare:

```bash
uv run mediadoctor-lab03 compare --labels runs/m4_labels.csv --reference data/labels/module04_dev_reference.csv
uv run mediadoctor-lab04 by-dimension --dim ambiguity
uv run mediadoctor-lab04 by-dimension --dim ambiguity --labels runs/m4_labels.csv
```

The first `by-dimension` uses the reference labels; the second uses yours.

Questions to answer in your notes:

- Which of your failures did `signals` flag? Which flagged traces were passes?
- Did you find the two new modes (accepting a false premise; assuming a detail the user did not give)? What did you
  call them?
- Break failures down by `evidence` and `expertise` as well. Is any other dimension doing work?

## 10. Seed with real queries

```bash
uv run mediadoctor-lab04 gaps
```

The ten beta queries in `data/synth/beta_queries.jsonl` stand in for early real traffic. (They are hand-written for
the course and labelled synthetic-authored; replace them with yours when you have them.) The command shows their
coverage, the values they never use, and how many generated tuples fill the remaining pairs.

## 11. Optional: generate with Claude

With an API key, write your own queries with the real synth model, as one batch:

```bash
EVALS_LLM_MODE=live uv run mediadoctor-lab04 generate --batch --out runs/m4_live.jsonl
uv run mediadoctor-lab04 check --dataset runs/m4_live.jsonl
```

Two hundred short requests to the small model cost well under a dollar at batch prices. A batch usually finishes
in minutes but can take up to 24 hours; the command polls every 30 seconds. Expect more varied phrasing than the
templates and different defects: run `check`, then read the queries before you trust them.

## Checkpoint

- [ ] `runs/m4_notes.md` with your view of each exclusion rule
- [ ] `runs/m4_v1.jsonl` matching the course hash, and `runs/m4_coverage.txt`
- [ ] 30 queries read, with notes on what sounds generated
- [ ] `runs/m4_labels.csv` with 37 dev-slice labels, and your failure rates by dimension
- [ ] A sentence on what the beta queries told you about your dimensions
