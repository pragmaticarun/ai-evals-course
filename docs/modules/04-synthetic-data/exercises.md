# Exercises

Try each exercise before opening its solution. Code solutions are tested in CI and run from the repo root.

## Exercise 1: Add a dimension and show how coverage changes

Module 3's live-stream failure happened after the app came back from the background. Add a dimension `app_state`
with values `foreground`, `background`, and `picture-in-picture`, and one rule you can justify. Then answer:

1. How do the number of valid tuples, feasible value pairs, and pairwise tuples change?
2. Treat every v1 query as `foreground` (none of them says otherwise). How many of the new feasible pairs does v1
   cover, and how many tuples would complete it?
3. Is `app_state` worth adding? What would make you say no?

??? success "Solution"
    ```python
    # exercise-solution
    from evalkit.synth import (
        Dimension,
        Rule,
        Space,
        feasible_pairs,
        full_product,
        pair_coverage,
        pairwise_tuples,
    )
    from mediadoctor.lab04 import load_dataset, load_default_space

    space = load_default_space()
    app_state = Dimension(
        "app_state",
        ("foreground", "background", "picture-in-picture"),
        "Where the app was when the problem happened.",
    )
    rule = Rule(
        when={"app_state": ("background",)},
        forbid={"topic": ("hdr-colour", "av1-playback")},
        reason="nothing is on screen to judge colour or frame drops",
    )
    bigger = Space(space.dimensions + [app_state], space.rules + [rule])

    print("valid tuples:", len(full_product(space)), "->", len(full_product(bigger)))
    print("feasible pairs:", len(feasible_pairs(space)), "->", len(feasible_pairs(bigger)))
    print(
        "pairwise tuples:",
        len(pairwise_tuples(space, seed=4)),
        "->",
        len(pairwise_tuples(bigger, seed=4)),
    )

    # v1 never asked where the app was; treat every v1 query as foreground.
    v1 = [{**{k: r[k] for k in space.names}, "app_state": "foreground"} for r in load_dataset()]
    covered, feasible = pair_coverage(v1, bigger)
    fill = pairwise_tuples(bigger, seed=4, start=v1)
    print(f"v1 covers {covered}/{feasible} pairs; {len(fill)} new tuples complete it")
    assert (covered, feasible) == (268, 317)
    ```

    Output:

    ```text
    valid tuples: 1342 -> 3410
    feasible pairs: 242 -> 317
    pairwise tuples: 34 -> 37
    v1 covers 268/317 pairs; 15 new tuples complete it
    ```

    The full product grows 2.5 times, but pairwise coverage grows by only 3 tuples: a new dimension with three
    values adds pairs, not a multiple of the old set. That is why pairwise is the right way to think about the cost of
    a dimension. The 49 uncovered pairs are every `background` and `picture-in-picture` combination: v1 simply
    cannot say anything about them, and its coverage matrix gives no hint, because the dimension did not exist.

    Is it worth adding? Yes if you believe the agent's behaviour changes with it. Here it plausibly does (resume
    after background is a known failure, and picture-in-picture changes surfaces and decoders). Say no if you cannot
    write a different query for each value, or if no failure hypothesis depends on it: a dimension that changes
    nothing costs queries and review time for no information.

    The rule is a judgement call. "Nothing is on screen in the background" is true for colour and frame drops, but
    audio still plays, and some decoders keep running; a stricter rule (forbid only `hdr-colour`) is defensible too.
    Writing the reason down is what makes the choice reviewable.

## Exercise 2: Choose a near-duplicate threshold, and justify it

The lab uses 0.6. Measure how many queries survive at thresholds from 0.4 to 0.9, then look at the pairs that the
threshold actually decides: those between 0.5 and 0.6, and between 0.6 and 0.7. Pick a threshold and write two
sentences defending it to a sceptical colleague. Then explain why `build_dataset` only compares queries with the
same `evidence` and `ambiguity` values.

