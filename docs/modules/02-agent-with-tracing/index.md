# 2. A measurable agent with tracing

!!! note "Coming soon"
    This module is planned but not written yet. The outline below is the approved plan.

**Goal:** Build the running agent so that every run leaves an inspectable trace.

**Estimated time:** 8 hours

## Learning goals

- Build a Claude tool-use loop with typed tools (`search_kb`, `ffprobe`, `codec_caps`, `logcat_grep`)
- Emit spans that follow the OpenTelemetry GenAI conventions
- Store traces as JSONL and browse them with an `evalkit view` CLI

## Artifacts you will produce

- `labs/mediadoctor` tool-using agent
- `evalkit.trace` and the trace viewer
- First 100 traces

Each module follows the same shape as [module 1](../01-why-evals/index.md): lesson, lab, exercises with collapsed solutions, and a quiz.
