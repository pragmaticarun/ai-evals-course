# Lab 2: Trace the agent (offline)

**Time:** about 3 hours. **Needs:** the setup from [lab 1](../01-why-evals/lab.md).
**Does not need:** an API key, ffmpeg, or network access. Everything replays from committed fixtures.

## 1. Update and check

```bash
git pull
uv sync
uv run pytest -q
```

## 2. Look at the inputs the tools read

```bash
ls data/media data/devices data/logs
uv run python -c "from mediadoctor.tools import ffprobe; print(ffprobe('hdr10_hevc_1080p.mp4'))"
uv run python -c "from mediadoctor.tools import codec_caps; print(codec_caps('lumen-l3', 'hevc'))"
uv run python -c "from mediadoctor.tools import logcat_grep; print(logcat_grep('live_resume.txt', 'exception'))"
```

Each tool returns a JSON string, which is exactly what the model receives as a `tool_result`. Read
`labs/mediadoctor/src/mediadoctor/tools.py`: note how unknown file names produce an error that lists the valid
choices, and how `ffprobe` reads the cache in `data/media/probes.json` rather than running the binary.

## 3. Run the agent with tracing

```bash
uv run mediadoctor-lab02 run --out runs/m2_traces.jsonl
```

You should see the per-trace table from the lesson (8 traces, total cost $0.0578), then the check table, then
`wrote 53 spans`. Run it twice and compare the files: replay traces are identical byte for byte.

```bash
uv run mediadoctor-lab02 run --out runs/again.jsonl > /dev/null && cmp runs/m2_traces.jsonl runs/again.jsonl && echo identical
```

## 4. Read traces

```bash
uv run evalkit view runs/m2_traces.jsonl                    # one line per trace
uv run evalkit view runs/m2_traces.jsonl m2q02              # a healthy three-step run
uv run evalkit view runs/m2_traces.jsonl m2q03 --results    # the fabricated-evidence run
uv run evalkit view runs/m2_traces.jsonl m2q08              # the expensive loop
uv run evalkit view runs/m2_traces.jsonl m2q04 --all        # every attribute
```

For each of m2q02, m2q03, and m2q08, write two lines in your notes: what the agent did, and the first point where
something went wrong (if anything did). Keep these notes; module 3 starts from them.

Then open `runs/m2_traces.jsonl` in an editor. One line is one span. Find the `retrieval` span inside m2q06 and read
its `parent_span_id`: it points at the `execute_tool search_kb` span.

## 5. Read the instrumentation

Open `labs/mediadoctor/src/mediadoctor/toolagent.py` and `labs/evalkit/src/evalkit/trace.py`. Find:

- where the `chat` span gets its token counts and cost;
- where a `ToolError` becomes both an `is_error` tool result *and* an `ERROR` span status;
- where the virtual clock is advanced, and why that line does nothing in live mode.

## 6. Export to OTLP

```bash
uv run evalkit otlp runs/m2_traces.jsonl -o runs/m2_otlp.json --openinference
uv run python -c "import json; b=json.load(open('runs/m2_otlp.json')); print(len(b['resourceSpans'][0]['scopeSpans'][0]['spans']), 'spans')"
```

That file is an OTLP/JSON request body. [Sending traces to Phoenix, Langfuse, and Braintrust](backends.md) shows
where to send it.

## 7. Optional: real runs

With an API key in your environment or a git-ignored `.env`:

```bash
EVALS_LLM_MODE=live uv run mediadoctor-lab02 run --case m2q03 --out runs/live.jsonl
uv run evalkit view runs/live.jsonl m2q03
```

Live traces use the wall clock and random ids. Compare Claude's real behaviour on m2q03 with the planted one: does
it get the file name right? If it fails, does it admit it? Use `record` instead of `live` only if you intend to
replace the course fixtures (the lab tests pin the synthetic numbers and will then fail; restore with
`git checkout fixtures/`).

To run the real ffprobe instead of the cache (needs ffmpeg installed):

```bash
MEDIADOCTOR_LIVE_FFPROBE=1 EVALS_LLM_MODE=live uv run mediadoctor-lab02 run --case m2q05
```

## Checkpoint

- [ ] `uv run pytest -q` passes
- [ ] You can point to the span that proves m2q03's citation is fabricated
- [ ] You can explain why m2q08's input tokens grow with every call
- [ ] Notes on three traces, each naming the first thing that went wrong
- [ ] `runs/m2_otlp.json` exists
