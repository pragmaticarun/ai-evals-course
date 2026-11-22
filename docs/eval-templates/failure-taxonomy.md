# Template: failure taxonomy sheet

Used from module 3 onward. It has two parts: the **annotation sheet** (one row per trace) and the **taxonomy
sheet** (one row per failure mode). `uv run mediadoctor-lab03 rank --taxonomy taxonomy.csv` produces the taxonomy
sheet from the annotation sheet and a modes file; you can also fill it in by hand.

## Part 1: annotation sheet (one row per trace)

| case_id | trace_id | verdict | note (open code) | first_upstream | modes (axial codes) | annotator | annotated_at |
|---|---|---|---|---|---|---|---|
| m3t033 | 4caafcf041c0… | fail | ffprobe called on 'late_moov.mp4', errored, answer still cites [tool:ffprobe] | execute_tool ffprobe | wrong-tool-args;fabricated-evidence | your name | 2026-11-23T10:15:00+05:30 |
| m3t006 | … | pass | | | | your name | … |

- `verdict` is `pass` or `fail`, never a score.
- `note` says what you observed, in your own words: the first thing that went wrong, not the fix.
- `first_upstream` is the step where it first went wrong: `chat:plan`, `execute_tool <tool>`, `retrieval`, or
  `chat:answer`.
- `modes` is empty until axial coding; separate several with `;`.

```text
case_id,trace_id,verdict,note,first_upstream,modes,annotator,annotated_at
```

## Part 2: taxonomy sheet (one row per failure mode)

| rank | id | failure mode | definition (one sentence a new labeler can apply) | example trace ids | count | % of traces | severity (1 to 3) | fixability | priority | first upstream step | detector (code / judge / none) | owner |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | | | | | | | | | | | | |
| 2 | | | | | | | | | | | | |

```text
rank,id,failure_mode,definition,example_trace_ids,count,pct,severity,fixability,priority,first_upstream_step,detector,owner
```

The modes themselves live in a TOML file (see `data/labels/module03_modes.toml` for a filled example):

```toml
[[mode]]
id = "fabricated-evidence"
name = "Cites evidence it never obtained"
definition = "The answer cites a tool or document whose call failed or never happened."
severity = 3          # 1 annoying, 2 misleading or costly, 3 harmful or trust-breaking
fixability = "easy"   # easy, medium, hard
detector = "code"     # code, judge, none
owner = "agent runtime"
```

## Guidelines

- Define modes so that two people would label the same trace the same way. Split modes when the fixes differ;
  merge them when you cannot write a sentence that separates them.
- In `example trace ids`, use ids you can open (`evalkit view FILE <id>`, `mediadoctor-lab03 review <id>`, or your
  backend's trace URL), not paraphrases.
- In `first upstream step`, name the step: for example `execute_tool ffprobe` (wrong argument) or `chat:answer`
  (contradicted a tool result). Trace checks from module 2 can count some modes for you; note that in `detector`.
- One trace can have several modes; count each mode once per trace.
- Rank by `priority` = count × severity, and write down any other rule you use (for example dividing by effort).
  Use `fixability` to find quick wins among the top rows.
- Record how many traces you read and where the last new mode appeared (saturation), so readers know how complete
  the sheet is.
- Revisit after every major change: modes appear, merge, and disappear.
