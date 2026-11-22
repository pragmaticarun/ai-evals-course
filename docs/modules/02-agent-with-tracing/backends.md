# Sending traces to Phoenix, Langfuse, and Braintrust

The course's own viewer is deliberately minimal. Once you have more than a few hundred traces, you will want a real
backend with search, filters, and dashboards. Because MediaDoctor's spans use the OpenTelemetry data model and the
GenAI attribute names, you are not locked into any vendor. This page shows how the pieces line up. All three products
change quickly, so check their current docs (linked below) before relying on a detail.

## The common path: OTLP over HTTP

All three accept the OpenTelemetry protocol (OTLP) over HTTP. There are two ways to get MediaDoctor's traces there:

1. **Convert the JSONL you already have:** `uv run evalkit otlp runs/m2_traces.jsonl -o runs/otlp.json` produces an
   OTLP/JSON `ExportTraceServiceRequest` body, which you can `POST` to the backend's traces endpoint with
   `Content-Type: application/json` and the backend's auth header. Good for experiments and for loading old runs.
2. **Use the OpenTelemetry SDK in the app:** replace `evalkit.trace.Tracer` with an OpenTelemetry `TracerProvider`
   and an OTLP exporter. Span names and attributes stay the same. This is the production route, with batching,
   retries, and sampling built in.

Replayed traces have timestamps on 2026-11-23 (the virtual clock's start). Most backends accept old timestamps, but
remember to filter by that date when searching.

## How the concepts map

| This course | OpenTelemetry | Phoenix (Arize) | Langfuse | Braintrust |
|---|---|---|---|---|
| One agent run | Trace (root span `invoke_agent`) | Trace | Trace | Trace / log row |
| `chat` span | Span with `gen_ai.operation.name=chat` | LLM span | Generation | LLM span |
| `execute_tool` span | Span with `gen_ai.operation.name=execute_tool` | Tool span | Tool or span observation | Tool span |
| `retrieval` span | Span with `gen_ai.operation.name=retrieval` | Retriever span | Retriever or span observation | Span |
| `evalkit.cost.usd` | Custom attribute | Metadata (Phoenix computes its own cost from tokens) | Can compute cost from model and tokens | Computes metrics from tokens |
| Trace checks (lab 2) | Not part of OTel | Evaluations attached to spans | Scores | Scores |
| Your labels (module 3) | Not part of OTel | Annotations | Annotations / scores | Human review scores |

## Phoenix

- **Endpoint:** a local Phoenix serves OTLP over HTTP at `http://localhost:6006/v1/traces`, on the same port as its UI
  (not the usual 4318). See [Phoenix: exporter and OTLP](https://arize.com/docs/phoenix/tracing/concepts-tracing/otel-openinference/exporter).
- **Attributes:** Phoenix renders spans best when they carry
  [OpenInference](https://github.com/Arize-ai/openinference) attributes (`openinference.span.kind`,
  `llm.token_count.*`, `input.value`, ...). `gen_ai.*` spans still arrive, but get less UI treatment. Add the
  OpenInference attributes with `evalkit otlp --openinference`, which maps our spans to `AGENT`, `LLM`, `TOOL`, and
  `RETRIEVER` kinds.
- **Format:** Phoenix's exporter docs default to protobuf. If your version rejects JSON bodies, use the
  OpenTelemetry SDK exporter (route 2 above).

## Langfuse

- **Endpoint:** `https://cloud.langfuse.com/api/public/otel/v1/traces` (EU; other regions and self-hosted instances
  have their own host), with Basic auth built from the project's public and secret keys, and the
  `x-langfuse-ingestion-version: 4` header for real-time ingestion. HTTP/JSON and HTTP/protobuf are accepted; gRPC is
  not. See [Langfuse: OpenTelemetry](https://langfuse.com/integrations/native/opentelemetry).
- **Attributes:** spans with `gen_ai.*` attributes (model, token usage) become *generations* with model, usage, and
  cost; other spans become regular observations in the tree. Langfuse also reads its own `langfuse.*` attributes,
  which take precedence if you want exact control.

## Braintrust

- **Endpoint:** `https://api.braintrust.dev/otel/v1/traces` with `Authorization: Bearer <API key>` and an
  `x-bt-parent` header naming the destination (`project_id:...`, `project_name:...`, or `experiment_id:...`).
  See [Braintrust: send OpenTelemetry traces](https://docs.braintrust.dev/integrations/sdk-integrations/opentelemetry/send-traces-and-logs).
- **Attributes:** Braintrust converts LLM calls in incoming spans into its own LLM spans, which can then be reused as
  prompts and scored.

## Example: posting the converted file

Keep keys out of your shell history and out of the repo. Put them in a git-ignored `.env` and load it first.

```bash
uv run evalkit otlp runs/m2_traces.jsonl -o runs/otlp.json --openinference

# Phoenix running locally (no auth by default)
curl -sS -X POST http://localhost:6006/v1/traces \
  -H 'Content-Type: application/json' --data-binary @runs/otlp.json

# Langfuse (keys from .env: LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY)
curl -sS -X POST https://cloud.langfuse.com/api/public/otel/v1/traces \
  -u "$LANGFUSE_PUBLIC_KEY:$LANGFUSE_SECRET_KEY" -H 'x-langfuse-ingestion-version: 4' \
  -H 'Content-Type: application/json' --data-binary @runs/otlp.json

# Braintrust (keys from .env: BRAINTRUST_API_KEY, BRAINTRUST_PROJECT_ID)
curl -sS -X POST https://api.braintrust.dev/otel/v1/traces \
  -H "Authorization: Bearer $BRAINTRUST_API_KEY" -H "x-bt-parent: project_id:$BRAINTRUST_PROJECT_ID" \
  -H 'Content-Type: application/json' --data-binary @runs/otlp.json
```

These commands were not run as part of building the course (no accounts or keys were used); treat them as a starting
point and check each product's docs for the current endpoint and headers.

## Choosing

All three can do the job. The course stays tool-agnostic on purpose. Whatever you pick, keep the attribute names
standard, keep your own JSONL export (it is your ground truth for replay and CI), and make sure you can still answer
"show me every trace where a tool failed and the answer cited it" with a query, not by scrolling.
