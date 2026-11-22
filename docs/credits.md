# Credits

This course is original work: the text, code, datasets, knowledge-base notes, and recorded fixtures were written
for it. Its overall arc and several core ideas come from the work of **Hamel Husain** and **Shreya Shankar**, and
anyone serious about evals should read them directly and consider their course.

## Where ideas come from

| Idea used here | Where it is used | Source |
|---|---|---|
| Course arc: build a measurable agent, error analysis, evaluators you trust, CI/CD, red-teaming, improving cost and accuracy | Whole course | [AI Evals For Engineers & PMs](https://maven.com/parlance-labs/evals) (Maven course by Hamel Husain and Shreya Shankar) |
| The analyze, measure, improve cycle | Module 1 onward | Hamel Husain and Shreya Shankar's course and [AI Evals FAQ](https://hamel.dev/blog/posts/evals-faq/) |
| Layering evaluators from cheap assertions up to human and model review | Module 1 | [Your AI Product Needs Evals](https://hamel.dev/blog/posts/evals/), Hamel Husain |
| Looking at your data first; error analysis before metrics; custom data viewers | Modules 1, 3, 9 | [A Field Guide to Rapidly Improving AI Products](https://hamel.dev/blog/posts/field-guide/), Hamel Husain |
| Binary pass/fail judges aligned with a domain expert | Modules 1, 5 | [Using LLM-as-a-Judge For Evaluation](https://hamel.dev/blog/posts/llm-judge/), Hamel Husain |
| Open coding then axial coding of traces; theoretical saturation; noting the first failure in a trace; reviewing at least 100 traces; a single domain expert as "benevolent dictator"; binary pass/fail verdicts | Module 3 | [AI Evals FAQ](https://hamel.dev/blog/posts/evals-faq/), Hamel Husain and Shreya Shankar, and their [Maven course](https://maven.com/parlance-labs/evals) |
| Error analysis as the highest-return activity; bottom-up categories from your own data | Module 3 | [A Field Guide to Rapidly Improving AI Products](https://hamel.dev/blog/posts/field-guide/), Hamel Husain |
| Criteria drift: reviewers' criteria change as they see outputs | Modules 3, 5 | Shreya Shankar et al., [Who Validates the Validators?](https://arxiv.org/abs/2404.12272) |
| Instrument first; build simple custom viewers for traces | Module 2 | [A Field Guide to Rapidly Improving AI Products](https://hamel.dev/blog/posts/field-guide/), Hamel Husain |
| Validating evaluators against human labels; criteria drift | Modules 5, 6 | Shreya Shankar et al., [Who Validates the Validators? Aligning LLM-Assisted Evaluation of LLM Outputs with Human Preferences](https://arxiv.org/abs/2404.12272) (arXiv 2404.12272) |

## Module 3 references

| Topic | Source |
|---|---|
| Open, axial coding and theoretical saturation (origin in qualitative research) | [Grounded theory](https://en.wikipedia.org/wiki/Grounded_theory) (overview; the method goes back to Glaser and Strauss, 1967) |
| Pareto charts | [Pareto chart](https://en.wikipedia.org/wiki/Pareto_chart) |

The module 3 traces, scenarios, and reference annotations are synthetic-authored for this course
(`scripts/author_module03_fixtures.py`, `data/labels/`).

## Module 2 references

| Topic | Source |
|---|---|
| Tool use with Claude (the agent loop) | [Anthropic: tool use overview](https://docs.anthropic.com/en/docs/agents-and-tools/tool-use/overview) |
| Span and attribute names (`gen_ai.*`) | [OpenTelemetry semantic conventions for generative AI](https://github.com/open-telemetry/semantic-conventions-genai) (status: development) |
| OTLP/JSON encoding | [OpenTelemetry protocol specification](https://opentelemetry.io/docs/specs/otlp/) |
| OpenInference attributes | [OpenInference](https://github.com/Arize-ai/openinference) (Arize) |
| Phoenix ingestion | [Phoenix: exporter and OTLP](https://arize.com/docs/phoenix/tracing/concepts-tracing/otel-openinference/exporter) |
| Langfuse ingestion | [Langfuse: OpenTelemetry](https://langfuse.com/integrations/native/opentelemetry) |
| Braintrust ingestion | [Braintrust: send OpenTelemetry traces](https://docs.braintrust.dev/integrations/sdk-integrations/opentelemetry/send-traces-and-logs) |
| Sample clips | Generated with [FFmpeg](https://ffmpeg.org/) test sources (`scripts/make_media.sh`); probed with ffprobe |

The two devices in `data/devices/` and the logs in `data/logs/` are fictional and written for this course.

This course is independent and is not affiliated with or endorsed by Hamel Husain, Shreya Shankar, Parlance Labs,
Maven, or Anthropic.

## Tools

[uv](https://docs.astral.sh/uv/), [Zensical](https://zensical.org/) and
[Material for MkDocs](https://squidfunk.github.io/mkdocs-material/), [pytest](https://pytest.org/), [FFmpeg](https://ffmpeg.org/),
[Ruff](https://docs.astral.sh/ruff/), [gitleaks](https://github.com/gitleaks/gitleaks), and the
[Anthropic Python SDK](https://github.com/anthropics/anthropic-sdk-python).
