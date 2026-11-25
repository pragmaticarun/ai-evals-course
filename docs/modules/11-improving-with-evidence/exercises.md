# Exercises

Try each exercise before opening its solution. Code solutions are tested in CI and run from the repo root, in replay
mode, with no API key.

## Exercise 1: The cheapest configuration within 2 points of the best

Using `lab11.summary` for every configuration, find the cheapest configuration (by cost per successful task) whose
success is within 2 points of the best. Do it twice: with point estimates, and then asking which configurations can
be *shown* to be within 2 points, using the paired 95% CI for (configuration minus best). What do you tell a manager
who asks "what's the cheapest option that's basically as good?"

??? success "Solution"
    ```python
    # exercise-solution: the cheapest configuration within 2 points of the best
    from mediadoctor import experiments as X
    from mediadoctor import lab11

    pts = [lab11.summary(n) for n in X.variants()]
    best = max(pts, key=lambda p: p.rate)

    # 1. Point estimates: within 2 points of the best rate, cheapest per successful task.
    pick = lab11.cheapest_within(pts, 0.02)
    print(f"best {best.variant} {best.rate:.3f}; point-estimate pick: {pick.variant}")

    # 2. With uncertainty: which variants can we NOT show to be more than 2 points worse than the best?
    #    (paired 95% CI for variant - best has its lower bound above -0.02)
    for p in sorted(pts, key=lambda p: p.cost_per_success):
        if p.variant == best.variant:
            print(
                f"  {p.variant:9s} (the best)                      cost/success ${p.cost_per_success:.5f}"
            )
            continue
        d = lab11.paired(best.variant, p.variant)
        ok = d.low > -0.02
        print(
            f"  {p.variant:9s} diff {d.diff:+.3f} [{d.low:+.3f}, {d.high:+.3f}]  "
            f"{'within' if ok else 'not shown within'} 2 pts  cost/success ${p.cost_per_success:.5f}"
        )
    ```

    Output:

    ```text
    best v2 0.277; point-estimate pick: v2
      haiku     diff -0.059 [-0.118, +0.000]  not shown within 2 pts  cost/success $0.00103
      cascade   diff -0.025 [-0.084, +0.034]  not shown within 2 pts  cost/success $0.00504
      v3-cache  diff -0.084 [-0.143, -0.025]  not shown within 2 pts  cost/success $0.02332
      retry     diff -0.076 [-0.134, -0.017]  not shown within 2 pts  cost/success $0.02422
      v2        (the best)                      cost/success $0.02495
      v1        diff -0.042 [-0.092, +0.000]  not shown within 2 pts  cost/success $0.02883
      v3        diff -0.034 [-0.092, +0.025]  not shown within 2 pts  cost/success $0.03454
    ```

    On point estimates the answer is v2 itself: the next best, the cascade (0.252), is 2.5 points below 0.277. With
    intervals, no configuration can be shown to be within 2 points of the best: even the cascade's paired CI goes
    down to −8.4 points. A 2-point tolerance is below what 119 queries can resolve (about 8 points when 10% of
    queries change outcome).

    Before you answer the manager, look at what "success" is measuring here. By the lab's grader every
    configuration succeeds on only 19% to 28% of tasks, but the reference labels find a failure mode in just 15 of
    the 833 dev answers (the lesson's Step 3). Most of the grader's failures are its own: its reference check looks
    for a fixed phrase per scenario, and the regenerated answers state the same diagnosis in other words. A ranking
    of the configurations by a grader that disagrees with the labels on most answers is a ranking of how each one
    happens to phrase things.

    For the manager: "on our labels the configurations are close to equally good, and our automated score cannot
    tell them apart; the cascade is about 80% cheaper per success than any Sonnet-only option, and Haiku cheaper
    again. We cannot call any of them within 2 points of another with this data and this grader. Before we trade
    points for money, we have to fix the grader." That is a less satisfying answer than a name, and the right one.

## Exercise 2: Explain a latency regression from the traces

Switching from v3-cache to retry raised p95 latency by 1.4 s and p50 by 0.6 s. Using the traces
(`lab11.task_results`, `lab11.spans_by_op`), explain where the extra time comes from, which tasks sit in the slow tail, and
what you would change to keep the self-check at a lower p95.

??? success "Solution"
    ```python
    # exercise-solution: explain a latency regression from the traces
    from collections import Counter

    from evalkit.stats import percentile
    from mediadoctor import lab11

    base, new = "v3-cache", "retry"
    rows_b = {r.case_id: r for r in lab11.run_rows(base)}
    rows_n = {r.case_id: r for r in lab11.run_rows(new)}
    print(
        f"p50 {percentile([r.latency_ms for r in rows_b.values()], 0.5) / 1000:.2f} -> "
        f"{percentile([r.latency_ms for r in rows_n.values()], 0.5) / 1000:.2f} s;  "
        f"p95 {percentile([r.latency_ms for r in rows_b.values()], 0.95) / 1000:.2f} -> "
        f"{percentile([r.latency_ms for r in rows_n.values()], 0.95) / 1000:.2f} s"
    )

    # Where does the extra time go? Sum span time by kind over every task.
    parts: Counter[str] = Counter()
    for t in lab11.task_results(new):
        for a in t.attempts:
            parts.update(lab11.spans_by_op(a.spans))
    n = len(rows_n)
    print("mean ms per task:", {k: round(v / n) for k, v in sorted(parts.items())})

    # Split the tasks: retried or not, and how much each group slowed down.
    for retried in (False, True):
        ids = [c for c, r in rows_n.items() if r.retried == retried]
        extra = [rows_n[c].latency_ms - rows_b[c].latency_ms for c in ids]
        print(
            f"{'retried' if retried else 'not retried':12s} n={len(ids):3d}  mean extra "
            f"{sum(extra) / len(extra) / 1000:+.2f} s  max {max(extra) / 1000:+.2f} s"
        )

    # Is the slowest 5% now made of retried tasks?
    slow = sorted(rows_n.values(), key=lambda r: -r.latency_ms)[: max(1, round(0.05 * n))]
    print(
        "slowest 5%:",
        ", ".join(
            f"{r.case_id} {r.latency_ms / 1000:.1f}s{' (retried)' if r.retried else ''}" for r in slow
        ),
    )
    ```

    Output:

    ```text
    p50 7.39 -> 7.97 s;  p95 13.40 -> 14.82 s
    mean ms per task: {'agent calls': 8309, 'self-check': 490, 'tools': 20}
    not retried  n=113  mean extra +0.48 s  max +1.86 s
    retried      n=  6  mean extra +7.16 s  max +10.79 s
    slowest 5%: m4q009 30.1s, m4q149 22.5s, m4q152 19.9s, m4q122 17.3s, m4q188 17.0s (retried), m4q135 14.9s (retried)
    ```

    Two mechanisms, visible in the spans. Every task now makes one more call (the Haiku self-check, about 0.5 s), a
    small, uniform shift that moves p50 by about the same amount. The 6 retried tasks also make a second agent turn
    (7.2 s more on average, up to 10.8 s). They are 5% of tasks, so they barely touch the median, but two of them
    (m4q188 and m4q135) climb into the slowest 5%, and that is what moves p95. The four slowest tasks were not
    retried at all: they were already slow under v3-cache (the retry configuration shares v3-cache's first answer),
    so most of the tail belongs to the agent, not the self-check. A regression that hits a minority of tasks hard
    moves p95 and leaves p50 alone; that is why you always report both, and why you read the slow tasks one by one.

    Ways to keep the self-check at a lower p95: run it in parallel with streaming the first answer to the user and
    only retry when it fails (the user waits only on failures); give the retry a smaller step budget; or retry only
    for the failure modes the judge catches reliably and the agent can actually fix. Here the judge caught none of
    the 3 answers the labels call defective and sent back 6 the labels call fine (the lesson's Step 4), so on this
    data the retry is all cost. Each fix is a new configuration with one change; test it the same way, with p95 as a
    guardrail.

## Exercise 3: Few-shot examples that do not leak the eval set

The first draft of v3's first few-shot example read: "In av_offset_300ms.mp4 the audio is ahead of the picture by
about a third of a second. Why?" Write a check that compares each few-shot example with every question in the
dataset and flags near-copies. Run it on the draft and on the examples v3 ships. Why does a near-copy matter even
when it is not identical, and why is it a problem even if it only matches a training-split question?

??? success "Solution"
    ```python
    # exercise-solution: few-shot examples that do not leak the eval set
    import re

    from mediadoctor import experiments as X
    from mediadoctor import lab04


    def words(text: str) -> set[str]:
        return set(re.findall(r"[a-z0-9_.]+", text.lower()))


    def jaccard(a: str, b: str) -> float:
        wa, wb = words(a), words(b)
        return len(wa & wb) / len(wa | wb)


    DRAFT = (
        "In av_offset_300ms.mp4 the audio is ahead of the picture by about a third of a second. Why?"
    )
    examples = [DRAFT] + re.findall(r"^Question: (.+)$", X.SYSTEM_AGENT_V3, re.M)
    dataset = lab04.load_dataset()
    for ex in examples:
        top = sorted(((jaccard(ex, r["question"]), r) for r in dataset), key=lambda t: -t[0])[:2]
        print(f"example: {ex[:60]}...")
        for score, r in top:
            print(f"   nearest {r['id']} ({r['split']}) jaccard {score:.2f}: {r['question'][:60]}...")

    # A rule you can put in CI: no few-shot example may be a near-copy of an eval question.
    for ex in examples:
        worst = max(jaccard(ex, r["question"]) for r in dataset)
        print(
            f"{'draft  ' if ex == DRAFT else 'shipped'} max overlap {worst:.2f} -> "
            f"{'OK' if worst < 0.4 else 'TOO CLOSE: rewrite or pick another example'}"
        )
    ```

    Output:

    ```text
    example: In av_offset_300ms.mp4 the audio is ahead of the picture by ...
       nearest m4q174 (train) jaccard 0.37: our av_offset_300ms.mp4 the audio is ahead of the lips by li...
       nearest m4q158 (test) jaccard 0.35: av_offset_300ms.mp4 the audio is ahead of the video by like ...
    example: Voices lead lip movement on one encoder output (av_offset_30...
       nearest m4q158 (test) jaccard 0.13: av_offset_300ms.mp4 the audio is ahead of the video by like ...
       nearest m4q101 (train) jaccard 0.12: customer says one of our videos takes ages to start, just si...
    example: lumen-l3: thumbnails go blank and we get codec errors (thumb...
       nearest m4q074 (train) jaccard 0.11: the lumen-l3 is widevine l1 right so we should be getting HD...
       nearest m4q119 (train) jaccard 0.11: can the lumen-l3 play the 4k hdr stuff or nah. we want to kn...
    draft   max overlap 0.37 -> OK
    shipped max overlap 0.13 -> OK
    shipped max overlap 0.11 -> OK
    ```

    On the regenerated dataset the draft just passes the 0.4 threshold, but look at its two nearest questions:
    m4q174 and m4q158 ask the same question about the same file in other words, and m4q158 is in the held-out test
    split. That is a near-copy by any reading, and word overlap scores it below the line because the rephrasings use
    different words ("lips", "video", "like"). The shipped examples were rewritten and share at most 13% of their
    words with any question. This is the case for reading the pairs just below the threshold, not only the ones
    above it.

    A near-copy matters because the model does not need the exact string: an example whose question and answer are
    nearly the test question hands it the answer, and the score then measures recall of the prompt, not diagnosis.
    It matters for the train split too, because the experiments here run on train plus dev; the "dev" score would
    be inflated exactly on the queries the examples resemble. Word overlap is a crude detector (it misses
    paraphrases with different words), so treat it as a floor: also keep a list of the sources of every example
    (`FEW_SHOT_SOURCES`), and check that the scenario-level gain holds on queries from scenarios the examples do not
    cover. The threshold (0.4 here) is a choice; set it by looking at the pairs just above and below it (on this
    dataset, a threshold of 0.3 would flag the draft and pass both shipped examples).

## Exercise 4: When does prompt caching pay, and what does batch save?

A MediaDoctor call has a 1,033-token cacheable prefix, about 400 other input tokens, and about 120 output tokens.
Using `Price.cost_usd` with the prices in `config/models.toml`, compute the cost per call with caching when the
cache is used by 1, 2, 3, and 10 calls before it expires, for Sonnet 5.5 and Haiku 5.5, and compare it with no
caching. Then compute what three dev-suite runs of v3-cache cost through the standard API and the
Batch API.

??? success "Solution"
    ```python
    # exercise-solution: when does prompt caching pay, and what does batch save?
    from evalkit import load_prices
    from mediadoctor import lab11

    PREFIX, REST, OUT = 1033, 400, 120  # tokens: cached prefix, rest of the input, output (per call)

    for model in ("claude-sonnet-5-5", "claude-haiku-5-5"):
        p = load_prices()[model]
        plain = p.cost_usd(PREFIX + REST, OUT)
        print(f"{model}: one call without caching ${plain:.6f}")
        for calls in (1, 2, 3, 10):
            # within one cache lifetime: the first call writes the prefix, the rest read it
            cached = p.cost_usd(REST, OUT, cache_write_tokens=PREFIX) + (calls - 1) * p.cost_usd(
                REST, OUT, cache_read_tokens=PREFIX
            )
            print(
                f"  {calls:2d} calls per cache lifetime: cached ${cached / calls:.6f}/call "
                f"vs ${plain:.6f}/call  ({cached / calls / plain - 1:+.0%})"
            )

    # The nightly eval: the dev tasks, standard vs Batch API (50% off, results within 24 h).
    s = lab11.summary("v3-cache")
    print(
        f"dev suite, 3 runs: standard ${3 * s.n * s.cost_per_task:.2f}, batch ${1.5 * s.n * s.cost_per_task:.2f}"
    )
    ```

    Output:

    ```text
    claude-sonnet-5-5: one call without caching $0.004066
       1 calls per cache lifetime: cached $0.004582/call vs $0.004066/call  (+13%)
       2 calls per cache lifetime: cached $0.003343/call vs $0.004066/call  (-18%)
       3 calls per cache lifetime: cached $0.002930/call vs $0.004066/call  (-28%)
      10 calls per cache lifetime: cached $0.002351/call vs $0.004066/call  (-42%)
    claude-haiku-5-5: one call without caching $0.000203
       1 calls per cache lifetime: cached $0.000229/call vs $0.000203/call  (+13%)
       2 calls per cache lifetime: cached $0.000170/call vs $0.000203/call  (-17%)
       3 calls per cache lifetime: cached $0.000150/call vs $0.000203/call  (-26%)
      10 calls per cache lifetime: cached $0.000122/call vs $0.000203/call  (-40%)
    dev suite, 3 runs: standard $1.61, batch $0.80
    ```

    Caching costs 25% extra on the prefix for the write, so a cache that is written and never read (one call per
    five-minute window) makes every call 13% more expensive. It breaks even before the second call and saves
    about 40% per call at ten calls per lifetime, where the remaining cost is mostly output tokens and the uncached
    part of the input. The lab's 46% saving per task is larger because each MediaDoctor task makes two calls in
    quick succession and the replay is one continuous batch (only one task in the whole run writes the cache). At low traffic (a request every ten
    minutes) each task's first call writes the cache again, only its second and third calls read it, and the
    saving shrinks. So state cache savings with the traffic they assume,
    and measure the real cache hit rate (`cache_read_input_tokens` over all input tokens) in production.

    Batch halves everything (the caching multipliers stack with it), so the nightly suite drops from $1.61 to $0.80
    for three runs; users cannot wait 24 hours, so it is for evals and backfills only.

## Exercise 5: Is the next experiment worth running?

The reference labels find a failure mode in only 3 of the retry configuration's 119 dev answers (the grader fails
far more; see Step 3 of the lesson). Suppose your next idea would remove a third of the labelled failures and break
almost nothing. Estimate how many paired tasks you need to detect that gain with 80% power, what the current dev set
can detect, and what a perfect score would save in cost per success. Should you run the experiment now?

??? success "Solution"
    ```python
    # exercise-solution: is the next experiment worth running?
    from evalkit.stats import mdd_paired, n_paired
    from mediadoctor import lab11

    s = lab11.summary("retry")
    labels = lab11.reference_labels()
    bad = sum(labels[("retry", c["id"])] != "none" for c in lab11.split_cases("dev"))
    print(f"retry on dev: the grader fails {s.n - s.successes}/{s.n}; the labels find {bad} defective answers")

    # A plausible next fix removes a third of the labelled failures and breaks almost nothing.
    gain = bad / 3 / s.n
    discordant = gain + 0.01  # tasks that change outcome: the fixed ones plus a few broken
    print(f"hoped-for gain {gain:+.3f}; discordant share {discordant:.3f}")
    print(f"tasks needed to see it (80% power, paired): {n_paired(discordant, gain)}")
    print(
        f"dev tasks we have: {s.n}; the largest gain {s.n} tasks can reliably see when 10% of tasks "
        f"change outcome: {mdd_paired(s.n, 0.10):.3f}"
    )

    # What a perfect score is worth in money, by the grader: cost per success if every task succeeded.
    print(
        f"cost/success now ${s.cost_per_success:.5f}; at 100% success ${s.cost_per_task:.5f} "
        f"({s.cost_per_task / s.cost_per_success - 1:+.0%})"
    )
    ```

    Output:

    ```text
    retry on dev: the grader fails 95/119; the labels find 3 defective answers
    hoped-for gain +0.008; discordant share 0.018
    tasks needed to see it (80% power, paired): 2044
    dev tasks we have: 119; the largest gain 119 tasks can reliably see when 10% of tasks change outcome: 0.080
    cost/success now $0.02422; at 100% success $0.00489 (-80%)
    ```

    Not on this dev set, and not for the usual reason. By the labels there is almost nothing left to fix: removing
    one of three failures is a gain of under one point, and seeing it reliably would take about 2,000 paired tasks,
    while 119 tasks can only see gains of about 8 points. Running it anyway produces a coin-flip "result" that you
    will be tempted to believe if it comes out positive.

    The last line is the trap. By the grader, a perfect system would cut cost per success by 80%, which looks like
    the biggest prize in the module. But almost all of the grader's 95 failures are answers the labels call
    correct: the money is not in the agent, it is in the measurement. The experiment worth running now is on the
    grader: measure its agreement with the labels (it fails every labelled defect but also rejects most good
    answers), fix its reference check, and re-run the comparisons. Then re-run error analysis on a larger, harder
    sample (module 9's production sampling) to find failures worth a fix. Stopping the agent work here is a
    decision, and it goes in the experiment log with these numbers.
