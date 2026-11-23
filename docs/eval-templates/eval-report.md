# Template: eval report

Used in the [module 12 capstone](../modules/12-capstone/index.md). Aim for two pages that a product owner can act on.
`uv run mediadoctor-capstone report` drafts one from MediaDoctor's artifacts, and the
[reference report](../capstone/index.md) is a fully worked example.

1. **Decision requested**: one sentence. (Ship v3? Switch the judge model? Fund retrieval work?)
2. **Summary**: three bullets with the key numbers *and* their confidence intervals.
3. **Scope**: system version, model IDs, prompt versions, dates, what was out of scope.
4. **Data**: case set name and version, size, how it was built (real, synthetic, or both), coverage gaps.
5. **Failure taxonomy**: top modes with counts and severity, before and after.
6. **Evaluators**: each check and judge, with what it detects and its validation (TPR and TNR for judges).
7. **Results**: table per failure mode (baseline vs candidate, with CIs), the per-case diff, latency and cost per successful task.
   Report cost and latency from traces (median and p90 per trace, plus the most expensive traces by id), and the
   trace-check pass rates (for example evidence is real, step budget) next to the answer-quality numbers.
8. **Risks and caveats**: sample size, judge error, distribution shift, anything you did not test.
9. **Recommendation and next steps**.
10. **Appendix**: commands to reproduce (`git sha`, `uv run ...`), the trace file (JSONL) or backend project, and
    trace ids for every example quoted in the report.
