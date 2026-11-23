# Lab 12: Capstone eval report (offline)

**Time:** about 4.5 hours. **Needs:** the setup from [lab 1](../01-why-evals/lab.md) and labs 1 to 11 (you do not
have to have finished them; their fixtures are in the repo). **Does not need:** an API key
([Make it your own](extensions.md) does).

You will run the whole eval loop in one command, choose a slice (the suggested one is DRM and Widevine questions),
take it through error analysis, judges, and an improvement experiment, write the eval report, review it against the
rubric, spend the held-out look, and publish the report on your copy of the course site. Keep working files under
`runs/`, which git ignores.

!!! info "Synthetic-authored model behaviour, real everything else"
    The capstone reads the fixtures of modules 1 to 11. Their model turns, token counts, and latencies were written
    by `scripts/author_module*_fixtures.py` and are labelled `"source": "synthetic-authored"`; the datasets were
    generated for the course. The numbers show what the method produces and make no claim about how Claude models
    behave on your system. The pipeline, agent loop, tools, checks, judges' prompts, prices, and statistics are
    real code. To put real numbers in your report, re-record live ([Make it your own](extensions.md), option A).

## 1. Update and check

```bash
git pull
uv sync
uv run pytest -q tests/test_capstone.py
uv run mediadoctor-capstone --help
```

## 2. Run the whole loop

```bash
uv run mediadoctor-capstone run
```

You should see the eleven stages from Step 1 of the lesson, with module 9 flagged. For each line, write one sentence
in `runs/capstone/notes.md`: what decision this stage informs. If you cannot write the sentence, reread that module's
summary. Then open `labs/mediadoctor/src/mediadoctor/capstone.py` and find the function for one stage (`m05`, say):
every number comes from the module's own code, called the same way its lab does.

## 3. Choose your slice

```bash
uv run mediadoctor-capstone slices
```

The suggested slice is **drm-resolution** (DRM, Widevine security levels, and resolution caps). It is a risk-based
choice: a wrong Widevine answer sends a customer to the wrong team or blames a device for a licence problem. Write
down, before you look further, what you expect: how many failures, which modes.

If you prefer, take any other topic, or the alternative project's slice from the syllabus (CrashTriage, see
[Make it your own](extensions.md), option B).

## 4. Error analysis on the slice

List the slice's dev queries and how each configuration did:

```python
from mediadoctor import capstone as C
from mediadoctor import lab11

ids = C.dev_ids("drm-resolution")
labels = lab11.reference_labels()
for i in ids:
    q = C.case_by_id()[i]["question"]
    print(i, labels[("v1", i)], labels[("retry", i)], q[:70])
```

For every query that fails under `v1`, read the trace (`uv run mediadoctor-lab11 trace v1 CASE`), and write an open
note on the first thing that went wrong, as in [module 3](../03-error-analysis/index.md). Then read two that pass
under both: error analysis that only reads failures misses the near-misses. Map your notes to the taxonomy. Did you
find a mode that is not in it? If so, that is [option C](extensions.md) of Make it your own.

Note the coverage of the slice in the report draft (next section) as well: every DRM query in the dataset carries
device evidence, and none carries a log. What questions does that leave untested?

## 5. Judges on the slice

The report shows the retry step's self-check judge on your slice. On DRM there are no defective first answers under
`v3-cache`, so its TNR on the slice is undefined: the slice cannot tell you whether the judge would catch a DRM
mistake. Find the module 5 judge that applies to the slice's main risk (`false-premise`, for the two v1 failures)
and print its validation on the test split:

```bash
uv run mediadoctor-lab05 judge false-premise --split test
```

Write down whether its test set contains any DRM traces. A judge validated on other topics is a judge you are
trusting on this one.

## 6. The improvement experiment, on the slice

In the replay, the experiment is module 11's chain, read on your slice. Pre-register first: in
`runs/capstone/prereg.md`, write the hypothesis ("the v2 prompt's premise check removes DRM's false-premise
failures"), the metric (slice success), and the rule (paired 95% CI above zero). Then run:

```python
from mediadoctor import capstone as C

ids = C.dev_ids("drm-resolution")
for a, b in [("v1", "v2"), ("v2", "v3"), ("v1", "retry")]:
    p = C.paired_on(ids, a, b)
    print(f"{a} -> {b}: {C.diff(p)}  fixed {p.b_only} broken {p.a_only}")
```

Every interval reaches zero: with 15 queries and two failures to fix, no experiment on this slice alone can pass a
superiority rule. That is the finding. Use the report's last slice paragraph to say how many queries you would
need, and write the follow-up as a data task (module 4: more DRM tuples, including log evidence), not as a prompt
task.

## 7. Generate the report

```bash
uv run mediadoctor-capstone report --slice drm-resolution --out runs/capstone/report.md
uv run mediadoctor-capstone check runs/capstone/report.md
```

The generated report is a **draft**. Its numbers are right; its prose is generic. Edit it:

- Rewrite **Decision requested** for your audience (the reference asks a product owner; yours might ask a support
  lead whether DRM questions can be routed to MediaDoctor).
- Rewrite the slice section's opening with your reason for choosing the slice and what you expected in section 3.
- Add your error-analysis notes from section 4 and the judge question from section 5 to Risks.
- Make sure every claim you add has a number with an interval or a case id.

Run `check` again after editing.

## 8. Review against the rubric

Score your report with the [rubric](rubric.md), honestly, criterion by criterion. Then go through the self-review
checklist under it. If you can, swap reports with someone and score each other's; the [exercises](exercises.md)
practise this on the reference report.

## 9. Spend the held-out look

When the report is final apart from the held-out numbers:

```bash
uv run mediadoctor-capstone report --slice drm-resolution --release --out runs/capstone/report-release.md
cat runs/capstone/holdout_log.csv
```

Copy the held-out lines into your edited report. Do not change the recommendation because of them unless they
reverse the direction; that rule was written before you looked.

## 10. Publish it on the site

On your fork, put the report where the site can find it, link it in the nav, and build:

```bash
cp runs/capstone/report.md docs/capstone/my-report.md
# mkdocs.yml, under "Capstone report:":  - "My report": capstone/my-report.md
uv run zensical build --clean --strict
python3 -m http.server -d site 8000   # open http://localhost:8000/capstone/my-report/
```

Relative links in the generated report point from `docs/capstone/` to the module pages, so they keep working. Push
to your fork, and the deploy workflow publishes it at `https://<you>.github.io/ai-evals-course/capstone/my-report/`.

## 11. Present it

Turn the report into a ten-minute talk with the [presentation outline](presentation.md). Rehearse the answer to the
question you least want: "how sure are you?"

## Checkpoint

You should have:

- `runs/capstone/notes.md` with one sentence per stage;
- error-analysis notes on every failing trace in your slice, mapped to the taxonomy;
- `runs/capstone/prereg.md`, written before the slice comparison;
- an edited `runs/capstone/report.md` that passes `mediadoctor-capstone check` and scores at least 3 on every
  rubric criterion;
- one logged look in `runs/capstone/holdout_log.csv`;
- the report on your copy of the site, built with `--strict`;
- a presentation outline with your three numbers.

Next: the [exercises](exercises.md).
