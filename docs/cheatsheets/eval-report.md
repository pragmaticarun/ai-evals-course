# Cheat sheet: writing the eval report

An eval only matters if it changes a decision. Module 12; code in `mediadoctor.capstone`, template in
[eval report](../eval-templates/eval-report.md), worked example in the [reference report](../capstone/index.md).

## Commands

```bash
uv run mediadoctor-capstone run                                   # every module's stage, one line each
uv run mediadoctor-capstone slices                                # baseline vs candidate per topic
uv run mediadoctor-capstone report --slice TOPIC --out FILE       # dev only; run as often as you like
uv run mediadoctor-capstone check FILE                            # template self-review
uv run mediadoctor-capstone report --slice TOPIC --release --out FILE   # once: the held-out look, logged
```

## The ten sections, and the test for each

| Section | Passes when |
|---|---|
| 1. Decision requested | someone could act on it without reading further |
| 2. Summary | three bullets; every number has an interval and a denominator; the third says what is not fixed |
| 3. Scope | system, models, prompt versions, dates, and out of scope are listed |
| 4. Data | every set's size and provenance (real or synthetic), and the coverage gaps |
| 5. Failure taxonomy | ranked modes with counts and severity; before and after |
| 6. Evaluators | every judge with its validation set, TPR, and TNR; corrected rates where judges carry a headline |
| 7. Results | paired diffs with fixed/broken counts; per-case ids; p50/p95 latency; cost per successful task |
| 8. Risks and caveats | sample size, judge error, provenance, definitions, untested modes, shift; specific to this report |
| 9. Recommendation | follows from a stated rule; next steps ordered and owned |
| 10. Appendix | commands, git sha or inputs fingerprint, every quoted id |

## Numbers to say carefully

| Instead of | Write |
|---|---|
| "+23 points" | "+0.231 [+0.157, +0.315], 25 fixed and 0 broken (n = 108)" |
| "DRM is solved (100%)" | "15/15 [0.796, 1.000]: a failure rate up to 20% is not ruled out" |
| "the judge says 82% pass" | "0.840 [0.236, 1.000] after correcting for the judge's TPR and TNR" |
| "confirmed on held-out" | "held out: +0.138 [+0.000, +0.310], 5 fixed and 1 broken; consistent, not a second test" |
| "significantly better" | the interval, and whether the rule written beforehand was met |

## Slices

- Choose by a rule written down first: weakest under the candidate, or highest risk.
- Report what the slice can detect (`mdd_paired(n, discordant)`); below that, list failures by id instead of rates.
- Check judges on the slice; a judge validated on other topics is trusted, not validated, here.
- A small slice's best output is a data request (more queries of the missing kinds), not a prompt change.

## Presenting

Ask, evidence, what changed, what is not fixed, how sure, next steps: six slides, ten minutes. Say intervals in
words ("at least 16 points better, probably about 23"). Show one real trace.
