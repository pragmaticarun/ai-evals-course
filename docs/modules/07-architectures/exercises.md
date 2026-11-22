# Exercises

Try each exercise before opening its solution. Code solutions are tested in CI and run from the repo root.

## Exercise 1: Build a hard-negative retrieval set

A **hard negative** is a passage that looks relevant (it shares the query's words or topic) but does not answer it.
Retrieval sets made only of easy queries overstate quality. Using `mediadoctor.rag` and `evalkit.retrieval`:

1. In the labelled set, which sections most often rank above the first relevant section for section+bm25?
2. Write six queries, each aimed at a section that has a close lexical neighbour in `data/kb_v2/` (HDR capture vs HDR
   display, AV1 encoding vs decoding, live latency vs falling behind the live window, banding vs blocking, Widevine
   provisioning vs security levels), label the answering section, and measure MRR and hit@1 for all four
   configurations.
3. For section+bm25, which queries does the hard negative win?

??? success "Solution"
    ```python
    # exercise-solution: a hard-negative retrieval set
    from collections import Counter

    from evalkit.retrieval import hit_at_k, reciprocal_rank
    from mediadoctor import lab07, rag

    # (a) Which sections most often outrank the first relevant one in the labelled set?
    above = Counter()
    for x in lab07.score_queries("section", "bm25"):
        for sid in x.ranked:
            if sid in x.query.relevant:
                break
            above[sid] += 1
    print("sections ranked above the first relevant one (section+bm25):", above.most_common(4))

    # (b) Queries written to sit next to a near-miss section: same words, different answer.
    HARD = [  # (query, answering section, the hard negative it is written against)
        ("How do I record HDR video with the camera?", "hdr-capture#1", "hdr-display-api"),
        ("How do I check whether the screen can show HDR10?", "hdr-display-api#1", "hdr-capture"),
        ("Which AV1 encoder settings should I use?", "av1-encoding#2", "av1-decoding"),
        (
            "How do I keep live latency low without falling out of the window?",
            "live-latency#1",
            "behind-live-window",
        ),
        ("Why do gradients in our dark scenes show stripes?", "color-banding#1", "blocking-artifacts"),
        (
            "Do I need provisioning before a Widevine license request?",
            "widevine-provisioning#1",
            "widevine-levels",
        ),
    ]
    for chunker, retriever in lab07.CONFIGS:
        rr, hit1 = [], []
        for text, answer, _negative in HARD:
            ranked = [c.section for c in rag.search(text, chunker, retriever, 5)]
            rr.append(reciprocal_rank(ranked, {answer}))
            hit1.append(hit_at_k(ranked, {answer}, 1))
        print(
            f"{chunker}+{retriever:<8} MRR {sum(rr) / len(rr):.2f}  hit@1 {sum(hit1) / len(hit1):.2f}"
        )

    print("section+bm25, top 1 per hard query:")
    for text, answer, negative in HARD:
        top = rag.search(text, "section", "bm25", 1)[0].section
        if top == answer:
            tag = "ok"
        elif top.startswith(negative + "#"):
            tag = "HARD NEGATIVE"
        else:
            tag = "same doc" if top.split("#")[0] == answer.split("#")[0] else "other miss"
        print(f"  {tag:<13} {top:<24} {text}")
    ```

    Output:

    ```text
    sections ranked above the first relevant one (section+bm25): [('av1-decoding#2', 4), ('av-sync#1', 2), ('av1-encoding#1', 2), ('surface-lifecycle#1', 2)]
    fixed+keyword  MRR 0.64  hit@1 0.50
    fixed+bm25     MRR 0.64  hit@1 0.50
    section+keyword  MRR 0.71  hit@1 0.67
    section+bm25     MRR 0.75  hit@1 0.67
    section+bm25, top 1 per hard query:
      ok            hdr-capture#1            How do I record HDR video with the camera?
      same doc      hdr-display-api#2        How do I check whether the screen can show HDR10?
      ok            av1-encoding#2           Which AV1 encoder settings should I use?
      HARD NEGATIVE behind-live-window#1     How do I keep live latency low without falling out of the window?
      ok            color-banding#1          Why do gradients in our dark scenes show stripes?
      ok            widevine-provisioning#1  Do I need provisioning before a Widevine license request?
    ```

    The sections that most often outrank the relevant one are the broad ones: `av1-decoding#2` ("Hardware decoding
    depends on the chip") collects words like "decoder", "hardware", and "device" that many codec questions use.
    On the hard set, section+bm25 still has the best MRR (0.75), but only 4 of 6 queries put the answer first. The
    live-latency query loses to `behind-live-window#1` because "live", "window", and "falling" all appear there, and
    the HDR10 screen query lands on the right document but the less specific section. Six queries is far too few to
    compare configurations (module 6); the value of the set is that each query is a regression test for a confusion
    you know about. Grow it from real misses: every time a user's question retrieves a near-miss, add it.

## Exercise 2: A session-level judge for "gave up too early"

The lab's `gave-up-early` judge reads whole transcripts. Write a cheap alternative: a regex on the last agent turn
(final answer plus give-up phrases), and compare it with the judge on the 32 labelled sessions. Then combine them
(flag a give-up only if both do). Which would you deploy?

??? success "Solution"
    ```python
    # exercise-solution: a session-level gave-up-early check, regex vs judge
    import re

    from evalkit.judge import confusion
    from mediadoctor import lab07

    GIVE_UP = re.compile(r"can't tell|hard to say|contact|vendor|bug report|many possible causes", re.I)


    def gave_up(session) -> bool:
        """Gave up: the last agent turn is a final answer that matches a give-up phrase."""
        last = session.agent_turns[-1]
        return "Likely cause:" in last and bool(GIVE_UP.search(last))


    heuristic = {sid: not gave_up(s) for sid, s in lab07.sessions().items()}  # PASS = kept going
    print("regex:", lab07.gave_up_confusion(heuristic))
    print("judge:", lab07.gave_up_confusion())

    labels = {sid: r["gave_up_early"] == "yes" for sid, r in lab07.session_labels().items()}
    for sid, s in lab07.sessions().items():
        if gave_up(s) != labels[sid]:
            print(f"  regex wrong on {sid}: {s.agent_turns[-1].splitlines()[0][:80]}")

    human = {sid: not v for sid, v in labels.items()}
    both = {sid: heuristic[sid] and bool(lab07.gave_up_verdicts()[sid].passed) for sid in human}
    print("regex AND judge:", confusion(human, both))
    ```

    Output:

    ```text
    regex: n=32 (human pass 25, fail 7)  TPR 0.92 (23/25)  TNR 1.00 (7/7)  agreement 0.94
    judge: n=32 (human pass 25, fail 7)  TPR 0.92 (23/25)  TNR 0.86 (6/7)  agreement 0.91
      regex wrong on c01-v1: Likely cause: Hard to say for sure, but network throughput is probably too low f
      regex wrong on c13-v2: Likely cause: Since the decoder supports these clips, the files themselves are p
    regex AND judge: n=32 (human pass 25, fail 7)  TPR 0.92 (23/25)  TNR 1.00 (7/7)  agreement 0.94
    ```

    On these 32 sessions the regex looks better than the judge (TNR 1.00 vs 0.86), and that is exactly the trap: the
    phrases came from reading these same sessions, so the regex is fitted to its test set. Its two errors are
    hedges, not give-ups ("hard to say for sure, but..." and "if it persists, contact the device vendor"), which
    any phrase list will keep tripping on. The judge's miss is the polite give-up after a question (`c06-v2`). To
    choose, write the regex on half the sessions, measure both on the other half (module 5's dev/test split), and
    expect the regex to drop. In production, a cheap regex can pre-filter and the judge can confirm; note that the
    "AND" combination only helps if the two make different mistakes, which needs more than 7 positives to show.

## Exercise 3: Retrieval fix or generation fix?

For each RAG system, compute (a) the pass rate now, (b) the pass rate if retrieval were perfect (every query gets
an answering passage, and the generator does as well as it does on hits today), and (c) the pass rate if the
generator never failed when it had the answer. Then break the improved system's generation failures down by cause.

??? success "Solution"
    ```python
    # exercise-solution: which fix is worth more, retrieval or generation?
    from mediadoctor import lab07

    for system in ("baseline", "improved"):
        a = lab07.attribution(system)
        n = sum(a.values())
        hits = a["pass"] + a["generation failure"]
        now = (a["pass"] + a["pass despite miss"]) / n
        perfect_retrieval = a["pass"] / hits  # every query gets a hit; generation behaves as on hits
        perfect_generation = hits / n + a["pass despite miss"] / n  # every hit passes
        print(
            f"{system:<9} now {now:.2f} | perfect retrieval {perfect_retrieval:.2f} "
            f"(+{perfect_retrieval - now:.2f}) | perfect generation on hits {perfect_generation:.2f} "
            f"(+{perfect_generation - now:.2f})"
        )

    why = {}
    for r in lab07.rag_runs().values():
        lab = lab07.rag_labels()[r.id]
        if r.system == "improved" and r.hit and not (lab["correct"] and lab["faithful"]):
            why[lab["note"]] = why.get(lab["note"], 0) + 1
    print("improved, generation failures by cause:", why)
    ```

    Output:

    ```text
    baseline  now 0.56 | perfect retrieval 0.75 (+0.19) | perfect generation on hits 0.75 (+0.19)
    improved  now 0.60 | perfect retrieval 0.72 (+0.12) | perfect generation on hits 0.83 (+0.23)
    improved, generation failures by cause: {'correct core, plus a specific claim the passages do not contain': 8, 'answers from an unrelated passage in the context': 3}
    ```

    For the baseline both fixes are worth the same (+0.19). After the retrieval improvement, perfect retrieval
    would add only 12 points but a perfect generator 23: the bottleneck has moved. Eight of the 11 generation
    failures add a specific claim that is not in the passages, so the next change is in the prompt or the
    generation step (quote the passage, forbid unsupported specifics), measured with a validated faithfulness
    judge. Both ceilings are estimates: "perfect retrieval" assumes the newly retrieved queries behave like the
    current hits, which is optimistic, because the hard-to-retrieve queries are often hard to answer too.

## Exercise 4: Find the transition-matrix hotspot and price the fix

From the multi-agent runs: (1) list the hottest cells; (2) for runs that first fail at `codec_caps`, show the device
arguments that failed; (3) count passing runs that hit a tool error and recovered, and their step efficiency;
(4) estimate the pass rate if `codec_caps` accepted display names.

??? success "Solution"
    ```python
    # exercise-solution: find the transition-matrix hotspot and price the fix
    from collections import Counter

    from evalkit.trajectory import step_efficiency
    from mediadoctor import lab07

    runs, refs = lab07.team_runs(), lab07.agent_refs()
    fails = {cid: lab07.failure_of(r) for cid, r in runs.items()}
    cells = Counter(f for f in fails.values() if f)
    cell, count = cells.most_common(1)[0]
    print(f"hottest cells: {cells.most_common(3)}")

    # Who fails at codec_caps, and with what arguments?
    args = Counter()
    for cid, f in fails.items():
        if f and f[1] == "codec_caps":
            bad = next(s for s in runs[cid].tool_steps if s.name == "codec_caps" and not s.ok)
            args[bad.args["device"]] += 1
    print("failed codec_caps device arguments:", dict(args))

    # The same mistake also happens in runs that recovered: they pass, but pay for it.
    recovered = [
        cid
        for cid, r in runs.items()
        if refs[cid]["verdict"] == "pass" and any(not s.ok for s in r.tool_steps)
    ]
    eff = [step_efficiency(lab07.minimal_calls(c), runs[c].model_calls) for c in recovered]
    print(
        f"passed after a failed tool call: {len(recovered)} runs, mean step efficiency {sum(eff) / len(eff):.2f}"
    )

    n = len(runs)
    k = sum(refs[c]["verdict"] == "pass" for c in runs)
    fixable = sum(1 for f in fails.values() if f and f[1] == "codec_caps")
    print(f"pass rate now {k / n:.2f}; if codec_caps accepted display names: {(k + fixable) / n:.2f}")
    ```

    Output:

    ```text
    hottest cells: [(('evidence', 'answer'), 6), (('handoff', 'codec_caps'), 5), (('start', 'plan'), 4)]
    failed codec_caps device arguments: {'Lumen L3': 5, 'Atlas A1': 1}
    passed after a failed tool call: 5 runs, mean step efficiency 0.83
    pass rate now 0.66; if codec_caps accepted display names: 0.77
    ```

    Three cells tie for attention: synthesis (`evidence → answer`, 6), routing (`start → plan`, 4), and the tool
    argument problem (`handoff → codec_caps` plus `logcat_grep → codec_caps`, 6 together). The tool problem is the
    cheapest to fix and the most certain: every one of those failures is a display name ("Lumen L3", "Atlas A1")
    passed as a device id, and the same mistake shows up in runs that recovered, costing them an extra model call.
    Normalising names in the tool (or listing the valid ids in the specialist's tool description) would lift the
    pass rate from 0.66 to about 0.77 on this set, if nothing else changes. Re-run the matrix after the fix:
    failures that were hidden behind the first one may surface.

## Exercise 5: The vision judge by severity, and how many frames you need

Using `lab07.frame_rows()`, report each judge's detection rate per severity with Wilson intervals, list its false
alarms, and use `evalkit.stats.n_for_halfwidth` to work out how many frames per severity would give a ±0.15
interval.

??? success "Solution"
    ```python
    # exercise-solution: the vision judge by severity, and how many frames you need
    from evalkit.stats import n_for_halfwidth, wilson_interval
    from mediadoctor import lab07

    for judge in ("frame-blocking", "frame-banding"):
        rows = [r for r in lab07.frame_rows() if r["judge"] == judge]
        for sev in ("severe", "mild"):
            s = [r for r in rows if r["present"] and r["severity"] == sev]
            k = sum(r["flagged"] for r in s)
            lo, hi = wilson_interval(k, len(s))
            print(f"{judge:<15} {sev:<7} detected {k}/{len(s)}  95% CI [{lo:.2f}, {hi:.2f}]")
        clean = [r for r in rows if not r["present"]]
        fa = [r["image"] for r in clean if r["flagged"]]
        print(f"{'':<15} false alarms {len(fa)}/{len(clean)}: {fa}")

    for p in (0.5, 0.8):
        print(f"frames per severity for +/-0.15 around {p}: {n_for_halfwidth(p, 0.15)}")
    ```

    Output:

    ```text
    frame-blocking  severe  detected 3/3  95% CI [0.44, 1.00]
    frame-blocking  mild    detected 1/3  95% CI [0.06, 0.79]
                    false alarms 1/10: ['banding_severe_b.png']
    frame-banding   severe  detected 3/3  95% CI [0.44, 1.00]
    frame-banding   mild    detected 1/3  95% CI [0.06, 0.79]
                    false alarms 1/10: ['blocking_severe_gradient.png']
    frames per severity for +/-0.15 around 0.5: 43
    frames per severity for +/-0.15 around 0.8: 28
    ```

    "Detects 3 of 3 severe artifacts" sounds perfect and is compatible with a true rate of 0.44; "1 of 3 mild" is
    compatible with anything from 0.06 to 0.79. Sixteen frames are enough to see how the judge behaves, not to
    certify it: for ±0.15 you need 30 to 45 frames per severity and artifact, which `make_module07_images.sh` can
    generate cheaply by varying sources, quantisers, and bit depths (the labels come with the recipe). Before
    scaling up, look at the false alarms: the banding judge's alarm on `blocking_severe_gradient.png` is arguably
    right, because heavy quantisation of a gradient also produces bands. Decide whether the label or the judge is
    wrong (module 5's alignment step), then fix the label set or the criterion.