??? success "Solution"
    ```python
    # exercise-solution
    from evalkit.synth import dedup
    from mediadoctor import lab04

    rows = lab04.generate_queries(lab04.make_tuples(lab04.load_default_space()))
    by_id = {r["tuple_id"]: r for r in rows}
    items = [(r["tuple_id"], r["query"]) for r in rows]


    def same_case(i):
        return tuple(by_id[i][k] for k in lab04.DEDUP_WITHIN)


    kept = {t: dedup(items, t, key=same_case) for t in (0.4, 0.5, 0.6, 0.7, 0.8, 0.9)}
    for t, res in kept.items():
        print(f"threshold {t}: keep {len(res.kept)}")


    def band(lo, hi):
        """Pairs dropped at `lo` but kept at `hi`: the decisions the threshold actually makes."""
        keep_hi = set(kept[hi].kept)
        return [(a, b, s) for a, b, s in kept[lo].dropped if a in keep_hi]


    for lo, hi in ((0.5, 0.6), (0.6, 0.7)):
        print(f"\n--- similarity in [{lo}, {hi}) ---")
        for a, b, s in band(lo, hi):
            print(f"{s:.2f} {a} {by_id[a]['persona']:<14} {by_id[a]['query'][:70]!r}")
            print(f"     {b} {by_id[b]['persona']:<14} {by_id[b]['query'][:70]!r}")

    assert [len(r.kept) for r in kept.values()] == [159, 173, 182, 188, 190, 197]
    ```

    Kept: 159, 173, 182, 188, 190, 197 at 0.4 to 0.9. Above 0.8 the dropped pairs differ by one opener ("Hey,",
    "QA question:") and nothing else: always duplicates. Between 0.6 and 0.7 most pairs still share the whole core
    sentence and differ by a short frame or a "thx", such as `t157` ("in our app, what makes a progressive mp4 slow
    to start thx") against `t085` ("What makes a progressive MP4 slow to start?"). Between 0.5 and 0.6 the
    differences start to carry meaning: a bug-ticket template against a plain question (`t156`/`t116`), or a novice
    rewrite with typos against a clean one (`t114`/`t074`). Those are exactly the persona and expertise variations
    the dimensions exist to test.

    A defensible answer: *"0.6 removes every pair that differs only in framing words, and keeps pairs where the
    persona or expertise visibly changed the text; at 0.5 we would lose 9 queries whose only difference is the
    thing we want to test."* The bands overlap (`t154`/`t016` at 0.61 differ by a bug-ticket frame, like the 0.55
    pair that survives), so no threshold is perfect; say so, and pick the side whose errors cost less. Here a
    surviving near-duplicate costs one extra trace to read, while a wrongly dropped query loses a slice.

    Why compare only within the same `evidence` and `ambiguity`: a query that pastes a log and the same query that
    says "I can grab logs if needed" can be 70% similar in words, yet they test different behaviour (reading
    evidence versus asking for it). Text similarity cannot see that; the tuple can. Use the tuple to decide which
    queries are *allowed* to be duplicates, and text similarity to decide which ones *are*.

## Exercise 3: What did the naive prompt miss?

Compare the 50 naive queries with dataset v1, topic by topic, using the keyword tagger in `lab04`. Before trusting
the tagger on the naive set, measure how often it finds the right topic where you know the answer. Then count the
queries that give the agent something to inspect.

