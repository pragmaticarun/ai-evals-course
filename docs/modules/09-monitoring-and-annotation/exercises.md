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
    227 judged requests, 117 distinct traces
    top 20 by disagreement: score >= 1, judge-passed failures 2
    random 20:              judge-passed failures 0
    modes the judge passed in the top 20: fabricated-evidence
    ```

    The online judge passes every trace it applies to this week, so every failure it sees is a judge-passed one,
    and there are few: 4 failing distinct traces among 140, all `fabricated-evidence` (an unsupported detail in
    an otherwise right answer). The disagreement order puts 2 of them in its top 20; the random 20 contain none.
    Most of the top 20 are there because of a tool error on the `vela-v2`, which the agent handled correctly, so
    the score is a weak filter here: with failures this rare, any queue is mostly passing traces. On traffic
    with more failures the same ordering concentrates judge errors further. Two refinements worth trying: weight
    the evidence by its measured precision (see `lab09 signals`: this week a retry is the best pointer and a
    tool error points at nothing), and record each item's inclusion probability so labels from this queue can
    still be weighted into an estimate.

## Exercise 2: A drift alert rule, tested on replayed traffic

An alert rule has two costs: false alarms on a normal week and delay on a real change. Measure both for two metrics:
`slow`, which has a reference rate to drift from, and `tool_error`, which has none.

1. Take the reference rate p0 from Monday to Wednesday (with the lab's floor of 0.5%, since a zero rate cannot be
   doubled).
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


    def daily_rule(xs, p0, factor=1.5, min_n=40):
        """Naive rule: alarm on the first day whose rate exceeds factor x the reference rate."""
        for i, d in enumerate(lab09.days()):
            day = [x for r, x in zip(reqs, xs, strict=True) if r.date == d]
            if len(day) >= min_n and sum(day) / len(day) > factor * p0:
                return i
        return None


    def false_alarm_rate(alarm, ref, sims=300):
        """Replay a week with no drift: the reference window's outcomes, resampled in time order."""
        hits = 0
        for s in range(sims):
            rng = random.Random(s)
            hits += alarm([rng.choice(ref) for _ in reqs]) is not None
        return hits / sims


    fa = {}
    for metric in ("slow", "tool_error"):
        stream = [lab09.metric_values(r)[metric] for r in reqs]
        ref = [x for r, x in zip(reqs, stream, strict=True) if r.reference]
        p0 = max(sum(ref) / len(ref), 0.005)  # the lab's floor: a zero rate cannot be doubled
        print(
            f"\n{metric}: reference rate {sum(ref) / len(ref):.3f} over {len(ref)} requests, p0 = {p0:.3f}"
        )
        print(f"{'rule':<26}{'false alarms/week':>18}  {'alarm on the real week'}")
        for h in (2.0, 4.0, 5.0, 6.0):

            def rule(xs, h=h, p0=p0):
                return bernoulli_cusum(xs, p0, 2 * p0, h).alarm_at

            at = rule(stream)
            hours = (reqs[at].ts - lab09.ROLLOUT).total_seconds() / 3600 if at is not None else 0
            when = f"{reqs[at].ts:%a %d %H:%M} IST, {hours:+.1f} h" if at is not None else "none"
            fa[metric, h] = false_alarm_rate(rule, ref)
            print(f"{f'CUSUM p1=2*p0, h={h:g}':<26}{fa[metric, h]:>18.2f}  {when}")
        d = daily_rule(stream, p0)
        day = f"{lab09.day_label(lab09.days()[d])} (end of day)" if d is not None else "none"
        print(
            f"{'daily rate > 1.5 x p0':<26}{false_alarm_rate(lambda xs, p0=p0: daily_rule(xs, p0), ref):>18.2f}  {day}"
        )
    assert fa["slow", 2.0] > fa["slow", 4.0] > fa["slow", 6.0]
    assert all(fa["tool_error", h] == 0 for h in (2.0, 4.0, 5.0, 6.0))
    ```

    Output:

    ```text
    slow: reference rate 0.051 over 369 requests, p0 = 0.051
    rule                       false alarms/week  alarm on the real week
    CUSUM p1=2*p0, h=2                      0.89  Tue 17 14:43 IST, -43.3 h
    CUSUM p1=2*p0, h=4                      0.20  Fri 20 12:17 IST, +26.3 h
    CUSUM p1=2*p0, h=5                      0.09  Fri 20 12:54 IST, +26.9 h
    CUSUM p1=2*p0, h=6                      0.04  Fri 20 14:55 IST, +28.9 h
    daily rate > 1.5 x p0                   0.60  Fri 20 (end of day)

    tool_error: reference rate 0.000 over 369 requests, p0 = 0.005
    rule                       false alarms/week  alarm on the real week
    CUSUM p1=2*p0, h=2                      0.00  Thu 19 14:54 IST, +4.9 h
    CUSUM p1=2*p0, h=4                      0.00  Thu 19 18:36 IST, +8.6 h
    CUSUM p1=2*p0, h=5                      0.00  Thu 19 20:04 IST, +10.1 h
    CUSUM p1=2*p0, h=6                      0.00  Fri 20 03:14 IST, +17.2 h
    daily rate > 1.5 x p0                   0.00  Thu 19 (end of day)
    ```

    For `slow`, the trade-off is plain. h = 2 alarms on almost every normal week and fired on Tuesday, two days
    before anything happened: useless. h = 4 has a false alarm about one week in five and fires on Friday, the
    first full day of 4.2 traffic, when 17.6% of requests are slow; h = 5 or 6 brings false alarms down to one in
    eleven to twenty-five weeks for a delay of under three hours more. The daily rule is the worst of both: a false
    alarm in more than half of normal weeks, and it can only fire at the end of a day. With a person on call, h = 5
    is a reasonable default for this volume; send h = 4 to a dashboard rather than a pager.

    `tool_error` shows the trap in the method. The reference window has no tool errors at all, so a resampled
    "normal week" has none either, and every rule's false-alarm rate comes out as exactly 0. That is an artefact of
    replaying a window with zero events, not a property of the rule: in production, a single stray tool error
    moves a CUSUM with p0 = 0.5% by log 2 at once. Set the floor from what you are willing to page on (or from a
    longer history), and test the rule on a reference window that contains some events. Two more caveats:
    resampling assumes requests are independent (retries and bursts are not), and the false-alarm rate per week
    grows with traffic, so re-tune h when volume changes.

