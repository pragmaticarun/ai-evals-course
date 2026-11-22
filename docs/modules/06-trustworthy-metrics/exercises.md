# Exercises

Try each exercise before opening its solution. Code solutions are tested in CI and run from the repo root.

## Exercise 1: How many queries to detect a 5-point change?

MediaDoctor's production pass rate is about 0.80, and a prompt change is expected to lift it by 5 points. Using
`evalkit.stats`:

1. How many queries give a ±5-point interval on one pass rate?
2. How many queries per variant to detect 0.80 → 0.85 (α = 0.05, power 0.8) if each variant runs on its own queries?
3. How many if both run on the same queries and 10%, 15%, or 25% of queries are discordant?
4. How many per variant for 0.95 → 0.99?
5. With 137 queries (and with 500), what is the smallest lift from 0.80 you can detect?

??? success "Solution"
    ```python
    # exercise-solution: how many queries to detect a 5-point change
    from evalkit.stats import (
        mdd_paired,
        mdd_two_proportions,
        n_for_halfwidth,
        n_paired,
        n_two_proportions,
    )

    print(f"(a) +/-5 points around 0.80: {n_for_halfwidth(0.80, 0.05)} queries")
    print(f"(b) 0.80 -> 0.85, separate queries: {n_two_proportions(0.80, 0.85)} per variant")
    for disc in (0.10, 0.15, 0.25):
        print(f"(c) 0.80 -> 0.85, same queries, {disc:.0%} discordant: {n_paired(disc, 0.05)} queries")
    print(f"(d) 0.95 -> 0.99, separate queries: {n_two_proportions(0.95, 0.99)} per variant")
    for n in (137, 500):
        print(
            f"(e) n={n}: smallest detectable lift from 0.80 is {mdd_two_proportions(n, 0.80):.3f} "
            f"unpaired, {mdd_paired(n, 0.15):.3f} paired (15% discordant)"
        )
    ```

    Output:

    ```text
    (a) +/-5 points around 0.80: 246 queries
    (b) 0.80 -> 0.85, separate queries: 906 per variant
    (c) 0.80 -> 0.85, same queries, 10% discordant: 312 queries
    (c) 0.80 -> 0.85, same queries, 15% discordant: 469 queries
    (c) 0.80 -> 0.85, same queries, 25% discordant: 783 queries
    (d) 0.95 -> 0.99, separate queries: 285 per variant
    (e) n=137: smallest detectable lift from 0.80 is 0.117 unpaired, 0.092 paired (15% discordant)
    (e) n=500: smallest detectable lift from 0.80 is 0.066 unpaired, 0.048 paired (15% discordant)
    ```

    A precise single rate (±5 points) needs about 250 queries; *detecting a 5-point change* between two variants
    needs about 900 per variant, because the difference carries the noise of both rates and you also want 80% power,
    not a coin flip. Pairing cuts that to 300 to 800 queries depending on how often the variants disagree: the fewer
    discordant queries, the cheaper the comparison. Near the ceiling (95% → 99%) the same 4-point change is cheaper
    because there is less binomial noise. With MediaDoctor's 137 labelled queries the honest statement is "we can see
    changes of about 9 points (paired) to 12 points (unpaired) or more"; a 5-point claim needs roughly 500 shared queries.

## Exercise 2: How a judge with TNR 0.8 moves the pass rate

A judge has TPR 0.95 and TNR 0.80. (1) What does it report when the true pass rate is 0.5, 0.7, or 0.9? At what
true rate is it exactly right? (2) Prompt v2 truly improves the pass rate from 0.70 to 0.80. What improvement does
the judge report? (3) Simulate 2,000 judged queries per variant and check that `corrected_pass_rate` recovers the
true rates.

