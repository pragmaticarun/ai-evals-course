# Template: failure taxonomy sheet

Used from module 3 onward. Keep it as a CSV in your repo (`data/labels/taxonomy.csv`) and render it here.

| id | failure mode | definition (one sentence a new labeler can apply) | example trace ids | count | % of traces | severity (1 to 3) | first upstream step | detector (code / judge / none) | owner |
|---|---|---|---|---|---|---|---|---|---|
| F1 | | | | | | | | | |
| F2 | | | | | | | | | |

**Guidelines**

- Define modes so that two people would label the same trace the same way.
- In `example trace ids`, use ids you can open (`evalkit view FILE <id>` or your backend's trace URL), not paraphrases.
- In `first upstream step`, name the span: for example `execute_tool ffprobe` (wrong argument) or `chat` step 2
  (ignored a tool error). Trace checks from module 2 can count some modes for you; note that in `detector`.
- One trace can have several modes; count each.
- Rank by count multiplied by severity; fix the top of the list first.
- Revisit after every major change: modes appear, merge, and disappear.

CSV header:

```text
id,failure_mode,definition,example_trace_ids,count,pct,severity,first_upstream_step,detector,owner
```
