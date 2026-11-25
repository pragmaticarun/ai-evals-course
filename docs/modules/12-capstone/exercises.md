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

    # A draft that dropped the intervals from the first summary bullet and renamed a section.
    draft = text.replace("## 6. Evaluators", "## 6. Our judges")
    draft = draft.replace(" [0.168, 0.319]", "").replace(" [0.205, 0.364]", "")
    draft = draft.replace(" [+0.000, +0.084]", "").replace(" [0.127, 0.434]", "")
    draft = draft.replace(" [-0.107, +0.107]", "")
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
    first) and on **Slice deep-dive** (it lists the 12 failing av-sync queries but labels them only "timeout or
    check failure"; a reviewer has to read the traces to learn that most of them are right answers the reference
    check misses, see the [lesson](index.md#step-3-error-analysis-on-the-slice)). Your scores may differ by a point;
    the written reason for each score matters more than the number.

## Exercise 2: Find the three weakest claims

Every report has claims that are weaker than its tone. Find the three weakest in the reference report, and for each
put a number on how weak it is, without re-reading the held-out split.

??? success "Solution"
    ```python
    # exercise-solution: put numbers on the three weakest claims
    from evalkit.stats import mcnemar_exact, wilson_interval
    from mediadoctor import capstone as C
    from mediadoctor import lab11

    # 1. "a check that the rejection hides no large gain". Read the counts from the report (1 fixed, 1 broken,
    #    +0.000 [-0.107, +0.107] on 28 queries); re-running the look to check it would be a second look.
    for fixed in (1, 3, 5):
        print(f"held out, {fixed} fixed and 1 broken: McNemar p = {mcnemar_exact(1, fixed):.3f}")

    # 2. "Most failures start in the model's turns, not in the tools": how many failing traces is that?
    up = C.m03()["upstream"]
    n, k = sum(up.values()), sum(c for s, c in up.items() if not s.startswith("tool"))
    lo, hi = wilson_interval(k, n)
    print(f"failures starting outside the tools: {k}/{n}, 95% CI [{lo:.2f}, {hi:.2f}]")

    # 3. "cascade is the best configuration that meets both guardrails": is it as good as v1?
    p = lab11.paired("v1", "cascade")
    print(f"v1 -> cascade: {C.diff(p)} ({p.b_only} fixed, {p.a_only} broken)")

    # And a claim that looks bold: v1 is over the cost guardrail.
    s = lab11.summary("v1")
    print(f"v1 cost per success {C.money(s.cost_per_success)} {C.ci_money(s.cps_low, s.cps_high)} vs $0.01")
    ```

    Output:

    ```text
    held out, 1 fixed and 1 broken: McNemar p = 1.000
    held out, 3 fixed and 1 broken: McNemar p = 0.625
    held out, 5 fixed and 1 broken: McNemar p = 0.219
    failures starting outside the tools: 3/3, 95% CI [0.44, 1.00]
    v1 -> cascade: +0.017 [-0.034, +0.067] (6 fixed, 4 broken)
    v1 cost per success $0.02883 [$0.02119, $0.04229] vs $0.01
    ```

    1. **"A check that the rejection hides no large gain."** The held-out look at `v2` came out 1 fixed and 1
       broken on 28 queries, +0.000 [-0.107, +0.107]. Even 5 fixed against 1 broken would give McNemar p = 0.22, so
       28 queries cannot rule out a gain of ten points either way. The look guards against a large reversal of the
       decision, not against a modest gain; the report should say "cannot rule out a gain of up to about 11
       points".
    2. **"Most failures start in the model's turns, not in the tools, so the changes tested target the prompt, the
       model, and a self-check."** It rests on 3 failing traces out of 100, with an interval from 0.44 to 1.00, and
       it explains the experiment's design after the fact: module 11 chose its changes by expected value, not from
       these counts.
    3. **"`cascade` is the best configuration that meets both guardrails."** True, and the recommendation leans on
       it as the next starting point. But against `v1` it is +0.017 [-0.034, +0.067] with 6 fixed and 4 broken: it
       meets the guardrails without being shown to answer as well as `v1`. A non-inferiority test against `v1`
       (module 11's -0.05 margin) would be the next experiment, not an adoption.

    And one claim that looks bold but is strong: "`v1` is over the cost guardrail". Its cost per success is
    $0.0288 [$0.0212, $0.0423], so even the bottom of the interval is twice the $0.01 limit. Checking is how you
    tell the two kinds apart: a reviewer should never mark a claim weak because it is large.

## Exercise 3: The DRM slice

Run the report for the `drm-resolution` slice without spending the held-out look. `v1` fails every DRM query. Is the
slice hopeless? What would you write in the report instead of "DRM: 0%"?

??? success "Solution"
    ```python
    # exercise-solution: the DRM slice, without spending the held-out look
    from collections import Counter

    from evalkit.stats import wilson_interval
    from mediadoctor import capstone as C

    text = C.report_markdown("drm-resolution", release=False, today="2026-11-23")
    start = text.index("### The drm-resolution slice")
    for line in text[start:].splitlines():
        if line.startswith(("**Paired", "| `v1`", "| `v2`", "**Queries")):
            print(line[:120])
    ids = C.dev_ids("drm-resolution")
    print("why v1 fails:", dict(Counter(C.base_mode(i) for i in ids if not C.dev_rows("v1")[i].success)))
    failed = Counter(c for i in ids for c, ok in C.dev_rows("v1")[i].checks if not ok)
    print("checks v1 fails:", dict(failed))
    r = next(r for r in C.slice_rows() if r["topic"] == "drm-resolution")
    lo, hi = wilson_interval(r["base"], r["n"])
    print(f"v1 on drm-resolution: {r['base']}/{r['n']}, success rate could still be up to {hi:.0%}")
    ```

    Output:

    ```text
    | `v1` | 0.000 (0/14) [0.000, 0.215] |
    | `v2` | 0.143 (2/14) [0.040, 0.399] |
    **Paired, `v1` → `v2` (rejected) on the slice:** +0.143 [+0.000, +0.357]; fixed 2, broken 0, McNemar p = 0.50.
    **Queries `v1` fails on this slice** (14):
    why v1 fails: {'a check failed': 13, 'timed out': 1}
    checks v1 fails: {'investigated': 6, 'correct': 14}
    v1 on drm-resolution: 0/14, success rate could still be up to 22%
    ```

    0 of 14 has a Wilson interval of [0.000, 0.215], so the slice says the success rate is low, not that it is zero.
    More important is why: one query timed out and the other 13 failed a code check. All 14 fail the `correct` check
    (the reference check of the diagnosis), six also fail `investigated` (no tool ran before the answer), and the
    reference labels record no failure mode for any of them. That disagreement is the finding. Read the first lines (`uv run mediadoctor-lab11 trace v1 m4q058`): the
    answers say the phone reports Widevine L3, the right diagnosis, in words the check's pattern
    (`security level L3`) does not match. So write "0/14 on dev by the reference check, which misses correct
    answers phrased differently; the labels find no failure mode in 14 answers", and make the next step a fix to
    the measurement (validate the check against the labels, as module 5 does for judges) before any prompt change.
    The six uninvestigated answers deserve a read of their own: all six are `missing-detail` questions, where
    asking which phone the user has may be the right move, or may be a skipped investigation the labels missed.
    Add what the slice does not cover: every DRM query in the dataset has device evidence and none has a log or a
    licence-server error.

## Exercise 4: How close was the rejection?

`v1` → `v2` was rejected with +0.042 [+0.000, +0.084] on 6 fixed and 1 broken queries. How many more fixed queries
would it have taken to pass the confidence-interval part of its rule? What does that tell you about how to report
it?

??? success "Solution"
    ```python
    # exercise-solution: how close was the rejection?
    from evalkit.stats import paired_bootstrap_diff
    from mediadoctor import capstone as C

    ids = C.dev_ids()
    a = [C.dev_rows("v1")[i].success for i in ids]
    b = [C.dev_rows("v2")[i].success for i in ids]
    print(
        f"as measured: fixed {sum(y and not x for x, y in zip(a, b))}, broken {sum(x and not y for x, y in zip(a, b))}"
    )

    # Fix k more of the queries both configurations fail (as if v2 had fixed them) and re-test.
    neither = [j for j, (x, y) in enumerate(zip(a, b)) if not x and not y]
    for k in range(4):
        bb = list(b)
        for j in neither[:k]:
            bb[j] = True
        p = paired_bootstrap_diff(a, bb, seed=11)
        keep = "passes the CI rule" if p.low > 0 else "fails the CI rule"
        print(f"{k} more fixed: diff {p.diff:+.3f} [{p.low:+.3f}, {p.high:+.3f}]  -> {keep}")
    ```

    Output:

    ```text
    as measured: fixed 6, broken 1
    0 more fixed: diff +0.042 [+0.000, +0.084]  -> fails the CI rule
    1 more fixed: diff +0.050 [+0.008, +0.101]  -> passes the CI rule
    2 more fixed: diff +0.059 [+0.008, +0.109]  -> passes the CI rule
    3 more fixed: diff +0.067 [+0.017, +0.118]  -> passes the CI rule
    ```

    One more fixed query would have lifted the lower bound above zero. The rejection is as fragile as an acceptance
    would have been, and the report should say so (it does, in Risks: "a rejection means the rule did not show an
    improvement ... not that there is none"). Two consequences. First, `v2` would still have been rejected: it is
    over both pre-registered guardrails (p95 12.0 s against 12 s, $0.0249 per success against $0.01), so the
    decision does not hinge on one query. Second, the honest summary for a stakeholder is "the v2 prompt may help a
    little; we cannot tell on 119 queries", not "the v2 prompt does not work".

## Exercise 5: The summary for a cheaper alternative

A stakeholder asks for the option that meets the guardrails: `cascade`. Write the three summary bullets for it,
with intervals, from `lab11`'s functions, and one sentence on what the routing adds over its parent.

??? success "Solution"
    ```python
    # exercise-solution: the three summary bullets for a cheaper alternative
    from mediadoctor import capstone as C
    from mediadoctor import lab11

    b, c = lab11.summary("v1"), lab11.summary("cascade")
    p = lab11.paired("v1", "cascade")
    q = lab11.paired("v3-cache", "cascade")
    print(
        f"- Answers: cascade {C.rate(c.successes, c.n)} vs v1 {C.rate(b.successes, b.n)}; "
        f"paired {C.diff(p)} ({p.b_only} fixed, {p.a_only} broken)."
    )
    print(
        f"- Cheaper: {C.money(c.cost_per_success)} {C.ci_money(c.cps_low, c.cps_high)} per success, "
        f"{c.cost_per_success / b.cost_per_success - 1:+.0%}; p95 {c.p95_ms / 1000:.1f} s "
        f"[{c.p95_low / 1000:.1f}, {c.p95_high / 1000:.1f}]; guardrails broken: {lab11.meets_guardrails(c) or 'none'}."
    )
    print(
        f"- What the routing adds over its rejected parent v3-cache: {C.diff(q)} success, "
        f"{c.cost_per_success / lab11.summary('v3-cache').cost_per_success - 1:+.0%} cost per success."
    )
    ```

    Output:

    ```text
    - Answers: cascade 0.252 (30/119) [0.183, 0.337] vs v1 0.235 (28/119) [0.168, 0.319]; paired +0.017 [-0.034, +0.067] (6 fixed, 4 broken).
    - Cheaper: $0.00504 [$0.00334, $0.00812] per success, -83%; p95 11.8 s [10.4, 23.0]; guardrails broken: none.
    - What the routing adds over its rejected parent v3-cache: +0.059 [+0.017, +0.101] success, -78% cost per success.
    ```

    `cascade` answers about as well as `v1` (+1.7 points [-3.4, +6.7]: not shown better, not shown worse), costs
    83% less per success, and its p95 of 11.8 s sits just inside the 12 s guardrail, with an interval that reaches
    23 s. Over its parent `v3-cache` the routing adds 5.9 points [1.7, 10.1] with nothing broken, but `v3-cache`
    itself was rejected, so `cascade` is not in the release chain. A good report puts this option on the page as
    the next experiment (a pre-registered non-inferiority test against `v1`) and says why the rule does not pick it
    today; whether a cheaper answer of similar quality is worth the latency risk is the stakeholder's call.