??? success "Solution"
    ```python
    # exercise-solution: a judge with TNR 0.8 inflates the pass rate and shrinks differences
    import random

    from evalkit.stats import corrected_pass_rate, observed_pass_rate

    TPR, TNR = 0.95, 0.80
    for true in (0.5, 0.7, 0.9):
        obs = observed_pass_rate(true, TPR, TNR)
        print(f"true {true:.2f} -> judge reports {obs:.3f} (error {obs - true:+.3f})")

    print(f"no error only at true = (1 - TNR) / (2 - TPR - TNR) = {(1 - TNR) / (2 - TPR - TNR):.2f}")

    v1, v2 = 0.70, 0.80
    o1, o2 = observed_pass_rate(v1, TPR, TNR), observed_pass_rate(v2, TPR, TNR)
    print(f"true lift {v2 - v1:+.3f} -> observed lift {o2 - o1:+.3f} (x{TPR + TNR - 1:.2f})")

    # Simulate 2,000 judged queries per variant and correct the observed rates.
    rng = random.Random(0)


    def judged_rate(true: float, n: int = 2000) -> float:
        verdicts = []
        for _ in range(n):
            good = rng.random() < true
            verdicts.append(rng.random() < TPR if good else rng.random() > TNR)
        return sum(verdicts) / n


    for name, true in (("v1", v1), ("v2", v2)):
        obs = judged_rate(true)
        print(f"{name}: observed {obs:.3f}, corrected {corrected_pass_rate(obs, TPR, TNR):.3f}")
    ```

    Output:

    ```text
    true 0.50 -> judge reports 0.575 (error +0.075)
    true 0.70 -> judge reports 0.725 (error +0.025)
    true 0.90 -> judge reports 0.875 (error -0.025)
    no error only at true = (1 - TNR) / (2 - TPR - TNR) = 0.80
    true lift +0.100 -> observed lift +0.075 (x0.75)
    v1: observed 0.724, corrected 0.699
    v2: observed 0.798, corrected 0.798
    ```

    The judge passes 20% of bad answers, which pushes the reported rate up, and fails 5% of good ones, which pushes
    it down. Which wins depends on the mix: below a true rate of 0.80 the false passes dominate and the judge
    inflates; above it, it deflates. So a judge's bias is not a constant you can subtract.

    Differences shrink by the factor TPR + TNR − 1 (here 0.75): a real 10-point improvement shows up as 7.5 points.
    A weak judge therefore makes real improvements look smaller *and* noisier, which feeds straight into the sample
    sizes of exercise 1. The correction restores the scale; its interval (module 5) restores the honesty.

## Exercise 3: Slicing an A/A test

`mediadoctor-lab06 slices` shows two topics where v2 looks much better or much worse. Estimate how often that
happens by chance: simulate 1,000 experiments comparing a prompt with *itself* on 8 slices of 17 queries (each
query with its own difficulty), test each slice with exact McNemar, and count the experiments with at least one
slice at p < 0.05, before and after Holm. Then run the same A/A test without slicing.

??? success "Solution"
    ```python
    # exercise-solution: slicing an A/A test
    import random

    from evalkit.stats import holm, mcnemar_exact

    rng = random.Random(1)
    SLICES, PER_SLICE, EXPERIMENTS = 8, 17, 1000  # about 137 queries in 8 topic slices
    raw_hits = holm_hits = 0
    for _ in range(EXPERIMENTS):
        p_values = {}
        for s in range(SLICES):
            a_only = b_only = 0
            for _ in range(PER_SLICE):
                p = rng.uniform(0.1, 0.9)  # each query has its own difficulty
                a, b = rng.random() < p, rng.random() < p  # A and B are the same prompt
                a_only += a and not b
                b_only += b and not a
            p_values[s] = mcnemar_exact(a_only, b_only)
        raw_hits += min(p_values.values()) < 0.05
        holm_hits += min(holm(p_values).values()) < 0.05
    print(
        f"A/A experiments with a 'significant' slice: raw {raw_hits / EXPERIMENTS:.1%}, Holm {holm_hits / EXPERIMENTS:.1%}"
    )

    overall = {}
    for _ in range(EXPERIMENTS):
        a_only = b_only = 0
        for _ in range(SLICES * PER_SLICE):
            p = rng.uniform(0.1, 0.9)
            a, b = rng.random() < p, rng.random() < p
            a_only += a and not b
            b_only += b and not a
        overall[len(overall)] = mcnemar_exact(a_only, b_only) < 0.05
    print(f"A/A experiments 'significant' overall: {sum(overall.values()) / EXPERIMENTS:.1%}")
    ```

    Output:

    ```text
    A/A experiments with a 'significant' slice: raw 12.9%, Holm 0.8%
    A/A experiments 'significant' overall: 2.0%
    ```

    With eight slices, about one A/A experiment in eight finds a "significant" slice, although nothing changed. Holm
    brings that below 5% (the exact McNemar test is conservative with few discordant pairs, which is why both the
    adjusted and the overall rates come out under 5%). In practice: decide slices before looking, adjust for the
    number you test, and treat a surprising slice as a question for a larger eval. Also note how small the slices
    are: a slice of 13 queries can only detect enormous effects (exercise 1).

## Exercise 4: Run-to-run variance and pass^k

Using the five runs of each prompt on the 37 dev queries: (1) report each prompt's run-to-run range, flaky
queries, and pass^1, pass^3, pass^5; (2) compare the prompts on each query's mean over five runs, with a bootstrap
interval that resamples *queries*. Which prompt would you ship to support engineers who retry a question when the
answer looks off?

