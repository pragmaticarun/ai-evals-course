# Exercises

Try each exercise before opening its solution. Code solutions are tested in CI and run from the repo root.

## Exercise 1: An "uncertain" queue ordered by judge disagreement

The online judge passes some traces that other evidence says are bad (a failed code check, a thumbs-down, a tool
error, a retry), and fails some that look fine (a thumbs-up, a copied answer with clean checks). Those
disagreements are where a person's label is worth the most: they either catch a judge error or a signal's false
alarm.

1. Score each judged request by how many pieces of evidence contradict the judge's verdict.
2. Build a queue ordered by that score, one item per distinct trace.
3. Compare its top 20 with a random 20 from the same judged requests: how many judge-passed failures does each
   contain? Which failure modes does the judge miss?

??? success "Solution"
    ```python
    # exercise-solution: an "uncertain" queue ordered by judge disagreement
    from mediadoctor import lab09

    verdicts = lab09.judge_verdicts()
    checks, sig = lab09.check_results(), lab09.signals()


    def disagreement(r) -> int:
        """How many other pieces of evidence contradict the online judge on this request."""
        v = verdicts[r.source]
        bad = [
            not all(checks[r.id].values()),
            r.thumb == "down",
            "tool_error" in sig[r.id],
            "retried" in sig[r.id],
        ]
        good = [r.thumb == "up", r.copied and all(checks[r.id].values())]
        return sum(bad) if v else sum(good)


    judged = [r for r in lab09.judged_sample() if verdicts[r.source] is not None]
    seen, uncertain = set(), []
    for r in sorted(judged, key=lambda r: (-disagreement(r), lab09.stable_fraction(r.id, "tie"))):
        fp = lab09.fingerprint(lab09.store()[r.id])
        if fp not in seen:  # one item per distinct trace
            seen.add(fp)
            uncertain.append(r)


    def missed(r) -> bool:
        """The judge passed it, but the trace fails (on any mode): worth a human look."""
        return bool(verdicts[r.source]) and lab09.label_of(r.id).failed


    k = 20
    top = uncertain[:k]
    rand = sorted(uncertain, key=lambda r: lab09.stable_fraction(r.id, "random-20"))[:k]
    print(f"{len(judged)} judged requests, {len(uncertain)} distinct traces")
    print(
        f"top {k} by disagreement: score >= {disagreement(top[-1])}, judge-passed failures {sum(map(missed, top))}"
    )
    print(f"random {k}:              judge-passed failures {sum(map(missed, rand))}")
    modes = sorted({m for r in top if missed(r) for m in lab09.label_of(r.id).modes})
    print("modes the judge passed in the top 20:", ", ".join(modes))
    assert sum(map(missed, top)) > sum(map(missed, rand))
    ```

    Output:

    ```text
    229 judged requests, 106 distinct traces
    top 20 by disagreement: score >= 1, judge-passed failures 11
    random 20:              judge-passed failures 5
    modes the judge passed in the top 20: fabricated-evidence, format-violation, redundant-steps, retrieval-miss, unknown-device-guess, wrong-tool-args
    ```

    Ordering by disagreement roughly doubles the judge errors a reviewer finds per 20 traces (11 against 5). The modes
    it surfaces are the ones the tool-grounding judge was never asked about (format, redundant steps) and the new
    `unknown-device-guess`, where the judge was fooled by a confident answer. Two refinements worth trying: weight the
    evidence (a failed code check is near-certain, a slow response is not; see `lab09 signals`), and record each item's
    inclusion probability so labels from this queue can still be weighted into an estimate.

## Exercise 2: A drift alert rule, tested on replayed traffic

An alert rule has two costs: false alarms on a normal week and delay on a real change. Measure both for the
`tool_error` metric.

