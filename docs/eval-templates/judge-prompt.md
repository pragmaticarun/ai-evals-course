# Template: binary LLM judge prompt

Used from module 5 onward with the `judge` model from `config/models.toml`. One judge per failure mode. In the
course code a judge is a TOML spec in `config/judges/`, rendered by `evalkit.judge.build_judge_request`; the
filled-in example below is `config/judges/tool-grounding.v2.toml`.

## Part 1: the spec

| Field | Fill in | Checks |
|---|---|---|
| name, version | `<failure-mode-judge>`, `v1` | bump the version for any change to the text, examples, context, or model |
| mode | the failure-mode name from your taxonomy | a FAIL verdict means this mode is present |
| criterion | one sentence: what PASS looks like | one failure mode only |
| pass | precise definition, including decided borderline cases | someone else could apply it |
| fail | precise definition, including decided borderline cases | names the evidence that decides |
| context | which of question / tools / answer the judge sees | only what the criterion needs |
| examples | 2 to 4 trace ids with verdict and critique | **train split only**; at least one FAIL and one tricky PASS |
| model | the `judge` role, pinned | revalidate when it changes |

## Part 2: the prompt text

```text
You evaluate one aspect of answers from <PRODUCT>, <one line on who uses it>. You check exactly one
criterion; ignore every other quality of the answer.

Criterion: <ONE failure mode, stated as what a PASS looks like>

PASS: <precise definition, with the borderline cases you decided are PASS>

FAIL: <precise definition, with the borderline cases you decided are FAIL>

Examples:

Example 1:
<question>...</question>
<tool_calls>...</tool_calls>          (only if the criterion needs them)
<answer>...</answer>
Output: {"critique": "<quotes the words the verdict rests on>", "verdict": "FAIL"}

Example 2: ... (a tricky PASS)

Read the material, write a short critique that quotes the specific words your verdict rests on,
then give the verdict. Respond with JSON only:
{"critique": "<two or three sentences>", "verdict": "PASS" or "FAIL"}
```

The user message holds the trace to judge, in the same tags as the examples.

## Part 3: filled-in example (MediaDoctor, tool-grounding v2)

| Field | Value |
|---|---|
| mode | `ignored-tool-output` |
| criterion | The answer's claims about files, devices, and logs agree with what the tool calls returned. |
| pass | Every statement about a file, device, decoder, or log is supported by, or not contradicted by, the tool results. Answers with no such claim, or that ask for more information, pass. Judge only agreement with the tool results. |
| fail | A statement a tool result contradicts: a different number, a capability the tool says is absent, a cause the log rules out. **This applies even when the user asserted the same claim** (added in v2 after dev disagreements). |
| context | question, tools, answer |
| examples | `m4q007` FAIL (16 decoders vs codec_caps 4), `m4q119` PASS, `m4q084` FAIL (user's wrong claim repeated), `m4q012` FAIL (start times) — all train |
| validation | dev: TPR 0.89 (24/27), TNR 1.00 (6/6). Test, once: TPR 0.90 (18/20), TNR 0.60 (3/5) |

## Part 4: validation record

| Version | Split | n (pass / fail) | TPR | TNR | Unparsed | What changed / decision |
|---|---|---|---|---|---|---|
| v1 | dev | | | | | |
| v2 | dev | | | | | |
| v2 | test (once) | | | | | |

## Checklist before you trust it

- [ ] Labels from a domain expert on at least 100 cases (ideally 50+ passes and 50+ failures for this mode), split
      into train (examples), dev (iterate), and test (report once)
- [ ] Few-shot examples from train only; no expected answers, labels, or reviewer notes in the prompt
      (`mediadoctor-lab05 leaks` or `evalkit.judge.leakage_problems`)
- [ ] TPR and TNR, with counts, on dev for every version and on test once
- [ ] Disagreements reviewed with the domain expert; decisions logged; criteria revisited (they drift)
- [ ] Pass rates reported corrected for judge error, with a bootstrap interval
- [ ] Prompt, examples, and model ID versioned; fixtures recorded
