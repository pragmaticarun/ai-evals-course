# Lab 9: A week in production, and a review app (offline)

**Time:** about 4 hours. **Needs:** the setup from [lab 1](../01-why-evals/lab.md), and modules 3, 5, and 6. A
browser for the app. **Does not need:** an API key.

You will replay a simulated week of MediaDoctor traffic, find the drift event in it from the monitoring output,
build a review queue, review traces in the annotation app, measure your agreement with a second annotator, and turn
your labels into a new failure mode and golden-dataset candidates. Keep your own files under `runs/`, which git
ignores.

!!! info "Synthetic-authored traffic"
    The week's traffic and feedback, the 40 AV1 traces, their reference labels, the online judge's verdicts on them,
    and annotator B's labels were written by `scripts/author_module09_fixtures.py` and are labelled
    `"source": "synthetic-authored"`. The traces the requests replay are module 3's recorded traces plus 40 recorded
    for this module. Every number the lab prints is computed from those files.

## 1. Update and check

```bash
git pull
uv sync
uv run pytest -q tests/test_monitor.py tests/test_annotate_app.py tests/test_lab09.py
```

New files to skim:

- `labs/evalkit/src/evalkit/monitor.py`: sampling, weighted rates, PSI, p-charts, CUSUM, the two-proportion test;
- `labs/evalkit/src/evalkit/annotate.py`: `cohen_kappa` and `kappa_report` at the end;
- `labs/mediadoctor/src/mediadoctor/lab09.py`: the simulated week, the checks and signals, the queue, the online
  judge, closing the loop, and the CLI;
- `labs/annotate/`: the review app (`app.py` routes, `render.py` domain views, `store.py` files, `templates/`,
  `static/keys.js`);
- `data/production/traffic.jsonl` (the week) and `data/labels/production_modes_v1.toml` (the taxonomy you start
  with).

## 2. Replay the week

```bash
uv run mediadoctor-lab09 simulate
```

This writes `runs/m9/traces.jsonl`: 776 requests and 4,684 spans in the same OpenTelemetry-style format as module 2,
with each request's id, time, user, app version, and model snapshot stamped on its root span. Open a few lines. Note
which attributes you would want on a real dashboard; `mediadoctor.sim.source_case` is the simulation's bookkeeping,
and the app hides it.

## 3. Monitor

```bash
uv run mediadoctor-lab09 monitor
```

Read the output top to bottom before reading on, and write down three things: when something changed, what changed,
and who it affects. Then check against this reading:

- the daily table: Monday to Wednesday are steady; from Thursday the AV1 share, the topic PSI, the app 4.2 share, the
  tool-error rate, and the evidence-failure rate all rise, and `vela-v2` appears as a new device;
- the p-chart for `evidence_fail`: above its limit from Thursday on;
- CUSUM: `tool_error` alarms Thursday 14:57 IST, 5.0 hours after the rollout started; `evidence_fail` on Friday at
  05:42; thumbs-down never;
- the snapshot change on Tuesday: 1/125 to 3/115, p = 0.27, nothing to see (and nothing there);
- by app version after the rollout: 4.1.3 looks like the reference week; 4.2.0 does not.

`--json runs/m9/dashboard.json` writes the same numbers for the app's dashboard page.

Two more views:

```bash
uv run mediadoctor-lab09 signals   # precision and recall of each user and system signal
uv run mediadoctor-lab09 tagger    # how good the topic tagger behind the PSI is
```

The tagger scores 1.000 on the week's questions and 0.835 on module 4's questions it never saw. Note the topics it
confuses: a PSI built on it inherits those errors.

## 4. The online judge

```bash
uv run mediadoctor-lab09 judge
```

The judge ran on a 30% random sample. Compare the raw and corrected rates before and after the rollout with the
simulation's truth column, and write two sentences: what the raw drop tells you, and why the corrected interval after
the rollout is so wide. Then read the last line: the judge's TPR on the new AV1 traces is lower than on its validation
set. What would you label to re-validate it?

## 5. Build the queue

```bash
uv run mediadoctor-lab09 sample --limit 60
```

Each line is a queue item: the request, how many identical requests it stands for (`+7`), the day, and why it was
picked (`signal:...` or `stratum:...`, with random picks marked `random`). Notice the rhythm: two triggered items,
then one random or stratified item. The queue is written to `runs/m9/queue.jsonl` with each item's inclusion
probability.