1. Take the reference rate p0 from Monday to Wednesday.
2. For CUSUM with p1 = 2·p0 and h of 2, 4, 5, and 6, and for a naive "a day's rate exceeds 1.5 × p0" rule, estimate
   the false-alarm rate per week by replaying weeks with no drift (resample the reference window's outcomes).
3. Run each rule on the real week and report when it alarms relative to the rollout. Which would you deploy?

??? success "Solution"
    ```python
    # exercise-solution: a drift alert rule, tested on replayed traffic
    import random

    from evalkit.monitor import bernoulli_cusum
    from mediadoctor import lab09

    reqs = list(lab09.traffic())
    stream = [lab09.metric_values(r)["tool_error"] for r in reqs]
    ref = [x for r, x in zip(reqs, stream, strict=True) if r.reference]
    p0 = sum(ref) / len(ref)


    def daily_rule(xs, factor=1.5, min_n=40):
        """Naive rule: alarm on the first day whose rate exceeds factor x the reference rate."""
        for i, d in enumerate(lab09.days()):
            day = [x for r, x in zip(reqs, xs, strict=True) if r.date == d]
            if len(day) >= min_n and sum(day) / len(day) > factor * p0:
                return i
        return None


    def false_alarm_rate(alarm, sims=300):
        """Replay a week with no drift: the reference window's outcomes, resampled in time order."""
        hits = 0
        for s in range(sims):
            rng = random.Random(s)
            hits += alarm([rng.choice(ref) for _ in stream]) is not None
        return hits / sims


    print(f"tool_error reference rate p0 = {p0:.3f} over {len(ref)} requests")
    print(f"{'rule':<26}{'false alarms/week':>18}  {'alarm on the real week'}")
    for h in (2.0, 4.0, 5.0, 6.0):

        def rule(xs, h=h):
            return bernoulli_cusum(xs, p0, 2 * p0, h).alarm_at

        at = rule(stream)
        when = f"{reqs[at].ts:%a %d %H:%M} IST, {(reqs[at].ts - lab09.ROLLOUT).total_seconds() / 3600:+.1f} h"
        print(f"{f'CUSUM p1=2*p0, h={h:g}':<26}{false_alarm_rate(rule):>18.2f}  {when}")
    d = daily_rule(stream)
    print(
        f"{'daily rate > 1.5 x p0':<26}{false_alarm_rate(daily_rule):>18.2f}  {lab09.day_label(lab09.days()[d])} (end of day)"
    )
    ```

    Output:

    ```text
    tool_error reference rate p0 = 0.089 over 372 requests
    rule                       false alarms/week  alarm on the real week
    CUSUM p1=2*p0, h=2                      0.99  Wed 18 13:48 IST, -20.2 h
    CUSUM p1=2*p0, h=4                      0.32  Thu 19 14:57 IST, +5.0 h
    CUSUM p1=2*p0, h=5                      0.12  Fri 20 05:46 IST, +19.8 h
    CUSUM p1=2*p0, h=6                      0.07  Fri 20 08:04 IST, +22.1 h
    daily rate > 1.5 x p0                   0.38  Thu 19 (end of day)
    ```

    h = 2 alarms on almost every normal week and fired on Wednesday, before anything happened: useless. h = 4 has a
    false alarm about one week in three and catches the rollout five hours in; h = 5 or 6 brings false alarms down to
    one in eight to fifteen weeks at the price of most of a day. The daily rule has the false-alarm rate of h = 4 but
    can only fire at the end of a day. With a person on call, h = 5 is a reasonable default for this volume;
    send h = 4 to a dashboard rather than a pager. Two caveats: resampling assumes requests are independent (retries
    and bursts are not), and the false-alarm rate per week grows with traffic, so re-tune h when volume changes.

## Exercise 3: Cohen's kappa by hand, and the rare-mode paradox

1. Compute p_o, p_e, and kappa for annotators A and B's verdicts on their 40 shared traces from the counts, and
   check the result against `evalkit.annotate.cohen_kappa`.
2. Do the same per failure mode (tagged or not) for `unknown-device-guess`, `fabricated-evidence`, and
   `vague-next-step`.
3. Explain why `vague-next-step` has 95% agreement and a kappa below 0.5.

??? success "Solution"
    ```python
    # exercise-solution: Cohen's kappa by hand, and the rare-mode paradox
    from collections import Counter

    from evalkit.annotate import cohen_kappa, load_annotations
    from mediadoctor import lab09

    a = {x.case_id: x for x in load_annotations(lab09.annotator_path("a"))}
    b = {x.case_id: x for x in load_annotations(lab09.annotator_path("b"))}
    ids = sorted(set(a) & set(b))


    def by_hand(la: list[str], lb: list[str]) -> tuple[float, float, float]:
        n = len(la)
        po = sum(x == y for x, y in zip(la, lb, strict=True)) / n
        ca, cb = Counter(la), Counter(lb)
        pe = sum(ca[k] / n * cb[k] / n for k in set(la) | set(lb))
        return po, pe, (po - pe) / (1 - pe)


    va, vb = [a[i].verdict for i in ids], [b[i].verdict for i in ids]
    po, pe, k = by_hand(va, vb)
    print(f"verdicts on {len(ids)} traces: p_o={po:.3f} p_e={pe:.3f} kappa={k:.3f}")
    assert abs(k - cohen_kappa(va, vb)) < 1e-12
    for mode in ("unknown-device-guess", "fabricated-evidence", "vague-next-step"):
        ma = ["y" if mode in a[i].modes else "n" for i in ids]
        mb = ["y" if mode in b[i].modes else "n" for i in ids]
        po, pe, k = by_hand(ma, mb)
        print(
            f"{mode:22} tagged by A {ma.count('y'):2}, by B {mb.count('y'):2}: p_o={po:.3f} p_e={pe:.3f} kappa={k:.2f}"
        )
    ```

    Output:

    ```text
    verdicts on 40 traces: p_o=0.950 p_e=0.600 kappa=0.875
    unknown-device-guess   tagged by A  9, by B  9: p_o=1.000 p_e=0.651 kappa=1.00
    fabricated-evidence    tagged by A 13, by B  8: p_o=0.875 p_e=0.605 kappa=0.68
    vague-next-step        tagged by A  1, by B  3: p_o=0.950 p_e=0.904 kappa=0.48
    ```

    For `vague-next-step`, both annotators say "no" on almost every trace, so chance alone would give 90% agreement
    (p_e = 0.904). The two traces where they differ are a large share of the little room above chance, so kappa is
    0.48 even though raw agreement is 95%. This is the "high agreement, low kappa" effect described by Feinstein and
    Cicchetti (1990). Report kappa per mode together with the counts; for a rare mode, read the disputed traces and
    sharpen the definition rather than trusting either number alone. `fabricated-evidence` is the more useful warning:
    A tags it 13 times (as does the reference) and B only 8, so B misses some unsupported citations. That is worth
    an alignment session.

## Exercise 4: What thumbs and copies really measure

The simulation gives every request a true label, which production never does. Use it to measure the biases of
explicit feedback:

1. Thumbs-down and thumbs-up rates for passing fast answers, passing slow answers, ordinary failures, and confident
   guesses about unknown devices.
2. How many users rate anything, and what share of requests carry a thumb.
3. The week's thumbs-down rate against its true failure rate.

??? success "Solution"
    ```python
    # exercise-solution: what thumbs and copies really measure
    from mediadoctor import lab09

    reqs = list(lab09.traffic())
    sig = lab09.signals()


    def rates(group):
        n = len(group)
        down = sum(r.thumb == "down" for r in group) / n
        up = sum(r.thumb == "up" for r in group) / n
        fail = sum(lab09.label_of(r.id).failed for r in group) / n
        return n, fail, down, up


    def guess(r):
        return "unknown-device-guess" in lab09.label_of(r.id).modes


    groups = {
        "all requests": reqs,
        "passing, fast": [
            r for r in reqs if not lab09.label_of(r.id).failed and "slow" not in sig[r.id]
        ],
        "passing, slow": [r for r in reqs if not lab09.label_of(r.id).failed and "slow" in sig[r.id]],
        "failing, not a guess": [r for r in reqs if lab09.label_of(r.id).failed and not guess(r)],
        "failing, confident guess": [r for r in reqs if guess(r)],
    }
    print(f"{'group':<26}{'n':>5}{'true fail':>11}{'thumbs-down':>13}{'thumbs-up':>11}")
    for name, g in groups.items():
        n, fail, down, up = rates(g)
        print(f"{name:<26}{n:>5}{fail:>11.2f}{down:>13.3f}{up:>11.3f}")
    raters = {r.user for r in reqs if r.thumb}
    print(
        f"\n{len(raters)} of {len({r.user for r in reqs})} users rated anything; "
        f"{sum(1 for r in reqs if r.thumb) / len(reqs):.1%} of requests carry a thumb"
    )
    _, week_fail, week_down, _ = rates(reqs)
    print(f"thumbs-down rate {week_down:.3f} vs true failure rate {week_fail:.3f}")
    ```

    Output:

    ```text
    group                         n  true fail  thumbs-down  thumbs-up
    all requests                776       0.34        0.044      0.041
    passing, fast               485       0.00        0.019      0.049
    passing, slow                27       0.00        0.037      0.111
    failing, not a guess        192       1.00        0.104      0.010
    failing, confident guess     72       1.00        0.056      0.042

    40 of 176 users rated anything; 8.5% of requests carry a thumb
    thumbs-down rate 0.044 vs true failure rate 0.340
    ```

    Three biases show up. Feedback is sparse and comes from a minority of users (40 of 176), so its rate is mostly a
    measure of who rates. Users punish what they can see: slow correct answers get twice the thumbs-down of fast
    ones, and confident wrong answers get fewer thumbs-down than visible failures and almost as many thumbs-up as
    correct ones. And the level is meaningless as a quality metric: 4.4% thumbs-down against 34% failing. Feedback is
    still a useful pointer (precision 0.71 in `lab09 signals`), which is how the queue uses it.

## Exercise 5: Close the loop: a check for the new mode, then golden candidates

1. Write a code check for `unknown-device-guess`: `codec_caps` failed for a device, and the answer still talks about
   that device without admitting the data is missing.
2. Measure its precision and recall on the 140 source traces against the reference labels, read any false positive,
   and count the requests it would flag in the week.
3. Turn annotator A's labels into golden candidates with `lab09.close_loop`, and summarise them: how many for the new
   mode, the proposed splits, and near-duplicates of existing golden questions.

??? success "Solution"
    ```python
    # exercise-solution: close the loop: a check for the new mode, then golden candidates
    import json
    import re

    from evalkit.annotate import load_annotations
    from mediadoctor import lab09

    ADMITS = re.compile(
        r"no .{0,20}profile|cannot confirm|can't confirm|no data|not in the device tables", re.I
    )


    def guesses_unknown_device(trace) -> bool:
        """FAIL (True) when codec_caps failed for a device and the answer still talks about that
        device's decoding without admitting the data is missing."""
        answer = lab09.answer_of(trace)
        for s in trace:
            a = s["attributes"]
            if a.get("gen_ai.tool.name") == "codec_caps" and s["status"]["code"] == "ERROR":
                device = json.loads(a["gen_ai.tool.call.arguments"]).get("device", "")
                if device and device in answer and not ADMITS.search(answer):
                    return True
        return False


    src = lab09.source_traces()
    truth = lab09.truth()
    tp = fn = 0
    fps = []
    for cid, t in src.items():
        got, want = guesses_unknown_device(t), "unknown-device-guess" in truth[cid].modes
        tp, fn = tp + (got and want), fn + (want and not got)
        if got and not want:
            fps.append(cid)
    print(
        f"check on the 140 source traces: precision {tp / (tp + len(fps)):.2f}, recall {tp / (tp + fn):.2f}"
    )
    for cid in fps:
        print(f"  flagged but labelled {';'.join(truth[cid].modes)}: {cid}: {truth[cid].note}")
    week = sum(guesses_unknown_device(lab09.store()[r.id]) for r in lab09.traffic())
    print(f"requests it flags in the week: {week} (it costs nothing to run on all traffic)")

    labels = load_annotations(lab09.annotator_path("a"))
    cands = lab09.close_loop(labels)
    new_mode = [c for c in cands if "unknown-device-guess" in c.modes]
    print(f"golden candidates from annotator A: {len(cands)}, {len(new_mode)} for the new mode")
    print(
        "proposed splits:",
        {s: sum(c.proposed_split == s for c in cands) for s in ("train", "dev", "test")},
    )
    near = [c for c in cands if c.near_duplicate_of]
    print(
        f"near-duplicates of existing golden questions: {len(near)}"
        + (f" (e.g. {near[0].id} ~ {near[0].near_duplicate_of}, {near[0].similarity})" if near else "")
    )
    assert fn == 0 and len(fps) <= 1
    ```

    Output:

    ```text
    check on the 140 source traces: precision 0.94, recall 1.00
      flagged but labelled wrong-tool-args: m3t010: wrong device name 'atlas_a1' -> tool error -> agent gave up and guessed
    requests it flags in the week: 78 (it costs nothing to run on all traffic)
    golden candidates from annotator A: 28, 9 for the new mode
    proposed splits: {'train': 17, 'dev': 5, 'test': 6}
    near-duplicates of existing golden questions: 2 (e.g. m9c-6fe3a42d ~ m4q073, 0.455)
    ```

    The check finds every labelled case. Its one false positive, `m3t010`, is a module 3 trace where a typo in the
    device name made `codec_caps` fail and the agent guessed: arguably the same failure, labelled under its root
    cause (`wrong-tool-args`). That is a taxonomy question, not a bug in the check; decide whether the new mode covers
    it and relabel consistently. Because the check costs nothing, it can run on all traffic and feed the CUSUM: 78
    flagged requests in the week, against the 9 traces a reviewer found in the queue. The candidates go to
    `data/golden/` only after review, with the two near-duplicates merged or dropped, and with a version bump of the
    golden manifest (module 8).