## Exercise 3: Cohen's kappa by hand, and the rare-category paradox

1. Compute p_o, p_e, and kappa for annotators A and B's verdicts on their 40 shared traces from the counts, and
   check the result against `evalkit.annotate.cohen_kappa`. Do the same for the one failure mode they use,
   `fabricated-evidence` (tagged or not).
2. Compute the same for each annotator's verdicts against the reference labels.
3. Explain why A agrees with the reference on 95% of traces and still has a kappa below 0.5, and what the two
   annotators' perfect agreement with each other does and does not tell you.

??? success "Solution"
    ```python
    # exercise-solution: Cohen's kappa by hand, and the rare-category paradox
    from collections import Counter

    from evalkit.annotate import cohen_kappa, load_annotations
    from mediadoctor import lab09

    a = {x.case_id: x for x in load_annotations(lab09.annotator_path("a"))}
    b = {x.case_id: x for x in load_annotations(lab09.annotator_path("b"))}
    ids = sorted(set(a) & set(b))
    ref = {i: lab09.label_of(i) for i in ids}


    def by_hand(la: list[str], lb: list[str]) -> tuple[float, float, float]:
        n = len(la)
        po = sum(x == y for x, y in zip(la, lb, strict=True)) / n
        ca, cb = Counter(la), Counter(lb)
        pe = sum(ca[k] / n * cb[k] / n for k in set(la) | set(lb))
        return po, pe, (po - pe) / (1 - pe) if pe < 1 else float("nan")


    def show(name, la, lb):
        po, pe, k = by_hand(la, lb)
        pos = [sum(x in ("fail", "y") for x in labels) for labels in (la, lb)]
        print(f"{name:32} fail/tagged {pos[0]} vs {pos[1]}: p_o={po:.3f} p_e={pe:.3f} kappa={k:.3f}")
        return k


    va, vb, vr = ([x[i].verdict for i in ids] for x in (a, b, ref))
    k_ab = show(f"A vs B, verdicts on {len(ids)} traces", va, vb)
    assert abs(k_ab - cohen_kappa(va, vb)) < 1e-12
    mode = "fabricated-evidence"
    ma, mb = (["y" if mode in x[i].modes else "n" for i in ids] for x in (a, b))
    show(f"A vs B, {mode}", ma, mb)
    k_ar = show("A vs reference, verdicts", va, vr)
    show("B vs reference, verdicts", vb, vr)
    assert abs(k_ar - cohen_kappa(va, vr)) < 1e-12
    differ = [i for i in ids if a[i].verdict != ref[i].verdict]
    print("traces where A and the reference differ:", ", ".join(differ))
    assert k_ab == 1.0 and k_ar < 0.5 and len(differ) == 2
    ```

    Output:

    ```text
    A vs B, verdicts on 40 traces    fail/tagged 1 vs 1: p_o=1.000 p_e=0.951 kappa=1.000
    A vs B, fabricated-evidence      fail/tagged 1 vs 1: p_o=1.000 p_e=0.951 kappa=1.000
    A vs reference, verdicts         fail/tagged 1 vs 3: p_o=0.950 p_e=0.904 kappa=0.481
    B vs reference, verdicts         fail/tagged 1 vs 3: p_o=0.950 p_e=0.904 kappa=0.481
    traces where A and the reference differ: r0031, r0634
    ```

    A and B agree on every verdict and on the one trace they tag, so kappa is 1.00. Notice how fragile that is:
    with one failure in 40, chance alone gives p_e = 0.951, and a single disputed trace would take kappa from 1.00
    to below 0.5. That is the "high agreement, low kappa" effect described by Feinstein and Cicchetti (1990), and the
    comparison with the reference shows it: 38 of 40 verdicts agree (p_o = 0.95), but both raters say "pass" on
    almost everything, so chance would give 0.904 and kappa is 0.48. Report kappa with the counts, and for a rare
    category read the disputed traces rather than trusting either number.

    The disputed traces matter more than the numbers. `r0031` and `r0634` both answer the question correctly and
    add an aside about the `lumen-l3`'s decoders that no tool returned. The reference calls that
    `fabricated-evidence`; A's notes say "not load-bearing" and pass them, and B passes them too. Two annotators
    agreeing with each other measures consistency, not correctness: here they share a reading of the definition
    that the reference does not. The fix is a sentence in the taxonomy ("a claim no tool returned is fabricated
    evidence even when the main answer does not rest on it", or the opposite), followed by relabelling.

## Exercise 4: What thumbs and copies really measure

The simulation gives every request a true label, which production never does. Use it to measure the biases of
explicit feedback:

1. Thumbs-down and thumbs-up rates for passing fast answers, passing slow answers, passing answers after a tool
   error, and failures.
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


    def ok(r):
        return not lab09.label_of(r.id).failed


    groups = {
        "all requests": reqs,
        "passing, fast": [r for r in reqs if ok(r) and "slow" not in sig[r.id]],
        "passing, slow": [r for r in reqs if ok(r) and "slow" in sig[r.id]],
        "passing, after a tool error": [r for r in reqs if ok(r) and "tool_error" in sig[r.id]],
        "failing": [r for r in reqs if not ok(r)],
    }
    print(f"{'group':<29}{'n':>5}{'true fail':>11}{'thumbs-down':>13}{'thumbs-up':>11}")
    for name, g in groups.items():
        n, fail, down, up = rates(g)
        print(f"{name:<29}{n:>5}{fail:>11.2f}{down:>13.3f}{up:>11.3f}")
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
    group                            n  true fail  thumbs-down  thumbs-up
    all requests                   766       0.03        0.018      0.033
    passing, fast                  688       0.00        0.009      0.035
    passing, slow                   53       0.00        0.094      0.019
    passing, after a tool error     90       0.00        0.022      0.067
    failing                         25       1.00        0.120      0.000

    32 of 176 users rated anything; 5.1% of requests carry a thumb
    thumbs-down rate 0.018 vs true failure rate 0.033
    ```

    Feedback is sparse and comes from a minority of users (32 of 176), so its rate is mostly a measure of who
    rates. Users punish what they can see: slow correct answers get ten times the thumbs-down of fast ones (0.094
    against 0.009), almost as many as real failures (0.120), so a thumbs-down is as likely to mean "slow" as
    "wrong": its precision in `lab09 signals` is only 0.21. The answers after a `vela-v2` tool error, which say
    plainly that the device has no profile, are rated like other correct answers. And the level says little about
    quality: 1.8% thumbs-down against 3.3% failing, with the two only loosely related. The generator behind the
    traffic also makes confident wrong answers attract thumbs-up as often as right ones, but this week has no such
    answers (the agent never guesses about the unknown device), so that bias cannot be measured here. Feedback is
    still a pointer, which is how the queue uses it.

## Exercise 5: Close the loop: a check for the new mode, then golden candidates

1. Write a code check for `unknown-device-guess` (the mode labels v2 adds): `codec_caps` failed for a device, and
   the answer still talks about that device without admitting the data is missing.
2. Count how many source traces the reference labels with the mode, run the check on the 140 source traces, read
   anything it flags, fix the check, and count the requests it would flag in the week.
3. Turn annotator A's labels into golden candidates with `lab09.close_loop`, then do the same with the reference
   labels for the whole queue, and summarise them: modes, proposed splits, and near-duplicates of existing golden
   questions.

??? success "Solution"
    ```python
    # exercise-solution: close the loop: a check for the new mode, then golden candidates
    import json
    import re

    from evalkit.annotate import load_annotations
    from mediadoctor import lab09

    ADMITS_V1 = r"no .{0,20}profile|cannot confirm|can't confirm|no data|not in the device tables"
    ADMITS_V2 = ADMITS_V1 + r"|profile isn't available|no decoder data"


    def guesses_unknown_device(trace, admits=ADMITS_V2) -> bool:
        """FAIL (True) when codec_caps failed for a device and the answer still talks about that
        device's decoding without admitting the data is missing."""
        answer = lab09.answer_of(trace)
        for s in trace:
            a = s["attributes"]
            if a.get("gen_ai.tool.name") == "codec_caps" and s["status"]["code"] == "ERROR":
                device = json.loads(a["gen_ai.tool.call.arguments"]).get("device", "")
                if device and device in answer and not re.search(admits, answer, re.I):
                    return True
        return False


    src, truth, st = lab09.source_traces(), lab09.truth(), lab09.store()
    labelled = [cid for cid in src if "unknown-device-guess" in truth[cid].modes]
    print(f"source traces labelled unknown-device-guess: {len(labelled)} of {len(src)}")
    flagged = {}
    for name, admits in (("v1", ADMITS_V1), ("v2", ADMITS_V2)):
        flagged[name] = [cid for cid, t in src.items() if guesses_unknown_device(t, admits)]
        week = sum(guesses_unknown_device(st[r.id], admits) for r in lab09.traffic())
        print(f"check {name}: flags {len(flagged[name])} source traces, {week} requests in the week")
        for cid in flagged[name]:
            answer = lab09.answer_of(src[cid]).removeprefix("Likely cause: ")
            print(f"  {cid} (reference: {truth[cid].verdict}): {answer[:72]}...")

    labels = load_annotations(lab09.annotator_path("a"))
    for who, labs in (
        ("annotator A (first 40 items)", labels),
        ("reference, whole queue", [lab09.label_of(it.request_id) for it in lab09.queue(limit=None)]),
    ):
        cands = lab09.close_loop(labs)
        splits = {s: sum(c.proposed_split == s for c in cands) for s in ("train", "dev", "test")}
        near = sum(bool(c.near_duplicate_of) for c in cands)
        print(f"golden candidates from {who}: {len(cands)}, splits {splits}, near-duplicates {near}")
        for c in cands:
            print(f"  {c.id} {c.proposed_split:5} {','.join(c.modes)}: {c.question[:60]}")
    assert not labelled and len(flagged["v1"]) == 3 and flagged["v2"] == []
    ```

    Output:

    ```text
    source traces labelled unknown-device-guess: 0 of 140
    check v1: flags 3 source traces, 4 requests in the week
      m9p03 (reference: pass): I can't say whether vela-v2 decodes AV1 in hardware: vela-v2's device pr...
      m9p13 (reference: pass): I can't determine this for vela-v2: vela-v2's device profile isn't avail...
      m9p15 (reference: pass): I can't determine this for vela-v2: vela-v2's device profile isn't avail...
    check v2: flags 0 source traces, 0 requests in the week
    golden candidates from annotator A (first 40 items): 1, splits {'train': 0, 'dev': 1, 'test': 0}, near-duplicates 0
      m9c-43ff17b7 dev   fabricated-evidence: [MD-4172] Our 4K60 AV1 trailer (av1_2160p60.mkv) drops frame
    golden candidates from reference, whole queue: 4, splits {'train': 0, 'dev': 1, 'test': 3}, near-duplicates 0
      m9c-37dcda1b test  fabricated-evidence: [MD-4110] Can we ship av1_2160p60.mkv as the default renditi
      m9c-43ff17b7 dev   fabricated-evidence: [MD-4172] Our 4K60 AV1 trailer (av1_2160p60.mkv) drops frame
      m9c-31196e1b test  fabricated-evidence: Ever since app 4.2 went out, the lumen-l3 plays av1_2160p60.
      m9c-b6ecdd3b test  fabricated-evidence: [MD-4188] Our live channel errors out if the app sat in the 
    ```

    No trace this week has the mode: on all 24 AV1 traces where `codec_caps` failed for the `vela-v2`, the agent
    said it had no profile for the device. The first version of the check still flags three of them, because its
    list of admissions does not include "profile isn't available" or "no decoder data". Every flag is a false
    positive, which is why you read them before trusting a check. After the fix it flags nothing, on the source
    traces or on any of the 766 requests. That is the useful result: a check that costs nothing runs on all
    traffic, so "no unknown-device guesses this week" is a statement about every request, not about a sample; if
    a later prompt or model starts guessing, the same check feeds a CUSUM. On data that has the failure, you would
    also measure its recall against labelled cases before relying on it.

    Annotator A's 40 labels give one golden candidate (`r0201`, `fabricated-evidence`, proposed for dev). The
    reference labels for the whole queue give four, one per failing distinct question, three of them proposed for
    test, none close to an existing golden question. The gap is A's two passes on `r0031` and `r0634` (exercise
    3) plus the one failure the first 40 items do not reach. Candidates go to `data/golden/` only after review,
    with a version bump of the golden manifest (module 8).
