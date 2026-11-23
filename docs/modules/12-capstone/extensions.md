# Make it your own

The capstone runs offline so that everyone gets the same numbers. These options swap in real behaviour, a different
system, or a failure mode you found yourself. Each one ends with the same deliverable: a report that follows the
[template](../../eval-templates/eval-report.md) and passes the [rubric](rubric.md).

## Option A: Re-record live with your Anthropic key

Replace the synthetic-authored model turns with real Claude responses and see how many of the course's numbers
survive.

!!! warning "Record and live call Claude Haiku 4.5 only"
    `[live]` in `config/models.toml` sends every record and live request to `claude-haiku-4-5`, whatever role it is
    for, and refuses any other model before a request leaves the machine (`ModelNotAllowedError`). No Opus, Fable,
    Sonnet, or Haiku 5.5 call is made with your key. Three consequences:

    - **Model comparisons collapse.** Module 11's `haiku`, `cascade`, and Sonnet variants all run on Haiku 4.5, as do
      the judges and the simulated user, so a live run can compare prompts and strategies, not models. Self-preference
      (module 5) is maximal: judge and agent are the same model.
    - **Prompt caching will not cache.** Haiku 4.5's minimum cacheable prompt is 4,096 tokens; MediaDoctor's cached
      prefix is about 1,000, so `v3-cache` costs the same as `v3`.
    - **Recordings are keyed with the model called.** To replay your own recordings, set
      `EVALS_REPLAY_LIVE_MODEL=1`; without it, replay keeps using the course fixtures.

    Haiku 4.5 is $1 / $5 per million tokens and thinks only when asked, so no thinking or effort is sent. Re-recording
    every module costs roughly $8 at the course's token counts (real answers may be longer).

1. Set `ANTHROPIC_API_KEY` in your shell (never in a file in the repo; the repo's gitleaks check will catch a
   committed key, but do not rely on it).
2. Record into `runs/`, not into `fixtures/`, so that the course fixtures stay intact. The pattern is the one in
   [lab 11's optional live section](../11-improving-with-evidence/lab.md#optional-record-a-few-live-runs):
   `LLM(namespace=..., mode="record", fixtures_dir=Path("runs/live-fixtures"), source="live")`.
3. Start small: ten dev queries for `v1` and `retry` cost a few cents (`uv run mediadoctor-lab11 cost` estimates the
   full dev suite). Then the 108 dev queries for both, then the held-out split once.
4. `EVALS_LLM_MODE` controls the mode for code that builds its own client: `replay` (the default, no key, no
   network), `record` (call the API and save each response), or `live` (call the API, save nothing). See the
   [README](https://github.com/pragmaticarun/ai-evals-course#replay-record-and-live) for details.
5. Re-run your error analysis on the live traces before you trust any automated label: the reference labels
   describe the synthetic fixtures, not your live run. Label a sample by hand (module 3), re-validate the judges on
   it (module 5), then run the experiment.

Expect differences. Real models fail in ways the fixture scripts did not write, latencies have a longer tail, and
prompt caching only pays when calls arrive within the cache lifetime. The report you write from a live run is the
one that means something; the replay taught you the method.

## Option B: A different agent

The syllabus's alternative project, **CrashTriage**, triages Android tombstones and ANR traces: given a crash dump
and a short description, it names the likely cause (native crash, deadlock, main-thread I/O, OOM), the responsible
module, and the next diagnostic step. It works well as the capstone slice because its failure modes are easy to
check in code (a wrong signal number, a misread backtrace frame) and hard to judge (a plausible but wrong root
cause).

To build it with the course's toolkit:

1. Write 20 hand-labelled cases (module 1), with tombstones from your own devices or AOSP's test data.
2. Reuse `evalkit.Tracer` and the agent loop from `mediadoctor.toolagent`, with tools such as `parse_tombstone`,
   `symbolize`, and `grep_anr`.
3. Open-code 100 traces (module 3), build a dimensions sheet (module 4: crash type × evidence × Android version ×
   reporter expertise), validate a root-cause judge (module 5), and follow the rest of the loop.
4. Copy `mediadoctor/capstone.py` and replace each stage function with your agent's; the report renderer only
   needs the numbers.

Any other agent you work on qualifies: a code-review bot, a media-transcoding assistant, an internal support bot.
The test is whether you can name its failure modes from 100 traces.

## Option C: Add a new failure mode

Module 11 labelled four modes. Pick one it did not track, or one you found in your slice's error analysis, and take
it through the loop:

1. **Define it** in the taxonomy format (`docs/eval-templates/failure-taxonomy.md`): name, definition, a passing and
   a failing example, severity.
2. **Find it**: label every dev trace of `v1` and `retry` for the mode (a CSV like
   `data/labels/module11_reference.csv`, in `runs/`).
3. **Detect it**: a code check if the mode is mechanical, or a judge if it is not. For example, an Android API
   level in the answer that contradicts the knowledge base: `data/kb_v2/audio-focus.md` says `AudioFocusRequest`
   needs API 26, and one of the reference report's surviving audio-focus answers, `m4q099`, says 21. Validate the
   detector against your labels with TPR and TNR.
4. **Measure it**: before and after, paired, with intervals, and add it to the report's taxonomy table.
5. **Gate it**: add the check to `evals/` so that CI blocks a regression (module 8).

A good new mode is one that matters to users and that none of the existing checks catches. Wrong API levels are a
strong candidate for MediaDoctor: they look right, they pass every format and citation check, and they waste a
developer's afternoon.

## Option D: A second slice, chosen by risk

Run the whole capstone a second time on another topic, and add a section to your report comparing the two: which
slice is weaker, and can your data tell? This is the cheapest option and practises the most common real request
("how are we doing on X?").
