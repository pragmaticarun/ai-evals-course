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

The lab uses 0.6. Measure how many queries survive at thresholds from 0.1 to 0.9, then look at the most similar
pairs: the ones a threshold would decide. Pick a threshold and write two sentences defending it to a sceptical
colleague. Then explain why `build_dataset` only compares queries with the
same `evidence` and `ambiguity` values.

??? success "Solution"
    ```python
    # exercise-solution
    from itertools import combinations

    from evalkit.synth import dedup, similarity
    from mediadoctor import lab04

    rows = lab04.generate_queries(lab04.make_tuples(lab04.load_default_space()))
    by_id = {r["tuple_id"]: r for r in rows}
    items = [(r["tuple_id"], r["query"]) for r in rows]


    def same_case(i):
        return tuple(by_id[i][k] for k in lab04.DEDUP_WITHIN)


    kept = {t: dedup(items, t, key=same_case) for t in (0.1, 0.15, 0.2, 0.3, 0.4, 0.6, 0.9)}
    for t, res in kept.items():
        print(f"threshold {t}: keep {len(res.kept)}")

    # The pairs a threshold could act on: the most similar queries within the same test case.
    pairs = sorted(
        (
            (similarity(qa, qb), a, b)
            for (a, qa), (b, qb) in combinations(items, 2)
            if same_case(a) == same_case(b)
        ),
        reverse=True,
    )
    print("\n--- the three most similar pairs ---")
    for s, a, b in pairs[:3]:
        print(f"{s:.2f} {a} {by_id[a]['persona']:<14} {by_id[a]['query'][:70]!r}")
        print(f"     {b} {by_id[b]['persona']:<14} {by_id[b]['query'][:70]!r}")

    assert [len(r.kept) for r in kept.values()] == [184, 195, 199, 200, 200, 200, 200]
    assert round(pairs[0][0], 2) == 0.20
    ```

    Output (first part):

    ```text
    threshold 0.1: keep 184
    threshold 0.15: keep 195
    threshold 0.2: keep 199
    threshold 0.3: keep 200
    threshold 0.4: keep 200
    threshold 0.6: keep 200
    threshold 0.9: keep 200
    ```

    On this dataset the threshold decides nothing between 0.3 and 0.9: the most similar pair of queries scores
    0.20, so 0.6 keeps all 200. The queries were written by Claude subagents, one call per tuple, and they share
    almost no word 3-grams. The top pairs show what "most similar" means here: `t158`/`t174` paste the same file
    name and the same "a third of a second" description but ask different things (diagnose against how-to);
    `t185`/`t193` state the same false premise in different words, once as a novice and once as an intermediate.
    These are the variations the dimensions exist to test, and a threshold low enough to drop them (0.15 drops 5,
    0.1 drops 16) would delete test cases, not duplicates.

    A defensible answer: *"Keep 0.6. Nothing here comes near it, so it costs nothing, and the pairs it would catch
    on a templated or copy-pasted set (the same sentence with a different greeting) are always duplicates; going
    below 0.3 would start removing queries whose only difference is the persona or expertise we want to test."*
    The check still earns its place: a writer that reuses templates, or a model that collapses two tuples into one
    text, produces pairs above 0.8, and the dropped list tells you which dimension value did not make it into the
    words. No threshold is perfect; pick the side whose errors cost less. Here a surviving near-duplicate costs one
    extra trace to read, while a wrongly dropped query loses a slice.

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
    assert cn["audio-focus"] == 2 and named[0] == 0 and untagged == 22
    ```

    The tagger finds the labelled topic in 86% of v1 queries: good enough to compare sets, not to label one query.
    (It misses novice typos such as "playbak", and vague references like "our trailer".) Always check an automatic
    tagger on labelled data before using it on unlabelled data; that is module 5's subject in miniature.

    Per 100 queries, v1 mentions every topic at least 7 times (audio focus 7.5, the lowest, partly because the
    tagger misses phrasings like "stop the music when another app plays audio"). Of the 50 naive queries, one
    mentions live streams and two each mention audio focus and DRM, against eight each for AV1 and codec limits.
    22 of the 50 match no topic at all; they are about things outside MediaDoctor's dimensions, such as HLS segment
    durations or tunneled playback. None names a file, device, or log, and none is written the way a novice writes:
    all 50 are capitalised, and 36% open with "how do". The naive set is not *wrong*; it is one slice (polite,
    expert, API-level, no evidence) repeated 50 times. An agent that
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
    print(f"same assignment either way: {grouped == naive}")

    # Nothing reaches 0.35. Lower the bar to see the closest pairs that do cross splits.
    close = sorted(leakage_pairs(items, naive, 0.15), key=lambda x: -x[2])
    print(f"{len(close)} cross-split pairs at similarity >= 0.15:")
    for a, b, s in close:
        print(f"  {s:.2f} [{naive[a]}] {by_tid[a]['question'][:60]!r}")
        print(f"       [{naive[b]}] {by_tid[b]['question'][:60]!r}")
    assert len(leakage_pairs(items, grouped, GROUP_THRESHOLD)) == 0 and grouped == naive
    assert len(close) == 3
    ```

    Output:

    ```text
    grouped      {'train': 120, 'dev': 42, 'test': 38}  leaking pairs: 0
    independent  {'train': 120, 'dev': 42, 'test': 38}  leaking pairs: 0
    same assignment either way: True
    3 cross-split pairs at similarity >= 0.15:
      0.20 [test] 'av_offset_300ms.mp4 the audio is ahead of the video by like '
           [train] 'our av_offset_300ms.mp4 the audio is ahead of the lips by li'
      0.16 [test] 'i read that faststart only matters for DASH and not progress'
           [dev] 'our progressive mp4 videos take forever to start. i read tha'
      0.15 [train] 'I think this is an audio focus problem since the live stream'
           [dev] 'live channel stops after the app comes back from background.'
    ```

    On v1 there is no leak to show. No pair of queries reaches the 0.35 grouping threshold, so grouping changes
    nothing: grouped and independent splitting give the same assignment and 0 leaking pairs, and no test query has
    a near-twin in train or dev. Lowering the bar to 0.15 finds three related pairs across splits; the closest
    (0.20) is a test query and a train query about the same clip, `av_offset_300ms.mp4`, described in the same
    words. That is not a rewording of the same test, but it is the kind of overlap that grows into one: on a set
    written from templates, or by a model that repeats itself, independent splitting puts dozens of near-copies on
    both sides of the line.

    How it misleads: suppose you add a few-shot example from train that teaches the agent to ask for the clip when
    the user says "our trailer". If the test set contains the twin of that example, the test score rises by more
    than the change deserves, and you conclude that the prompt generalises when it has partly memorised. With
    synthetic data the risk is higher than with real data, because templates and models reuse phrasing; v1 happens
    to be free of it, which you only know because you checked. Grouping by similarity before splitting, and
    checking with `leakage_pairs`, is cheap insurance. Use a lower threshold for
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
