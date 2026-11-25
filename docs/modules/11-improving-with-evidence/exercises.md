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
    best retry 0.898; point-estimate pick: retry
      haiku     diff -0.259 [-0.352, -0.176]  not shown within 2 pts  cost/success $0.00028
      cascade   diff -0.204 [-0.287, -0.130]  not shown within 2 pts  cost/success $0.00069
      v3-cache  diff -0.046 [-0.093, -0.009]  not shown within 2 pts  cost/success $0.00402
      retry     (the best)                      cost/success $0.00428
      v2        diff -0.139 [-0.204, -0.074]  not shown within 2 pts  cost/success $0.00815
      v1        diff -0.231 [-0.315, -0.157]  not shown within 2 pts  cost/success $0.00880
      v3        diff -0.065 [-0.120, -0.019]  not shown within 2 pts  cost/success $0.00981
    ```

    On point estimates the answer is retry itself: nothing else is within 2 points of 0.898 (v3-cache is 4.6 points
    below). With intervals, no configuration can be shown to be within 2 points of the best: even v3-cache's paired
    CI goes down to −9.3 points. A 2-point tolerance is below what 108 queries can resolve (about 8 points when 10%
    of queries change outcome).

    For the manager: "retry is the most accurate option we tested. v3 with caching is 6% cheaper per success and
    4.6 points less accurate (CI 0.9 to 9.3 points); we cannot call them equivalent at a 2-point tolerance with this
    data. If 'basically as good' means within 5 points, the pre-registered margin, v3-cache does not clear that
    either. If the 6% matters more than the points, the decision is a business call, and here are the numbers for
    it." Note that the cheapest option overall (Haiku) is not on the table at any tolerance anyone would accept.

## Exercise 2: Explain a latency regression from the traces

Switching from v3-cache to retry raised p95 latency by 2.7 s but p50 by only 0.7 s. Using the traces
(`lab11.task_results`, `lab11.spans_by_op`), explain where the extra time comes from, why p95 moved so much more
than p50, and what you would change to keep most of the accuracy gain at a lower p95.

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
    p50 5.14 -> 5.84 s;  p95 7.76 -> 10.42 s
    mean ms per task: {'agent calls': 5701, 'self-check': 392, 'tools': 29}
    not retried  n= 93  mean extra +0.37 s  max +1.59 s
    retried      n= 15  mean extra +3.45 s  max +5.44 s
    slowest 5%: m4q132 12.6s (retried), m4q081 11.6s (retried), m4q158 11.3s (retried), m4q068 10.8s (retried), m4q084 10.7s (retried)
    ```

    Two mechanisms, visible in the spans. Every task now makes one more call (the Haiku self-check, about 0.4 s), a
    small, uniform shift that moves p50 by about the same amount. The 15 retried tasks also make a second agent turn
    (3.4 s more on average, up to 5.4 s). They are 14% of tasks, so they barely touch the median, but they are
    exactly the tasks that land in the slowest 5%: all five slowest tasks are retried ones. A regression that hits a
    minority of tasks hard moves p95 and leaves p50 alone; that is why you always report both.

    Ways to keep most of the gain at a lower p95: run the self-check in parallel with streaming the first answer to
    the user and only retry when it fails (the user waits only on failures); give the retry a smaller step budget;
    or retry only for the failure modes the judge catches reliably and the agent can actually fix (here, 5 of 14
    caught defects were fixed). Each is a new configuration with one change; test it the same way, with p95 as a
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
       nearest m4q147 (train) jaccard 0.59: in av_offset_300ms.mp4 teh audio is ahead of teh picture by ...
       nearest m4q019 (train) jaccard 0.48: Hey, in av_offset_300ms.mp4 the audio is ahead of the pictur...
    example: Voices lead lip movement on one encoder output (av_offset_30...
       nearest m4q161 (train) jaccard 0.14: how do we tell whether teh a/v offset in av_offset_300ms.mp4...
       nearest m4q090 (train) jaccard 0.12: I know both streams in the file start at zero. How do we tel...
    example: lumen-l3: thumbnails go blank and we get codec errors (thumb...
       nearest m4q177 (train) jaccard 0.16: QA question: How do we find out whether the lumen-l3 will ge...
       nearest m4q042 (dev) jaccard 0.14: qa question: is teh lumen-l3 able to decode and display hdr1...
    draft   max overlap 0.59 -> TOO CLOSE: rewrite or pick another example
    shipped max overlap 0.14 -> OK
    shipped max overlap 0.16 -> OK
    ```

    The draft shares most of its words with m4q147 and m4q019 (a typo-ed copy and a rephrasing of the same
    question), because module 4 generated its queries from the same scenarios module 3's traces came from. The
    shipped examples were rewritten and share at most 16% of their words with any question.

    A near-copy matters because the model does not need the exact string: an example whose question and answer are
    nearly the test question hands it the answer, and the score then measures recall of the prompt, not diagnosis.
    It matters for the train split too, because the experiments here run on train plus dev; the "dev" score would
    be inflated exactly on the queries the examples resemble. Word overlap is a crude detector (it misses
    paraphrases with different words), so treat it as a floor: also keep a list of the sources of every example
    (`FEW_SHOT_SOURCES`), and check that the scenario-level gain holds on queries from scenarios the examples do not
    cover. The threshold (0.4 here) is a choice; set it by looking at the pairs just above and below it.

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
    claude-sonnet-5-5: one call without caching $0.004058
       1 calls per cache lifetime: cached $0.004573/call vs $0.004058/call  (+13%)
       2 calls per cache lifetime: cached $0.003338/call vs $0.004058/call  (-18%)
       3 calls per cache lifetime: cached $0.002926/call vs $0.004058/call  (-28%)
      10 calls per cache lifetime: cached $0.002350/call vs $0.004058/call  (-42%)
    claude-haiku-5-5: one call without caching $0.000203
       1 calls per cache lifetime: cached $0.000229/call vs $0.000203/call  (+13%)
       2 calls per cache lifetime: cached $0.000169/call vs $0.000203/call  (-16%)
       3 calls per cache lifetime: cached $0.000150/call vs $0.000203/call  (-26%)
      10 calls per cache lifetime: cached $0.000122/call vs $0.000203/call  (-40%)
    dev suite, 3 runs: standard $1.11, batch $0.55
    ```

    Caching costs 25% extra on the prefix for the write, so a cache that is written and never read (one call per
    five-minute window) makes every call 13% more expensive. It breaks even before the second call and saves
    about 40% per call at ten calls per lifetime, where the remaining cost is mostly output tokens and the uncached
    part of the input. The lab's 59% saving per success is larger because each MediaDoctor task makes two or three
    calls in quick succession and the replay is one continuous batch. At low traffic (a request every ten
    minutes) each task's first call writes the cache again, only its second and third calls read it, and the
    saving shrinks. So state cache savings with the traffic they assume,
    and measure the real cache hit rate (`cache_read_input_tokens` over all input tokens) in production.

    Batch halves everything (the caching multipliers stack with it), so the nightly suite drops from $1.11 to $0.55
    for three runs; users cannot wait 24 hours, so it is for evals and backfills only.

## Exercise 5: Is the next experiment worth running?

The recommended configuration succeeds on 97 of 108 dev tasks. Suppose your next idea would remove a third of the
remaining failures and break almost nothing. Estimate how many paired tasks you need to detect that gain with 80%
power, what the current dev set can detect, and what a perfect system would save in cost per success. Should you
run the experiment now?

??? success "Solution"
    ```python
    # exercise-solution: is the next experiment worth running?
    from evalkit.stats import mdd_paired, n_paired
    from mediadoctor import lab11

    s = lab11.summary("retry")
    remaining = 1 - s.rate
    print(f"retry: success {s.rate:.3f}; failures left {s.n - s.successes}/{s.n} = {remaining:.3f}")

    # A plausible next fix removes a third of the remaining failures and breaks almost nothing.
    gain = remaining / 3
    discordant = gain + 0.01  # tasks that change outcome: the fixed ones plus a few broken
    print(f"hoped-for gain {gain:+.3f}; discordant share {discordant:.3f}")
    print(f"tasks needed to see it (80% power, paired): {n_paired(discordant, gain)}")
    print(
        f"dev tasks we have: {s.n}; the largest gain {s.n} tasks can reliably see when 10% of tasks "
        f"change outcome: {mdd_paired(s.n, 0.10):.3f}"
    )

    # What a perfect fix is worth in money: cost per success if every task succeeded.
    print(
        f"cost/success now ${s.cost_per_success:.5f}; at 100% success ${s.cost_per_task:.5f} "
        f"({s.cost_per_task / s.cost_per_success - 1:+.0%})"
    )
    ```

    Output:

    ```text
    retry: success 0.898; failures left 11/108 = 0.102
    hoped-for gain +0.034; discordant share 0.044
    tasks needed to see it (80% power, paired): 297
    dev tasks we have: 108; the largest gain 108 tasks can reliably see when 10% of tasks change outcome: 0.084
    cost/success now $0.00428; at 100% success $0.00384 (-10%)
    ```

    Not on this dev set. The hoped-for gain is about 3.4 points; detecting it reliably needs about 300 paired tasks,
    nearly three times what you have, and 108 tasks can only reliably see gains of about 8 points. Running it anyway
    produces a coin-flip "result" that you will be tempted to believe if it comes out positive. The money is also
    small: a perfect system would cut cost per success by 10%.

    Better options, in order: grow the dev set from production traffic (module 9's sampling) so future experiments
    have the power they need; re-run error analysis on the 11 remaining failures to see whether they share a cause
    worth a larger fix; and spend the effort on the latency side (exercise 2), where the retry's p95 cost is easier
    to measure. Stopping here is a decision, and it goes in the experiment log with these numbers.
