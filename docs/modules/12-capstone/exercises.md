# Exercises

Try each exercise before opening its solution. Code solutions are tested in CI and run from the repo root, in replay
mode, with no API key. The first two are the syllabus's peer-review exercise: score the reference report, then find
its three weakest claims.

## Exercise 1: Score the reference report

Score the [reference report](../../capstone/index.md) with the [rubric](rubric.md), criterion by criterion, before
reading the solution. Then use `capstone.check_report` to see which problems a machine can find, and make a draft
that fails it: what does the check catch, and what can only a reviewer catch?

??? success "Solution"
    ```python
    # exercise-solution: score a report against the template before reading it
    from pathlib import Path

    from mediadoctor import capstone as C

    text = Path("docs/capstone/index.md").read_text(encoding="utf-8")
    print("reference report:", C.check_report(text) or "no template problems")

    # A draft that dropped the intervals from the summary and renamed a section.
    draft = text.replace("## 6. Evaluators", "## 6. Our judges")
    draft = draft.replace(" [0.827, 0.942]", "").replace(" [0.573, 0.748]", "")
    draft = draft.replace(" [+0.157, +0.315]", "").replace(" [0.828, 0.994]", "")
    draft = draft.replace(" [0.655, 0.924]", "").replace(" [+0.000, +0.310]", "")
    for p in C.check_report(draft):
        print("draft:", p)
    ```

    Output:

    ```text
    reference report: no template problems
    draft: missing section: Evaluators
    draft: summary bullet 1 has a number without an interval
    ```

    The reference report passes the mechanical check, and a broken draft fails it on the renamed section and on the
    first summary bullet, which now quotes rates with no interval. (The other two bullets still carry intervals.)
    That is all a machine can see. A reviewer scoring with the rubric finds what `check` cannot: whether the
    decision follows from the evidence, whether the risks are the ones that would change the decision, and whether
    the claims in the prose are as strong as their numbers. A fair score for the reference report is 4 on most
    criteria, with 3 on **Recommendation** (the next steps are concrete but have no owners or dates beyond the
    first) and on **Slice deep-dive** (it says what 12 queries cannot show but proposes the fix only in outline).
    Your scores may differ by a point; the written reason for each score matters more than the number.

## Exercise 2: Find the three weakest claims

Every report has claims that are weaker than its tone. Find the three weakest in the reference report, and for each
put a number on how weak it is, without re-reading the held-out split.

??? success "Solution"
    ```python
    # exercise-solution: put numbers on the three weakest claims
    from evalkit.stats import bootstrap_ci, mcnemar_exact, wilson_interval
    from mediadoctor import capstone as C
    from mediadoctor import lab11

    # 1. "the one held-out look points the same way". Read the counts from the report (5 fixed, 1 broken);
    #    re-running the look to check it would be a second look.
    for broken in (1, 2):
        print(f"held out, 5 fixed and {broken} broken: McNemar p = {mcnemar_exact(broken, 5):.3f}")

    # 2. What the slice says about the retry step: it rests on 5 retries.
    ids = set(C.dev_ids("audio-focus"))
    tr = [t for t in lab11.task_results("retry") if t.case_id in ids and t.retried]
    fixed = sum(lab11.reference_labels()[("retry", t.case_id)] == "none" for t in tr)
    lo, hi = wilson_interval(fixed, len(tr))
    print(f"slice retries fixed {fixed}/{len(tr)}, 95% CI [{lo:.2f}, {hi:.2f}]")
    allt = [t for t in lab11.task_results("retry") if t.retried]
    fa = sum(lab11.reference_labels()[("retry", t.case_id)] == "none" for t in allt)
    lo, hi = wilson_interval(fa, len(allt))
    print(f"all retries fixed {fa}/{len(allt)}, 95% CI [{lo:.2f}, {hi:.2f}]")

    # 3. "cost per successful task -51%": the interval on the ratio, resampling queries in pairs.
    rows_a, rows_b = C.dev_rows("v1"), C.dev_rows("retry")
    ids = sorted(rows_a)


    def ratio(sample):
        ca = sum(rows_a[i].cost_usd for i in sample) / max(1, sum(rows_a[i].success for i in sample))
        cb = sum(rows_b[i].cost_usd for i in sample) / max(1, sum(rows_b[i].success for i in sample))
        return cb / ca - 1


    est, lo, hi = bootstrap_ci(ids, ratio, draws=2000, seed=12)
    print(f"cost per success change {est:+.1%} [{lo:+.1%}, {hi:+.1%}]")
    ```

    Output:

    ```text
    held out, 5 fixed and 1 broken: McNemar p = 0.219
    held out, 5 fixed and 2 broken: McNemar p = 0.453
    slice retries fixed 1/5, 95% CI [0.04, 0.62]
    all retries fixed 6/15, 95% CI [0.20, 0.64]
    cost per success change -51.4% [-56.7%, -46.5%]
    ```

    1. **"The one held-out look points the same way."** True, and weak: 5 fixed against 1 broken gives McNemar
       p = 0.22, and one more broken query would make it 0.45. The report frames the look as a check for reversal,
       not a second test, which is the right framing; a reader who skims "0.966 vs 0.828" will still take it as
       confirmation. The p-value belongs next to the numbers, as in section 7, so that nobody has to compute it.
    2. **The slice's statement about retries.** One fix in five retries, against six in fifteen overall: the
       intervals ([0.04, 0.62] and [0.20, 0.64]) overlap almost entirely. The report says this is too few to
       compare; any sentence that turned it into "the retry does not work on audio focus" would be unsupported.
       The supported finding is narrower: three ignored-tool-output failures survive the retry.
    3. **"Most failures start in the model's final answer or its plan... which is why the improvements are prompt
       and self-check changes."** This explains the choice after the fact. Module 3's first-upstream counts come
       from 100 different traces, and module 11 chose its fixes by expected value; the sentence implies a causal
       link the report never tested.

    And one claim that looks bold but is strong: the cost saving. Resampling queries in pairs gives −51%
    [−57%, −47%], so "cheaper per successful task" holds at any plausible level of noise. Checking is how you tell
    the two kinds apart: a reviewer should never mark a claim weak because it is large.

