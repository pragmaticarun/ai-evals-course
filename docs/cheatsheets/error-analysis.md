# Cheat sheet: error analysis

## The loop

```text
sample ~100 traces (random order, all question types)
   │
   ▼
OPEN CODING   pass/fail + one-line note on the first thing that went wrong + the step
   │
   ▼
AXIAL CODING  group notes → named modes with one-sentence definitions, severity, fixability
   │
   ▼
RE-LABEL      tag every failing trace with its modes; fix definitions that drifted
   │
   ▼
COUNT & RANK  traces per mode × severity; fixability for quick wins; Pareto chart
   │
   ▼
saturated? (≥100 read and ~20 in a row with nothing new) ── no ──► read more
```

## Reading one trace

1. Question, then answer: would the expert accept it? Pass or fail.
2. On fail, walk the steps from the top; stop at the first wrong output.
3. Write what you saw, not the fix. Name evidence: tool, argument, returned value, document id.

| First upstream step | Typical failures |
|---|---|
| `chat:plan` | skipped the tools, redundant calls, wrong tool chosen |
| `execute_tool <name>` | wrong argument (error), wrong but valid argument (silent) |
| `retrieval` | wrong documents: query problem or retriever/KB problem |
| `chat:answer` | contradicts tool output, wrong API detail, vague next step, broken format |

## Good notes vs weak notes

The first two rows are illustrations of the note style, not cases from the course data; the third is the module 3
reference note on `m3t010`.

| Weak | Better |
|---|---|
| hallucination | says lumen-l3 supports Main 10; codec_caps profiles = [Main] |
| bad retrieval | 'sound continues when phone rings' → av-sync, needed audio-focus |
| made it up | says lumen-l3 AV1 is software-only, 1080p30; no tool queried lumen-l3 |

## Special cases

- **Tool error + successful retry** → pass (maybe note the cost).
- **Tool error + answer cites the tool** → wrong-tool-args *and* fabricated-evidence; first upstream = the tool call.
- **Retrieval miss** → would a better query find the doc? Yes: query formulation. No: retriever or KB.
- **Right answer, wasteful path** → still a failure if cost or latency matters; record the multiple.

## Prioritising

| Signal | Use |
|---|---|
| traces × severity | what hurts most |
| ÷ effort, or fixability | what to do this week |
| flat Pareto | severity and fixability decide |
| one tall bar | fix that first |

## Commands (module 3 lab)

```bash
uv run mediadoctor-lab03 run --out runs/m3_traces.jsonl
uv run mediadoctor-lab03 annotate --traces runs/m3_traces.jsonl --labels runs/m3_labels.csv
uv run mediadoctor-lab03 notes --labels runs/m3_labels.csv
uv run mediadoctor-lab03 code --labels runs/m3_labels.csv --modes runs/m3_modes.toml
uv run mediadoctor-lab03 rank --labels runs/m3_labels.csv --modes runs/m3_modes.toml --taxonomy runs/taxonomy.csv --svg runs/pareto.svg
uv run mediadoctor-lab03 saturation --labels runs/m3_labels.csv
uv run mediadoctor-lab03 errors | retrieval | signals
uv run mediadoctor-lab03 compare --labels runs/m3_labels.csv
```

## Red flags

- Categories chosen before anyone read a trace.
- Labels from someone who cannot tell a right answer from a plausible one.
- Stopping after a short run of "nothing new".
- Only reading the traces that automatic checks flagged.
- A taxonomy with no definitions, or definitions nobody else can apply.
