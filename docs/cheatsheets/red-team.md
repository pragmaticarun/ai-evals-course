# Cheat sheet: red-teaming and safety

Every tool output is untrusted input. Test your own agent, measure attacks and false positives together, and make
the dangerous outcomes impossible in code, not just unlikely in the prompt. Module 10; code in
`mediadoctor.guarded`, `mediadoctor.lab10`, `config/redteam/`, and `evals/test_redteam.py`.

## Red-team checklist

1. **Threat model.** Assets (prompt, secrets, files, user trust, public outputs); entry points and who controls
   each; sinks; current controls. Check for the lethal trifecta: private data + untrusted content + a way out.
2. **Entry points for injection.** User message (direct); tool outputs, retrieved documents, file names, metadata,
   logs, web pages (indirect). For media: container tags, subtitle cues, handler names, file names, logcat lines.
3. **Suite dimensions.** vector × goal × technique (plain, authority, roleplay, obfuscated, delimiter escape; add
   many-shot, payload splitting, translation, multi-turn when relevant). Exclude impossible combinations; cover all
   pairs (`pairwise_tuples`), then top up (`stratified_sample`).
4. **Carriers for real.** Build payloads into real files (`ffmpeg -metadata`, `mov_text` subtitles, log files, KB
   notes) and record what the pipeline delivers, not what you wrote.
5. **Success checks in code, from the trace.** What ran (tool spans with OK status, their arguments and results) and
   what the user saw. Never only the answer: the worst attacks leave a normal-looking answer.
6. **Benign traffic with hard negatives.** Requests that look like attacks (imperative text, base64, "token",
   "secret", shell commands) but are fine. Run every configuration on them.
7. **Report.** ASR and benign FPR with Wilson intervals, side by side; paired comparisons (McNemar, bootstrap) on
   the same cases; breakdowns by vector, goal, and technique; residual cases by id.
8. **Fix in layers, then re-measure.** See the table below.
9. **Gate.** Known attacks as `must_block` regression tests; residual risks listed in `accepted_risks`; canary
   never in any answer; ASR and FPR budgets; paired no-regression against the committed baseline.
10. **Scope.** Fake secrets (canaries), `.example` hosts, simulated or sandboxed action tools, and only systems you
    are responsible for.

## Guardrail layers

| Layer | Stops | Guarantee? | False-positive risk |
|---|---|---|---|
| No secrets in the prompt; a canary instead | leaks of anything valuable | yes | none |
| Input keyword filter | lazy direct attacks | no | high on hard negatives |
| Fencing (spotlighting) with an unguessable id | some indirect injection | no | none |
| Injection detector (judge on tool-output free text) | most indirect injection | no | imperative but benign text |
| Strict tool schemas (enums, presets, argv, no free strings) | argument injection | yes | users needing other options |
| Argument validation (paths, types, unknown args) | path traversal, odd calls | yes | rare |
| URL allowlist and egress check | exfiltration via fetch | yes for hosts; encodings get past text checks | legitimate unknown hosts |
| Human approval | publishing, irreversible actions | yes, if reviewers read | approval fatigue |
| Output filter (secrets incl. base64, prompt overlap, unknown links) | leaks and phishing in the answer | partly | correct links to new domains |

## Metrics

| Metric | Definition | Report with |
|---|---|---|
| Attack success rate | attacks whose goal was reached ÷ attacks | Wilson interval; by dimension |
| Benign false-positive rate | benign requests a guardrail interfered with ÷ benign requests | Wilson interval; list each one |
| Detector TPR / TNR | on the texts it screened, labelled injected or clean | counts; misses must be caught later |
| Approvals per benign request | approval cards ÷ benign requests | trend over time (fatigue) |
| Paired change | discordant cases (−/+), McNemar p, bootstrap CI | always on the same cases |

- Sizing: a 2/60 ASR has an upper bound of 0.11; bounding it under 0.05 at the same rate takes about 640 cases
  (`wilson_interval`). For paired FPR changes, use `n_paired` and `mdd_paired`.
- ASR describes your suite, not attackers. Never report it without the suite's description and the FPR.

## Commands

## Beyond the fixed suite

- Adaptive attacks: an attacker model loop (PAIR, TAP) against staging; ASR per attacker budget; every success
  becomes a `must_block` case.
- Third-party tool servers (MCP): descriptions are untrusted input; pin, review, diff on update; poisoned
  descriptions are their own vector.
- Report over-refusal (benign refused or blocked, by cause) next to ASR; a rise is a regression.

```bash
uv run mediadoctor-lab10 surface                # attack surface map
uv run mediadoctor-lab10 suite                  # dimensions and coverage
uv run mediadoctor-lab10 run --guard v2         # one line per case
uv run mediadoctor-lab10 report --out runs/m10/guardrail_report.md
uv run mediadoctor-lab10 trace wx01 --guard none
uv run mediadoctor-lab10 detector               # TPR and TNR of the injection detector
uv run mediadoctor-lab10 hitl --approver ask    # be the reviewer
uv run mediadoctor-lab10 gate [--guard v1] [--write-baseline]
uv run pytest evals/test_redteam.py -q
```