## Exercise 3: The DRM slice

Run the report for the `drm-resolution` slice without spending the held-out look. The candidate passes every DRM
query. Is the slice solved? What would you write in the report instead of "DRM: 100%"?

??? success "Solution"
    ```python
    # exercise-solution: the DRM slice, without spending the held-out look
    from evalkit.stats import wilson_interval
    from mediadoctor import capstone as C

    text = C.report_markdown("drm-resolution", release=False, today="2026-11-23")
    start = text.index("### The drm-resolution slice")
    for line in text[start:].splitlines():
        if line.startswith(("**Paired", "| `v1`", "| `retry`", "**Queries", "None.")):
            print(line[:120])
    r = next(r for r in C.slice_rows() if r["topic"] == "drm-resolution")
    lo, hi = wilson_interval(r["cand"], r["n"])
    print(
        f"retry on drm-resolution: {r['cand']}/{r['n']}, failure rate could still be up to {1 - lo:.0%}"
    )
    ```

    Output:

    ```text
    | `v1` | 0.867 (13/15) [0.621, 0.963] |
    | `retry` | 1.000 (15/15) [0.796, 1.000] |
    **Paired, v1 → retry on the slice:** +0.133 [+0.000, +0.333]; fixed 2, broken 0, McNemar p = 0.50.
    **Queries `retry` still fails on this slice** (0):
    None. With this few queries that is not proof the slice is solved: the upper end of the failure rate's interval is still
    retry on drm-resolution: 15/15, failure rate could still be up to 20%
    ```

    15 of 15 has a Wilson interval of [0.796, 1.000]: the true failure rate could still be one in five. Write
    "15/15 on dev; with 15 queries we cannot rule out a failure rate up to 20%" and add what the slice does not
    cover: every DRM query in the dataset has device evidence, none has a log or a licence-server error, and only
    two are plainly worded (`ambiguity: clear`). A support lead who routes DRM tickets to MediaDoctor on the
    strength of "100%" will meet the untested kinds first. The next step is data (module 4: tuples with log
    evidence and licence errors), not a prompt change.

## Exercise 4: How fragile is the last step?

The last kept step, `v3-cache` → `retry`, passed its rule with +0.046 [+0.009, +0.093] on 5 fixed and 0 broken
queries. How many broken queries would it take to reject it? What does that tell you about how to report it?

