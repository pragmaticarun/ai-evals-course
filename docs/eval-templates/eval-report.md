# Template: eval report

Used in the module 12 capstone. Aim for two pages that a product owner can act on.

1. **Decision requested**: one sentence. (Ship v3? Switch the judge model? Fund retrieval work?)
2. **Summary**: three bullets with the key numbers *and* their confidence intervals.
3. **Scope**: system version, model IDs, prompt versions, dates, what was out of scope.
4. **Data**: case set name and version, size, how it was built (real, synthetic, or both), coverage gaps.
5. **Failure taxonomy**: top modes with counts and severity, before and after.
6. **Evaluators**: each check and judge, with what it detects and its validation (TPR and TNR for judges).
7. **Results**: table per failure mode (baseline vs candidate, with CIs), the per-case diff, latency and cost per successful task.
8. **Risks and caveats**: sample size, judge error, distribution shift, anything you did not test.
9. **Recommendation and next steps**.
10. **Appendix**: commands to reproduce (`git sha`, `uv run ...`), and links to traces.