Before reviewing anything, compare the queue's failure rate with the week's:

```bash
uv run python -c "from mediadoctor import lab09; print(lab09.queue_bias())"
```

Unweighted, the queue says 0.553; weighted by 1/p, 0.364; the truth is 0.340. Keep that in mind when someone shows you
a rate computed from reviewed traces.

## 6. Review in the app

```bash
uv run mediadoctor-lab09 annotate
```

This rebuilds the trace store, the queue (60 items), and the dashboard, then serves the app at
<http://127.0.0.1:8009>. Enter a name; your labels go to `runs/m9/labels/labels-<name>.csv`.

Press `?` for the keys. The ones you will use most:

| Key | Action |
|---|---|
| `p` / `f` | pass / fail |
| `1` to `9` | toggle a failure mode (also sets fail) |
| `m` | name a new failure mode (sets fail; Enter saves) |
| `n` | write a note (Escape leaves the box) |
| `g` | flag as a golden-dataset candidate |
| Enter or `s` | save and load the next trace |
| `j` / `k` | next / previous without saving |
| `t` | expand or collapse all tool outputs |
| `c` | show the raw attributes |

Label the first 40 items. Judge each trace by module 3's rules: one verdict for the whole answer, every mode that
applies, and a short note on the first thing that went wrong. Read the answer with its citation marks (green: the
evidence is in the trace; red: it is not), then the tool outputs.

Somewhere in the first dozen items you will meet an answer about the `vela-v2` after `codec_caps` failed with an
unknown device, which describes the phone's decoders anyway. No mode in the v1 taxonomy fits. Press `m`, name it
`unknown-device-guess`, and use the same name for the next ones (the app adds it to the mode list after the first
use, in `runs/m9/labels/modes-added.toml`). Many of these answers also cite a decoder table the trace does
not contain: tag `fabricated-evidence` too, since a trace gets every mode that applies.

Then look at the other pages:

- `/` shows your progress through the queue;
- `/dashboard` is the monitoring summary from step 3;
- `/agreement` compares you with annotator B, whose labels on the same 40 traces ship with the lab;
- the export links download your labels, the taxonomy CSV (modes ranked by count and severity), golden candidates
  as JSONL, and your golden flags.

The app also runs on any trace store in the course's format, with no lab code involved:

```bash
uv run annotate serve --traces runs/m9/traces.jsonl --queue runs/m9/queue.jsonl \
    --modes data/labels/production_modes_v2.toml --out runs/m9/labels-v2 \
    --dashboard runs/m9/dashboard.json --compare b=data/labels/module09_annotator_b.csv
```

## 7. Agreement and scoring

```bash
uv run mediadoctor-lab09 agreement runs/m9/labels/labels-<name>.csv data/labels/module09_annotator_b.csv
uv run mediadoctor-lab09 score runs/m9/labels/labels-<name>.csv
```

The first prints kappa on verdicts and per mode, with counts, and the traces you disagree on. The second compares
your verdicts with the reference labels. For reference, annotator A (also shipped) agrees with B on 38 of 40 verdicts
(kappa 0.87), on every `unknown-device-guess` (kappa 1.00), and less well on `vague-next-step` (0.48: rare, so a
single disagreement costs a lot). Pick the two traces where you disagree most with B and write which definition in the
taxonomy caused it, and the sentence you would add to fix it.

## 8. Close the loop

```bash
uv run mediadoctor-lab09 close-loop runs/m9/labels/labels-<name>.csv \
    --flagged runs/m9/labels/golden-<name>.json --out runs/m9/candidates.jsonl
```

Each candidate is one distinct question that failed (or that you flagged), with its modes, a proposed split, and its
most similar existing golden question if that is close. Decide on each near-duplicate: keep, merge, or drop.

Compare your new mode with `data/labels/production_modes_v2.toml`, which adds `unknown-device-guess` with a
definition, a severity, and a detector. Exercise 5 writes the detector.

## Checkpoint

- [ ] Your three-line reading of the week (when, what, who), and the evidence for each line
- [ ] Two sentences on the online judge: what the raw drop means, and why the corrected interval is wide
- [ ] 40 labelled traces, with the new failure mode named and defined in your own words
- [ ] Your kappa with annotator B, overall and for the new mode, and one definition you would tighten
- [ ] The list of golden candidates, with your decision on each near-duplicate
- [ ] One sentence on why the thumbs-down rate never alarmed
