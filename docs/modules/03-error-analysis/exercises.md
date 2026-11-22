# Exercises

Try each exercise before opening its solution. Code solutions are tested in CI and run from the repo root.

## Exercise 1: Code a batch and compare with the reference

Take traces `m3t061` to `m3t080` (20 traces). Without looking at the reference, label them: pass or fail, a note,
the first upstream step, and modes from *your* taxonomy. Then compare with the reference. Where do you differ, and
is the difference in the verdict, the grouping, or only the name?

```bash
uv run mediadoctor-lab03 review m3t061 --traces runs/m3_traces.jsonl   # ... through m3t080
```

??? success "Solution"
    The reference fails 9 of the 20 and uses 7 modes on them. You can check this with:

    ```python
    # exercise-solution
    from evalkit.annotate import load_annotations, mode_counts
    from mediadoctor.lab03 import reference_labels_path

    ref = load_annotations(reference_labels_path())
    batch = [a for a in ref if 61 <= int(a.case_id[3:]) <= 80]
    failing = [a.case_id for a in batch if a.failed]
    print(failing)
    print(mode_counts(batch).most_common())
    assert len(failing) == 9
    assert mode_counts(batch)["skipped-investigation"] == 4
    ```

    This batch is unusual: *skipped-investigation* (4) and *fabricated-evidence* (3) dominate, while the top mode
    overall, *ignored-tool-output*, appears once. A 20-trace sample can rank modes very differently from the full set,
    which is why the lesson asks for at least 100.

    Typical differences, and what they mean:

    - **Verdict differences** on borderline answers such as `m3t073` (correct cause, next step "Look into the
      rendering code."). Decide whether a weak next step is a failure *for your users*; then write it into the
      definition so you decide the same way next time.
    - **Grouping differences**: many people merge *skipped-investigation* and *fabricated-evidence* when the agent
      both skipped the tools and cited them (`m3t068`, `m3t077`). The reference keeps them apart because the fixes
      differ (prompt vs runtime guard) and tags both.
    - **Name differences only** ("made-up-evidence" vs "fabricated-evidence"): harmless. `compare` shows them as
      a one-to-one mapping.

## Exercise 2: Find the first upstream failure

For each trace, name the first step that went wrong and say whether later problems follow from it:
`m3t019`, `m3t050`, `m3t088`, `m3t008`, `m3t023`.

??? success "Solution"
    | Trace | First upstream failure | What follows from it |
    |---|---|---|
    | `m3t019` | **retrieval** (step 5): query `'player crashes when reopened'` with `k=1` returned `audio-focus` | The log in step 2 already showed `BehindLiveWindowException`, but the answer follows the wrong document. A query using the exception name finds the right note, so this is a query-formulation miss. |
    | `m3t050` | **execute_tool codec_caps** (step 2): device `"Lumen L3"` does not exist | The answer then quotes the lumen-l3's decoder limits anyway: fabricated evidence, downstream of the bad argument. |
    | `m3t088` | **execute_tool logcat_grep** (step 2): log `live_resume.log` instead of `.txt` | The agent gave up on the log, found the right document, and still hedged. The retrieval was fine; the missing log evidence is what weakened the answer. |
    | `m3t008` | **chat:plan** (step 6): a second search with almost the same query | Steps 7 to 11 repeat it; the answer is right but the trace costs about 2.5 times a normal one. |
    | `m3t023` | **chat:answer** (step 5): reads `NO_MEMORY: max instances reached` as a Java heap problem | The tools were fine. Note the inconsistency: the next step is right (release codecs) while the cause is wrong, which a quick skim of the answer would miss. |

    ```python
    # exercise-solution
    from evalkit.annotate import load_annotations
    from mediadoctor.lab03 import reference_labels_path

    ref = {a.case_id: a for a in load_annotations(reference_labels_path())}
    expected = {
        "m3t019": "retrieval",
        "m3t050": "execute_tool codec_caps",
        "m3t088": "execute_tool logcat_grep",
        "m3t008": "chat:plan",
        "m3t023": "chat:answer",
    }
    for cid, step in expected.items():
        print(cid, ref[cid].first_upstream, ref[cid].modes)
        assert ref[cid].first_upstream == step
    ```

## Exercise 3: Turn one slice of a judge-type mode into a code check

*ignored-tool-output* is marked `detector = "judge"` because contradictions take many forms. But one slice is easy
to check with code: claims about where the `moov` box is. Write `check_box_order_claim(trace)`, which fails when the
*Likely cause* line contradicts the box order that a successful ffprobe call returned. Which traces does it flag?

??? success "Solution"
    ```python
    # exercise-solution
    import json

    from mediadoctor.lab03 import root_of, run_cases, traces_by_case


    def check_box_order_claim(trace):
        boxes = None
        for s in trace:
            a = s["attributes"]
            if a.get("gen_ai.tool.name") == "ffprobe" and s["status"]["code"] != "ERROR":
                result = json.loads(a["gen_ai.tool.call.result"])
                boxes = result.get("mp4_top_level_boxes")
        if not boxes or "moov" not in boxes or "mdat" not in boxes:
            return True  # nothing to contradict
        moov_last = boxes.index("moov") > boxes.index("mdat")
        answer = root_of(trace)["attributes"]["mediadoctor.answer"]
        cause = next((ln for ln in answer.splitlines() if ln.startswith("Likely cause:")), "").lower()
        if moov_last and "at the front" in cause:
            return False
        if not moov_last and "at the end" in cause:
            return False
        return True


    traces = traces_by_case(run_cases())
    flagged = sorted(cid for cid, t in traces.items() if not check_box_order_claim(t))
    print(flagged)
    assert flagged == ["m3t003", "m3t004"]
    ```

    It flags exactly the two box-order contradictions, with no false alarms on the other 98 traces. Notice the
    design choices: it looks only at the *Likely cause* line (correct answers say "move moov to the front" in the
    next step), and it passes traces where ffprobe failed, which other checks already cover.

    It catches 2 of the 11 *ignored-tool-output* traces. The rest (decoder profiles, Widevine level, decoder count,
    `NO_MEMORY`) would each need their own rule. Narrow code checks are cheap and precise, so write them where a
    slice is common; for the long tail, module 5 builds an LLM judge and measures it against your labels.

## Exercise 4: Change the priority rule

Rank the reference modes by `traces × severity ÷ effort`, with effort 1 for easy, 2 for medium, and 3 for hard. What
moves, and would you work from this list or the original one?

??? success "Solution"
    ```python
    # exercise-solution
    from evalkit.annotate import load_annotations, load_modes, mode_counts
    from mediadoctor.lab03 import reference_labels_path, reference_modes_path

    ref = load_annotations(reference_labels_path())
    modes = load_modes(reference_modes_path())
    effort = {"easy": 1, "medium": 2, "hard": 3}
    counts = mode_counts(ref)


    def score(m):
        return counts[m] * modes[m].severity / effort[modes[m].fixability]


    order = sorted(counts, key=lambda m: (-score(m), m))
    for m in order:
        print(f"{m:<24} {score(m):5.1f}")
    assert order[:2] == ["fabricated-evidence", "ignored-tool-output"]
    assert order.index("wrong-api-detail") == 4
    ```

    *fabricated-evidence* moves to first (severe and easy), *ignored-tool-output* drops to second, and the two
    medium-effort modes *wrong-api-detail* and *retrieval-miss* fall behind the easy *skipped-investigation* and
    *wrong-tool-args*.

    Both lists are defensible; they answer different questions. Count × severity says *what hurts users most*.
    Dividing by effort says *what to do this week*. A reasonable plan uses both: ship the easy fixes now (guard,
    tool, prompt), and start the medium-effort work on the top-hurting mode in parallel, since it needs a judge
    (module 5) before you can even measure progress. Effort estimates are guesses, so do not let a precise-looking
    score hide that.

## Exercise 5: Does review order change saturation?

Shuffle the reference labels into 5 different review orders (seeds 0 to 4). For each, find where the last new mode
appears and where *fabricated-evidence* is first seen. What does this say about stopping rules?

??? success "Solution"
    ```python
    # exercise-solution
    import random

    from evalkit.annotate import last_new_mode_at, load_annotations, saturation_curve
    from mediadoctor.lab03 import reference_labels_path

    ref = load_annotations(reference_labels_path())
    results = []
    for seed in range(5):
        order = ref[:]
        random.Random(seed).shuffle(order)
        last = last_new_mode_at(saturation_curve(order))
        first_fab = next(i for i, a in enumerate(order, 1) if "fabricated-evidence" in a.modes)
        results.append((seed, last, first_fab))
        print(f"seed {seed}: last new mode at {last:>3}, fabricated-evidence first at {first_fab:>3}")
    lasts = [r[1] for r in results]
    assert min(lasts) == 20 and max(lasts) == 59
    ```

    The last new mode appears anywhere from trace 20 to trace 59, depending only on order. With seed 4 you would
    see all nine modes in 20 traces; with seed 1 you would wait until 59. A rule like "stop after 10 traces with
    nothing new" would end some of these reviews long before saturation.

    Practical consequences: review in a **random** order (not by date or by topic, which clusters similar
    failures); use a long window (about 20 traces with nothing new) *and* a minimum (about 100); and make sure the
    sample covers every kind of question, because a mode that only occurs for one question type cannot appear until
    you read that type. Module 4 builds test sets with that coverage on purpose.
