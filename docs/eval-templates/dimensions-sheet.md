# Template: dimensions sheet

Used from module 4 onward. Fill it in before generating anything; it becomes the dimensions file
(`config/synth/<product>.toml`) and the first lines of your dataset manifest.

## Part 1: failure hypotheses

Write what you expect to go wrong, before choosing dimensions. Each dimension should serve at least one hypothesis.

| # | Hypothesis | Evidence so far | Dimension(s) that test it |
|---|---|---|---|
| H1 | The agent answers from memory when the question names a file or device | module 3: fabricated-evidence (3 of 100 traces state details no tool returned) | `evidence` |
| H2 | The agent repeats wrong beliefs stated by the user | none yet (guess) | `ambiguity` |
| H3 | Vague, misspelt questions retrieve the wrong note | none in module 3's 100 traces (guess) | `expertise` |

## Part 2: dimensions

| Dimension | Values (3 to 6) | What changes in the query | Hypotheses | Source of values |
|---|---|---|---|---|
| persona | app-developer, media-engineer, qa-tester, support-agent | framing, vocabulary, ticket templates | H1 | support queue categories |
| topic | ... | which tools and notes are needed | H1, H3 | knowledge-base sections |
| evidence | none, media-file, device, file+device, log | what can be inspected | H1 | test data inventory |
| expertise | expert, intermediate, novice | precision, typos | H3 | |
| ambiguity | clear, missing-detail, false-premise | what is left out or wrong | H2 | |

Checks: each dimension is one kind of variation; every value can be written as a query; no dimension exists
"for completeness".

## Part 3: exclusion rules

| When | Forbid | Reason | Kind |
|---|---|---|---|
| topic = audio-focus | evidence ≠ none | no clip, device table, or log for it | our data |
| goal = check | evidence in none, media-file, log | a compatibility check needs a device | world |

*Kind* is `world` (impossible for any user) or `our data` (possible, but we cannot support it yet). Revisit every
`our data` rule when real traffic arrives.

## Part 4: generation settings

| Setting | Value |
|---|---|
| tuple strategy | pairwise, then stratified by ______ to n = ______ |
| seed | |
| writer model and prompt version | e.g. claude-haiku-5-5, prompt v1 |
| style examples | file, how they are chosen |
| dedup threshold and scope | e.g. 0.6, within the same evidence and ambiguity |
| split fractions and grouping threshold | e.g. 60/20/20, group at 0.35 |

## Part 5: review log

| Date | Sample read | Problems found | Action |
|---|---|---|---|
| | 30 queries | e.g. 1 query drops its file name | regenerate / relabel / rule change |

## Part 6: when real queries arrive

| Question | Answer |
|---|---|
| Real queries collected (count, period, source) | |
| Pair coverage of real queries alone | ___ / ___ |
| Values never used by real queries | |
| Variation seen in real queries that no dimension captures | |
| Next version: real / generated / stratified counts | |
