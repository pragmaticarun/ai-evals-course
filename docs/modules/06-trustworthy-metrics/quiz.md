# Quiz

Ten questions. Answer each, then expand to check.

**1. Prompt A passes 49 of 60 queries and prompt B passes 47 of 60. What can you conclude?**

??? question "Answer"
    Almost nothing. The 95% Wilson intervals are about [0.70, 0.89] and [0.66, 0.87], a two-sample test gives
    p ≈ 0.65, and 60 queries can only detect changes of about 16 points from 80%. Report it as "no detectable
    difference at n = 60", and pair the comparison or add queries if a few points matter.

**2. Why use the Wilson interval rather than p ± 1.96·√(p(1−p)/n)?**

??? question "Answer"
    The simple (Wald) interval fails near 0 and 1 and at small n, which is where eval rates and judge TNRs live: at
    6/6 it gives [1.00, 1.00], and it can extend outside [0, 1]. Wilson stays inside [0, 1] and has close to the stated
    coverage even with small samples (6/6 gives [0.61, 1.00]).

**3. You ran each of 40 queries 5 times. A colleague bootstraps the 200 runs as independent samples. What is
wrong?**

??? question "Answer"
    The runs of one query are correlated: they share its difficulty. Resampling runs pretends there are 200
    independent queries and gives an interval that is too narrow. Resample the 40 queries and keep each query's runs
    together (a cluster bootstrap), or average per query first.

**4. The API no longer lets you set temperature at all. How do you deal with run-to-run variance?**

??? question "Answer"
    Measure it rather than trying to remove it: run each query several times, report the run-to-run spread and
    pass^k, and treat a query's outcome as a probability. Even temperature 0, back when you could set it, was never fully deterministic (serving
    and batching effects), and evals should use the settings you ship. More queries narrow comparisons; repeats
    measure consistency.

**5. Why compare two prompts on the same queries, and what does McNemar's test use?**

??? question "Answer"
    Query difficulty is the largest source of variation; running both prompts on the same queries cancels it, so a
    smaller set detects the same change. McNemar's test uses only the discordant queries (passed by one prompt and
    failed by the other) and asks whether they split more unevenly than a fair coin would.

**6. You need to detect a 5-point improvement from 80%. Roughly how many queries, unpaired and paired (15% of
queries discordant)?**

??? question "Answer"
    About 906 per variant unpaired (α = 0.05, power 0.8), and about 469 shared queries paired. The required n grows
    with 1/δ², so a 2.5-point change needs about four times as many.

**7. You compare prompts on 8 topic slices and one shows p = 0.03. Is the prompt better on that topic?**

??? question "Answer"
    Not on this evidence. With eight tests, the chance that at least one reaches p < 0.05 by luck is far above 5%.
    Adjust (Holm-Bonferroni: 0.03 × 8 = 0.24 for the smallest p) and treat the slice as a hypothesis for a larger,
    pre-planned eval.

**8. v2's overall pass rate is +5 points with a paired interval crossing zero. Should you drop v2?**

??? question "Answer"
    Look per failure mode first. In the lab, the aggregate hid a significant fix (accepted false premises 18% → 7%)
    and a significant regression (format violations 3% → 17%). The right move is to keep the fix and repair the
    regression, which a single score cannot tell you.

**9. What is the difference between pass@k and pass^k, and which matters for an agent people rely on?**

??? question "Answer"
    pass@k is the chance that at least one of k attempts passes (useful when someone picks the best attempt); pass^k
    is the chance that all k pass. For an agent users ask repeatedly, consistency matters: pass^k. In the lab v2 has
    the higher pass^1 but the lower pass^5.

**10. A vendor offers a "helpfulness" score from 1 to 10 and a semantic-similarity score. How do you decide whether
to use them?**

??? question "Answer"
    Test them against your labels: does the score separate passing from failing traces (for example, the chance a
    random passing trace outscores a random failing one)? In the lab both were at or below 0.5: helpfulness rewarded
    confident wrong answers, and word overlap rewarded an answer contradicting ffprobe. Use binary per-failure-mode
    evaluators as metrics; generic scores at most help you find traces to read.