??? success "Solution"
    ```python
    # exercise-solution: how fragile is the last kept step?
    from evalkit.stats import paired_bootstrap_diff
    from mediadoctor import capstone as C

    ids = C.dev_ids()
    a = [C.dev_rows("v3-cache")[i].success for i in ids]
    b = [C.dev_rows("retry")[i].success for i in ids]
    print(
        f"as measured: fixed {sum(y and not x for x, y in zip(a, b))}, broken {sum(x and not y for x, y in zip(a, b))}"
    )

    # Break k of the queries both configurations pass (as if retry had made them worse) and re-test.
    both = [j for j, (x, y) in enumerate(zip(a, b)) if x and y]
    for k in range(4):
        bb = list(b)
        for j in both[:k]:
            bb[j] = False
        p = paired_bootstrap_diff(a, bb, seed=11)
        keep = "keep" if p.low > 0 else "reject"
        print(f"broken {k}: diff {p.diff:+.3f} [{p.low:+.3f}, {p.high:+.3f}]  -> {keep}")
    ```

    Output:

    ```text
    as measured: fixed 5, broken 0
    broken 0: diff +0.046 [+0.009, +0.093]  -> keep
    broken 1: diff +0.037 [+0.000, +0.083]  -> reject
    broken 2: diff +0.028 [-0.019, +0.074]  -> reject
    broken 3: diff +0.019 [-0.037, +0.074]  -> reject
    ```

    A single broken query takes the lower bound to zero and the step fails its pre-registered rule. That does not
    make the step wrong; it makes it fragile, and the report should say so (it does, in Risks: "rests on 5 fixed
    and 0 broken queries"). Two consequences. First, the retry step is the part of the recommendation most likely
    to disappear on new data or a live re-record, so a stakeholder should hear "most of the gain is the prompts;
    the retry adds a little more and costs 2.7 s at p95". Second, a cheaper fallback exists: Exercise 5.

## Exercise 5: The summary for a cheaper alternative

A stakeholder asks for the option without the retry: `v3-cache`. Write the three summary bullets for it, with
intervals, from `lab11`'s functions, and one sentence on what the retry adds on top.

??? success "Solution"
    ```python
    # exercise-solution: the three summary bullets for a cheaper alternative
    from mediadoctor import capstone as C
    from mediadoctor import lab11

    b, c = lab11.summary("v1"), lab11.summary("v3-cache")
    p = lab11.paired("v1", "v3-cache")
    q = lab11.paired("v3-cache", "retry")
    print(
        f"- Better answers: v3-cache {C.rate(c.successes, c.n)} vs v1 {C.rate(b.successes, b.n)}; "
        f"paired {C.diff(p)} ({p.b_only} fixed, {p.a_only} broken)."
    )
    print(
        f"- Cheaper: {C.money(c.cost_per_success)} {C.ci_money(c.cps_low, c.cps_high)} per success, "
        f"{c.cost_per_success / b.cost_per_success - 1:+.0%}; p95 {c.p95_ms / 1000:.1f} s "
        f"[{c.p95_low / 1000:.1f}, {c.p95_high / 1000:.1f}]."
    )
    print(
        f"- What retry adds on top: {C.diff(q)} success for "
        f"{lab11.summary('retry').cost_per_success / c.cost_per_success - 1:+.0%} cost per success "
        f"and +{(lab11.summary('retry').p95_ms - c.p95_ms) / 1000:.1f} s p95."
    )
    ```

    Output:

    ```text
    - Better answers: v3-cache 0.852 (92/108) [0.773, 0.907] vs v1 0.667 (72/108) [0.573, 0.748]; paired +0.185 [+0.111, +0.259] (20 fixed, 0 broken).
    - Cheaper: $0.00402 [$0.00365, $0.00443] per success, -54%; p95 7.8 s [7.2, 8.7].
    - What retry adds on top: +0.046 [+0.009, +0.093] success for +6% cost per success and +2.7 s p95.
    ```

    Without the retry, MediaDoctor still gains 18.5 points [11.1, 25.9] with nothing broken, costs 54% less per
    success, and its p95 falls to 7.8 s. The retry adds 4.6 points [0.9, 9.3] for 6% more per success and 2.7 s at
    p95. Both are defensible; which to ship depends on whether the users of MediaDoctor feel a wrong answer or a
    slow one more, and that is the stakeholder's call, not the eval's. A good report puts both options on one
    page and says which one the rule picks and why.