??? success "Solution"
    ```python
    # exercise-solution: run-to-run variance and pass^k
    from evalkit.stats import bootstrap_ci, pass_hat_k, trial_summary
    from mediadoctor import lab06

    for prompt in lab06.PROMPTS:
        rep = lab06.repeated(prompt)
        s = trial_summary(rep)
        hats = [sum(pass_hat_k(5, sum(v), k) for v in rep.values()) / len(rep) for k in (1, 3, 5)]
        print(
            f"{prompt}: runs {min(s.run_rates):.3f} to {max(s.run_rates):.3f}, flaky {s.flaky}/37, "
            f"pass^1 {hats[0]:.3f}  pass^3 {hats[1]:.3f}  pass^5 {hats[2]:.3f}"
        )

    # Compare the prompts on per-query pass probability (mean of 5 runs), resampling queries.
    v1, v2 = lab06.repeated("v1"), lab06.repeated("v2")
    pairs = [(sum(v1[c]) / 5, sum(v2[c]) / 5) for c in sorted(v1)]


    def diff(ps):
        return sum(b - a for a, b in ps) / len(ps)


    point, lo, hi = bootstrap_ci(pairs, diff, draws=2000, seed=6)
    print(f"v2 - v1, 5-run means per query: {point:+.3f} [{lo:+.3f}, {hi:+.3f}]")
    ```

    Output:

    ```text
    v1: runs 0.405 to 0.459, flaky 15/37, pass^1 0.438  pass^3 0.324  pass^5 0.270
    v2: runs 0.378 to 0.486, flaky 19/37, pass^1 0.454  pass^3 0.289  pass^5 0.189
    v2 - v1, 5-run means per query: +0.016 [-0.135, +0.178]
    ```

    v2 has the better single-run pass rate (0.454 vs 0.438) but the worse consistency: pass^5 is 0.189 against 0.270,
    and 19 of 37 queries are flaky. Its premise check helps some queries every time and adds a format slip to others
    some of the time. Averaging five runs per query does not rescue the comparison: +0.02 with an interval of
    [−0.14, +0.18], because the interval is driven by the 37 queries, not the runs. Repeats measure consistency; only
    more queries narrow the comparison. (Resampling the 185 runs as if independent would give a falsely narrow
    interval.) For engineers who retry, a flaky answer is worse than a consistent one; neither prompt is ready, and
    v2's format slip is the first thing to fix.

## Exercise 5: Test two vanity metrics against the labels

The lab replays a generic 1-to-10 helpfulness judge and computes word-overlap F1 against reference answers. Find
which kinds of answers each one rewards and punishes.

??? success "Solution"
    ```python
    # exercise-solution: vanity metrics against the labels
    from statistics import mean

    from mediadoctor import lab06

    for prompt in lab06.PROMPTS:
        h = lab06.helpfulness(prompt)
        print(f"{prompt}: mean helpfulness {mean(h.values()):.2f}")

    h, labels = lab06.helpfulness("v1"), lab06.labels()[("v1", 1)]
    items = lab06.items("v1", 1)
    groups = {
        "asks for details (PASS)": [
            c for c in h if items[c].answer.startswith("Likely cause: Not enough")
        ],
        "accepted false premise": [c for c in h if "accepted-false-premise" in labels[c]],
        "ignored tool output": [c for c in h if "ignored-tool-output" in labels[c]],
        "no failure (incl. asks)": [c for c in h if not labels[c]],
    }
    for name, ids in groups.items():
        print(f"  {name:<25} n={len(ids):>2}  helpfulness {mean(h[c] for c in ids):.2f}")

    sim = lab06.similarity("v1")
    fails = [c for c in sim if labels[c]]
    passes = [c for c in sim if not labels[c]]
    for mode in ("ignored-tool-output", "accepted-false-premise"):
        c = max((c for c in fails if mode in labels[c]), key=sim.get)
        print(f"most similar {mode} answer {c}: F1 {sim[c]:.2f}")
    print(f"failing answers with F1 >= 0.9: {sum(sim[c] >= 0.9 for c in fails)} of {len(fails)}")
    print(f"passing answers with F1 < 0.5: {sum(sim[c] < 0.5 for c in passes)} of {len(passes)}")
    ```

    Output:

    ```text
    v1: mean helpfulness 7.71
    v2: mean helpfulness 7.66
      asks for details (PASS)   n=18  helpfulness 4.89
      accepted false premise    n=24  helpfulness 8.04
      ignored tool output       n=22  helpfulness 8.45
      no failure (incl. asks)   n=52  helpfulness 7.23
    most similar ignored-tool-output answer m4q012: F1 0.77
    most similar accepted-false-premise answer m4q021: F1 0.79
    failing answers with F1 >= 0.9: 27 of 85
    passing answers with F1 < 0.5: 18 of 52
    ```

    Helpfulness does not move between prompts while two failure modes moved by more than 10 points, and it ranks
    answers backwards: answers that correctly ask for the missing file or device score lowest (4.89), and answers
    that contradict the tool output score highest (8.45). A generic judge rewards confident, specific-sounding text.

    Word overlap fails the other way: an answer that says the opposite of ffprobe (m4q012, start times) shares most
    of its words with the reference and scores 0.77, while correct answers that ask or that reject a premise use
    different words. 27 of 85 failing answers score at least 0.9; 18 of 52 passing ones score below 0.5. Neither
    metric belongs on the dashboard; at most, sort by them to find traces to read.