??? success "Solution"
    ```python
    # exercise-solution
    from mediadoctor.lab04 import NAMES, load_dataset, naive_queries, tag_topics, topic_coverage

    naive = naive_queries()
    v1 = load_dataset()

    # 1. How good is the tagger? Check it where we know the answer: on v1, whose topics are labelled.
    recall = sum(r["topic"] in tag_topics(r["question"]) for r in v1) / len(v1)
    print(f"tagger finds the labelled topic in {recall:.0%} of v1 queries")

    # 2. Topic coverage, per 100 queries so the sets are comparable.
    cn, cv = topic_coverage(naive), topic_coverage([r["question"] for r in v1])
    for topic in sorted(set(cv) | set(cn)):
        print(
            f"{topic:<16} naive {100 * cn[topic] / len(naive):5.1f}   v1 {100 * cv[topic] / len(v1):5.1f}"
        )

    # 3. Things the agent must actually inspect.
    untagged = sum(not tag_topics(q) for q in naive)
    named = (
        sum(bool(NAMES.search(q)) for q in naive),
        sum(bool(NAMES.search(r["question"])) for r in v1),
    )
    lower = sum(q == q.lower() for q in naive)
    print(
        f"naive: {untagged}/50 match no topic, {named[0]} name a file/device/log, {lower} written in lower case"
    )
    print(f"v1: {named[1]}/{len(v1)} name a file, device, or paste a log")
    assert cn["audio-focus"] == 0 and named[0] == 0 and untagged == 33
    ```

    The tagger finds the labelled topic in 86% of v1 queries: good enough to compare sets, not to label one query.
    (It misses novice typos such as "playbak", and vague references like "our trailer".) Always check an automatic
    tagger on labelled data before using it on unlabelled data; that is module 5's subject in miniature.

    Per 100 queries, v1 mentions every topic at least 11 times. Of the 50 naive queries, none mentions audio
    focus, and one each mentions live streams, A/V sync, and DRM. 33 of the 50 naive queries match no topic at all ("Why is my video not
    playing on Android?"). None names a file, device, or log, and none is written the way a novice writes. The naive
    set is not *wrong*; it is one slice (polite, expert-ish, generic, no evidence) repeated 50 times. An agent that
    answers in generalities would pass it, and that is the failure module 3 found most often.

## Exercise 4: Show the leak

Split v1 again, but assign each query independently (no grouping), and count near-duplicate pairs that cross
splits. How many test queries have a near-twin in train or dev? Describe a concrete way this would mislead you in
a later module, when you tune MediaDoctor's prompt on train and dev.

??? success "Solution"
    ```python
    # exercise-solution
    from collections import Counter

    from evalkit.synth import assign_splits, leakage_pairs
    from mediadoctor.lab04 import GROUP_THRESHOLD, load_dataset

    v1 = load_dataset()
    items = [(r["tuple_id"], r["question"]) for r in v1]
    by_tid = {r["tuple_id"]: r for r in v1}

    grouped = assign_splits(items, salt="mediadoctor-v1", group_threshold=GROUP_THRESHOLD)
    naive = assign_splits(items, salt="mediadoctor-v1", group_threshold=1.01)  # no grouping
    for name, splits in (("grouped", grouped), ("independent", naive)):
        leaks = leakage_pairs(items, splits, GROUP_THRESHOLD)
        print(f"{name:<12} {dict(Counter(splits.values()))}  leaking pairs: {len(leaks)}")

    leaks = leakage_pairs(items, naive, GROUP_THRESHOLD)
    test_side = {a if naive[a] == "test" else b for a, b, _ in leaks if "test" in (naive[a], naive[b])}
    print(f"{len(test_side)} test queries have a near-twin in train or dev, e.g.:")
    a, b, s = max(leaks, key=lambda x: x[2])
    print(f"  {s:.2f} [{naive[a]}] {by_tid[a]['question'][:70]!r}")
    print(f"       [{naive[b]}] {by_tid[b]['question'][:70]!r}")
    assert len(leakage_pairs(items, grouped, GROUP_THRESHOLD)) == 0 and len(leaks) == 46
    ```

    Grouped splitting leaves 0 similar pairs across splits; independent splitting leaves 46, and 16 test queries
    have a near-twin outside test. The closest pair (0.78) is the same question with and without the file name.

    How it misleads: suppose you add a few-shot example from train that teaches the agent to ask for the clip when
    the user says "our trailer". The test set contains the twin of that example, so the test score rises by more
    than the change deserves, and you conclude that the prompt generalises when it has partly memorised. With
    synthetic data the risk is higher than with real data, because templates and models reuse phrasing. Grouping
    by similarity before splitting, and checking with `leakage_pairs`, is cheap insurance. Use a lower threshold for
    grouping (0.35) than for dedup (0.6): dedup removes queries that are the same test; grouping keeps related tests
    together.

## Exercise 5: Seed the next version with real queries

The ten beta queries in `data/synth/beta_queries.jsonl` stand in for your first real traffic. Which value pairs do
they cover, which dimension pairs are most under-covered, and how many generated tuples does pairwise need on top of
them? What would you change in the dimensions file after seeing that they never use `goal=check` or
`ambiguity=false-premise`?

??? success "Solution"
    ```python
    # exercise-solution
    from evalkit.synth import feasible_pairs, pair_coverage, pairs_of, pairwise_tuples
    from mediadoctor.lab04 import SEED, load_default_space, make_tuples
    from mediadoctor.synth_spec import style_examples

    space = load_default_space()
    beta = [{k: e[k] for k in space.names} for e in style_examples()]

    covered = set().union(*(pairs_of(t, space.names) for t in beta))
    missing = feasible_pairs(space) - covered
    by_dims = {}
    for (d1, v1), (d2, v2) in missing:
        by_dims.setdefault((d1, d2), []).append(f"{v1}+{v2}")
    print(f"beta covers {len(covered)}/{len(feasible_pairs(space))} pairs; missing by dimension pair:")
    for dims, vals in sorted(by_dims.items(), key=lambda kv: -len(kv[1]))[:5]:
        print(f"  {dims[0]} x {dims[1]}: {len(vals)}")

    fill = pairwise_tuples(space, seed=SEED, start=beta)
    print(f"seeded: {len(fill)} generated tuples, total {len(beta) + len(fill)}")
    print(f"unseeded pairwise: {len(pairwise_tuples(space, seed=SEED))} tuples")
    assert pair_coverage(beta + fill, space)[0] == len(feasible_pairs(space))
    ```

    Ten real queries cover 106 of 242 pairs. The biggest gaps are persona × topic (22 pairs) and topic × ambiguity
    and topic × expertise (14 each): real traffic arrives unevenly by topic, so cross-topic pairs are the last to
    fill. Seeded pairwise needs only 25 generated tuples (35 in total), against 34 tuples for the unseeded version:
    the real queries do most of the work and keep their real phrasing.

    On the missing values, do not react to ten queries by deleting values. Ask which explanation fits:

    - **Users do not ask this.** If after a few hundred real queries nobody asks a yes/no compatibility question,
      `goal=check` is a hypothesis that failed; keep a few synthetic ones for safety and stop spending budget there.
    - **Users ask, but not in this group.** Beta users are often developers on your own team, who rarely hold false
      beliefs about your devices. Customers relayed through support do. Keep `false-premise`, and check the
      support queue before deciding.
    - **Your values are wrong.** Real queries may contain a variation you did not list: a screen recording instead of
      a log, or two problems in one message. Add values for what you actually see.

    The v2 process is: real queries first, generated tuples only for the gaps, a stratified fill for small slices,
    and a manifest that records how many of each.
