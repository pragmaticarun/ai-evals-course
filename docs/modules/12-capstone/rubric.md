# Grading rubric and self-review checklist

Use the rubric to score a capstone report (yours, a peer's, or the [reference report](../../capstone/index.md)), and
the checklist to review your own before anyone else reads it. A report that passes is one a product owner could act
on and an engineer could reproduce.

## Rubric

Score each criterion from 1 to 4. Write one sentence of evidence for every score: a quote, a number, or a missing
section. A passing capstone has at least 3 on every criterion and at least 30 of 40 overall.

| # | Criterion | 4: exemplary | 3: sound | 2: weak | 1: missing |
|---|---|---|---|---|---|
| 1 | **Decision** | One paragraph names the action, the alternative, and any condition; the rest of the report supports exactly that | The decision is clear but needs the summary to make sense | The decision is implied ("results look promising") | No decision |
| 2 | **Summary numbers** | Three bullets; every number has an interval and a denominator; the third bullet says what the change does not fix | Three bullets with intervals; one number lacks context | Point estimates only, or more than five bullets | No summary |
| 3 | **Scope and data** | System, models, prompt versions, dates, and out-of-scope listed; every set's provenance (real or synthetic) and coverage gaps stated | Scope and data present; coverage gaps vague | Data described without provenance or size | Missing |
| 4 | **Failure taxonomy** | Ranked modes with counts, rates with intervals, and severity; before and after for the modes the change targets | Ranked modes with counts; before and after for some | A list of modes without counts | Missing |
| 5 | **Evaluators** | Every check and judge with what it detects, its validation set, and TPR and TNR; headline judge rates corrected for judge error | Judges with TPR and TNR; validation sets not named | Judges listed without validation | Missing |
| 6 | **Results** | Paired comparisons with fixed and broken counts; per-case diff with ids; latency (p50, p95 or p90) and cost per successful task; architecture, gate, monitoring, and red-team results each tied to the decision | Paired results and cost; one of the other parts thin | Unpaired rates, or accuracy without cost and latency | Missing |
| 7 | **Slice deep-dive** | Slice chosen by a stated rule; error analysis by id; judges checked on the slice; what the sample size can and cannot detect; a concrete next experiment or data request | Slice analysed with intervals; next step vague | Slice rates without intervals or failures | No slice |
| 8 | **Risks and caveats** | Sample size, judge error, data provenance, metric definitions, untested modes, and distribution shift, each specific to this report; the risks that would change the decision are marked | Most of these, some generic | One or two generic caveats | Missing |
| 9 | **Recommendation** | Follows from a stated rule; next steps concrete, ordered, and owned; conditions for revisiting the decision | Follows from the evidence; next steps listed | Recommendation not supported by the results | Missing |
| 10 | **Reproducibility** | Commands, inputs fingerprint or git sha, and every quoted id; the held-out look logged once; builds on the site with `--strict` | Commands and sha; some ids missing | Prose description of how it was run | Missing |

## Self-review checklist

Go through this before you ask anyone to read your report. Each item is a yes or no.

**Before you write**

- [ ] I wrote down my slice and what I expected from it before looking at its numbers.
- [ ] I wrote the pre-registration for my slice experiment before running it.
- [ ] I have not read the held-out split yet (or I have, once, and it is logged).

**The numbers**

- [ ] Every rate has its denominator and a 95% interval.
- [ ] Every comparison is paired on the same queries, with fixed and broken counts.
- [ ] Every judge-measured number has the judge's TPR and TNR next to it.
- [ ] Cost is per successful task; latency has p50 and a tail percentile.
- [ ] No claim about a slice is smaller than what the slice can detect.
- [ ] I checked the claim that looks strongest and the one that looks weakest (Exercise 2).

**The words**

- [ ] The decision is in the first paragraph.
- [ ] Nothing in the summary is softened in section 8, and nothing in section 8 contradicts the summary.
- [ ] Every example I quote has an id in the appendix.
- [ ] Words like "significant", "solved", "proves", and "always" appear only with the number that justifies them,
      or not at all.
- [ ] Someone outside the team could read the summary and the recommendation without a glossary.

**The mechanics**

- [ ] `uv run mediadoctor-capstone check runs/capstone/report.md` passes.
- [ ] The commands in the appendix reproduce the summary numbers on a fresh clone.
- [ ] The report builds on the site with `uv run zensical build --clean --strict`.
- [ ] The synthetic-data statement is at the top if any number comes from synthetic data.
