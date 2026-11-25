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
    regex: n=32 (human pass 29, fail 3)  TPR 1.00 (29/29)  TNR 0.00 (0/3)  agreement 0.91
    judge: n=32 (human pass 29, fail 3)  TPR 1.00 (29/29)  TNR 0.00 (0/3)  agreement 0.91
      regex wrong on c05-v1: Likely cause: The audio and video timestamps are offset, commonly from mismatche
      regex wrong on c06-v1: Likely cause: The HDR video is probably being rendered without HDR-to-SDR tone m
      regex wrong on c13-v1: Likely cause: The phone likely lacks a hardware decoder profile for that HDR for
    regex AND judge: n=32 (human pass 29, fail 3)  TPR 1.00 (29/29)  TNR 0.00 (0/3)  agreement 0.91
    ```

    Neither check catches a single give-up. The regex looks for phrases like "can't tell", "contact the vendor",
    and "many possible causes", and the judge was written for the same kind of give-up. The three labelled give-ups
    (`c05-v1`, `c06-v1`, `c13-v1`) are none of these. They are v1 answers given without asking for the missing
    fact, and they sound confident ("The audio and video timestamps are offset, commonly from...") but hedge across
    several causes and offer only a diagnostic step. The 0.91 agreement is just the base rate: a check that never
    flags anything agrees on the 29 sessions that did not give up. Combining the two changes nothing, because both
    fail the same way.

    Before choosing between the regex and the judge, fix the definition. Read the three positives, write down what
    makes them give-ups ("answers a question it should have asked, with a list of hedged causes"), and rewrite the
    judge prompt or the regex to match. Develop on half the sessions, measure on the other half (module 5's dev/test
    split), and expect too few positives to say much: with 3 give-ups in 32, you need more sessions, or a weaker
    prompt that gives up more often, before any TNR means anything.

## Exercise 3: Retrieval fix or generation fix?

For each RAG system, compute (a) the pass rate now, (b) the pass rate if retrieval were perfect (every query gets
an answering passage, and the generator does as well as it does on hits today), and (c) the pass rate if the
generator never failed when it had the answer. Then break the improved system's failures down by component.

??? success "Solution"
    ```python
    # exercise-solution: which fix is worth more, retrieval or generation?
    from collections import defaultdict

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

    failures = defaultdict(list)
    for r in lab07.rag_runs().values():
        lab = lab07.rag_labels()[r.id]
        if r.system == "improved" and not (lab["correct"] and lab["faithful"]):
            failures["generation failure" if r.hit else "retrieval failure"].append(r.query.id)
    print("improved, failures by component:", dict(failures))
    ```

    Output:

    ```text
    baseline  now 0.75 | perfect retrieval 1.00 (+0.25) | perfect generation on hits 0.75 (+0.00)
    improved  now 0.83 | perfect retrieval 1.00 (+0.17) | perfect generation on hits 0.83 (+0.00)
    improved, failures by component: {'retrieval failure': ['r06', 'r07', 'r11', 'r13', 'r22', 'r23', 'r45', 'r46']}
    ```

    In this data the question has a one-sided answer. The generator passed every query where an answering passage
    reached it, so a perfect generator would add nothing (+0.00), and every remaining failure is retrieval: all
    eight of the improved system's failures are queries where no answering passage was in the top 3, and the
    generator declined or hedged instead of guessing. The next change is in search: query rewriting or embeddings
    for the vocabulary gaps (r07, r11, r13 are the codec misses from the lab), not the prompt. Treat the
    "perfect retrieval 1.00" ceiling as optimistic. It assumes the newly retrieved queries behave like the current
    hits, but the hard-to-retrieve queries are often hard to answer too. On a system whose generator also fails, the
    same three numbers show how much each fix is worth, and the bottleneck can move after a retrieval fix.

## Exercise 4: Find the transition-matrix hotspot and price the fix

From the multi-agent runs: (1) list the hottest cells and read the notes of the runs in the hottest one; (2) count
the runs whose route differed from the reference, their verdicts and step efficiency; (3) list passing runs that
never gathered the reference's expected evidence; (4) estimate the pass rate if the hottest cell were fixed.

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
    for cid, f in fails.items():
        if f == cell:
            print(f"  {cid}: {refs[cid]['note'][:90]}")

    # Upstream deviations that did not fail the run: wrong routes, and passes without the expected evidence.
    wrong_route = [cid for cid, r in runs.items() if not lab07.states(r)[0][1]]
    passed = Counter(refs[c]["verdict"] for c in wrong_route)
    print(f"wrong route: {len(wrong_route)} runs, verdicts {dict(passed)}")
    no_evidence = [
        cid
        for cid, r in runs.items()
        if refs[cid]["verdict"] == "pass" and lab07.states(r)[-2] != ("evidence", True)
    ]
    print(f"passed without the expected evidence: {no_evidence}")
    eff = [step_efficiency(lab07.minimal_calls(c), runs[c].model_calls) for c in wrong_route]
    print(f"wrong-route runs, mean step efficiency {sum(eff) / len(eff):.2f}")

    n = len(runs)
    k = sum(refs[c]["verdict"] == "pass" for c in runs)
    print(f"pass rate now {k / n:.2f}; if every {cell} failure were fixed: {(k + count) / n:.2f}")
    ```

    Output:

    ```text
    hottest cells: [(('evidence', 'answer'), 2)]
      m4q028: Generic answer: it restates the KB's audio-focus note but does not answer what was asked (
      m4q081: Generic answer: it restates the KB ('handleAudioFocus should pause for you'), admits it ca
    wrong route: 11 runs, verdicts {'pass': 11}
    passed without the expected evidence: ['m4q052', 'm4q163', 'm4q192']
    wrong-route runs, mean step efficiency 0.77
    pass rate now 0.96; if every ('evidence', 'answer') failure were fixed: 1.00
    ```

    The matrix has one hot cell, and it holds both failures: synthesis (`evidence → answer`). In both runs the
    knowledge specialist found only a general audio-focus note, and the planner restated it instead of answering
    the specific question. The fix is in the planner's answer step: say what the knowledge base does not cover
    instead of padding with what it does. That would lift the pass rate from 0.96 to 1.00 on this set, but two runs
    are far too few to price a fix (module 6). The upstream deviations matter more for the eval itself. The planner
    picked a different route from the reference 11 times, every one of those runs passed, and the extra specialists
    cost about a quarter of the model calls (mean step efficiency 0.77). Three runs passed without the reference's
    expected evidence. Before you count either as an error, check whether the reference trajectory is too strict.
    Re-run the matrix on a harder set or a weaker model: the method only shows hotspots when there are failures to
    spread across it.

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
    frame-blocking  mild    detected 3/3  95% CI [0.44, 1.00]
                    false alarms 4/10: ['banding_severe_a.png', 'banding_severe_b.png', 'banding_severe_c.png', 'banding_mild_a.png']
    frame-banding   severe  detected 3/3  95% CI [0.44, 1.00]
    frame-banding   mild    detected 3/3  95% CI [0.44, 1.00]
                    false alarms 2/10: ['blocking_severe_mandelbrot.png', 'blocking_severe_gradient.png']
    frames per severity for +/-0.15 around 0.5: 43
    frames per severity for +/-0.15 around 0.8: 28
    ```

    "Detects 3 of 3" at both severities sounds perfect and is compatible with a true rate of 0.44. Sixteen frames
    are enough to see how the judge behaves, not to certify it: for ±0.15 you need 30 to 45 frames per severity and
    artifact, which `make_module07_images.sh` can generate cheaply by varying sources, quantisers, and bit depths
    (the labels come with the recipe). Here the false alarms are the bigger problem. The blocking judge flags all
    four banded frames, so as it stands it says "compression artifact", not "blocking". The banding judge flags two
    severely blocked frames. Its alarm on `blocking_severe_gradient.png` is arguably right, because heavy
    quantisation of a gradient also produces bands. Decide frame by frame whether the label or the judge is wrong
    (module 5's alignment step), then fix the label set or sharpen the criterion (for example, tell the blocking
    judge that smooth horizontal steps are banding, not blocks), and measure again on fresh frames.
