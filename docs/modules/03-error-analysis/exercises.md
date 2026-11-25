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
    The reference fails 1 of the 20 (`m3t072`) and uses 1 mode on it. You can check this with:

    ```python
    # exercise-solution
    from evalkit.annotate import load_annotations, mode_counts
    from mediadoctor.lab03 import reference_labels_path

    ref = load_annotations(reference_labels_path())
    batch = [a for a in ref if 61 <= int(a.case_id[3:]) <= 80]
    failing = [a.case_id for a in batch if a.failed]
    print(failing)
    print(mode_counts(batch).most_common())
    assert failing == ["m3t072"]
    assert mode_counts(batch) == {"fabricated-evidence": 1}
    ```

    Output:

    ```text
    ['m3t072']
    [('fabricated-evidence', 1)]
    ```

    With 3 failures in 100 traces, a 20-trace batch holds 0 or 1 failures most of the time; this one holds 1. A
    small sample says almost nothing about which modes exist or how they rank, which is why the lesson asks for at
    least 100.

    Typical differences, and what they mean:

    - **Verdict differences** on `m3t072`: the cause and the suggestion to check `getVideoCapabilities()` are right,
      and the unsupported part (that the lumen-l3 does H.264/HEVC hardware decode up to 1080p60) sits in the middle
      of the next step. Many reviewers pass it on a first read. Decide whether an unsupported capability claim is a
      failure *for your users* (an engineer might ship a 1080p60 HEVC rendition on that basis); then write it into
      the definition so you decide the same way next time.
    - **Verdict differences** on `m3t080`: its next-step label reads `Next step (standard Media3 recovery, not shown
      in the log):`. The `format` signal flags it; the reference passes it, since the answer is right and the
      label is honest about where the advice comes from. Either call is defensible if it is written down.
    - **Grouping or name differences** ("made-up-evidence" or "unsupported claim" vs "fabricated-evidence"):
      harmless. `compare` shows them as a one-to-one mapping.

## Exercise 2: Find the first upstream failure

For each trace, decide pass or fail; on a fail, name the first step that went wrong and say which earlier step
could have supplied the missing evidence: `m3t010`, `m3t072`, `m3t088`, `m3t080`.

??? success "Solution"
    | Trace | First upstream failure | What follows from it |
    |---|---|---|
    | `m3t010` | **chat:answer** (step 4): adds that the lumen-l3 has only a software AV1 decoder capped at 1080p30 | ffprobe and `codec_caps` for the atlas-a1 (steps 2 and 3) are fine and the shipping advice is right. No step queried the lumen-l3; a `codec_caps` call for it would have grounded the claim, or the answer could have left the device out. |
    | `m3t072` | **chat:answer** (step 4): the next step says the lumen-l3 does H.264/HEVC hardware decode up to 1080p60 | Step 3 called `codec_caps` for `video/av01` only. The diagnosis is grounded; the alternative it recommends is not. A second `codec_caps` call (`video/avc` or `video/hevc`) would have checked it. |
    | `m3t088` | **chat:answer** (step 5): states the pause time 09:15:02 and "roughly 11 minutes in the background" | The grep in step 2 did not match the `onPause` line. The tool call itself was valid, so this is not a tool error; a pattern that included `background` or `onPause` would have returned the line. |
    | `m3t080` | none: **pass** | The same scenario and almost the same sentence as `m3t088`, but this grep pattern includes `background`, so line L1 (`onPause ... 09:15:02`) is in the tool output and the claim is grounded. |

    All three failures start at the final answer, with good earlier steps; none compounds from a tool or retrieval
    error. `m3t088` against `m3t080` is the useful pair: the same answer text is a failure in one trace and a pass in
    the other, and only the tool output tells them apart.

    ```python
    # exercise-solution
    from evalkit.annotate import load_annotations
    from mediadoctor.lab03 import reference_labels_path

    ref = {a.case_id: a for a in load_annotations(reference_labels_path())}
    expected = {
        "m3t010": "chat:answer",
        "m3t072": "chat:answer",
        "m3t088": "chat:answer",
        "m3t080": "",  # a pass has no first upstream failure
    }
    for cid, step in expected.items():
        print(cid, ref[cid].verdict, repr(ref[cid].first_upstream), ref[cid].modes)
        assert ref[cid].first_upstream == step
    assert ref["m3t080"].verdict == "pass"
    ```

    Output:

    ```text
    m3t010 fail 'chat:answer' ['fabricated-evidence']
    m3t072 fail 'chat:answer' ['fabricated-evidence']
    m3t088 fail 'chat:answer' ['fabricated-evidence']
    m3t080 pass '' []
    ```

## Exercise 3: Turn one slice of a judge-type mode into a code check

*ignored-tool-output* is marked `detector = "judge"` in the reference definitions because contradictions take many
forms. But one slice looks easy to check with code: claims about where the `moov` box is. Write
`check_box_order_claim(trace)`, which fails when the *Likely cause* line contradicts the box order that a successful
ffprobe call returned. Which traces does it flag, and are they real failures?

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
    assert flagged == ["m3t084"]
    ```

    Output:

    ```text
    ['m3t084']
    ```

    It flags one trace, and that trace is a **false alarm**. In `m3t084` ffprobe shows `ftyp, moov, free, mdat`
    (moov at the front), and the answer says so correctly, then adds that *the usual "moov at the end" cause does
    not apply*. The phrase match sees "at the end" and fires. The reference passes `m3t084`, and no trace in this set
    contradicts its box order, so the check has 0 true positives and 1 false positive here.

    Two lessons. Phrase rules are brittle once answers explain what is *not* the cause, which good answers do; a
    rule like this needs checking against your labels before you trust it, exactly as module 5 does for judges.
    And the design choices still matter: looking only at the *Likely cause* line avoids firing on "move moov to the
    front" in the next step, and passing traces where ffprobe failed leaves those to other checks. On a set where
    the agent does contradict box order, the same rule would catch that slice cheaply; the long tail of other
    contradictions (decoder profiles, Widevine level) would each need their own rule or a judge.

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
    assert order == ["fabricated-evidence"] and score("fabricated-evidence") == 9.0
    ```

    Output:

    ```text
    fabricated-evidence        9.0
    ```

    Nothing moves: on the current labels there is one mode, so any rule ranks it first. The score is unchanged too
    (3 traces × severity 3 ÷ effort 1), because the reference rates the mode easy. That rating is worth questioning:
    the easy fix is a guard against citing tools that failed or never ran, and none of these three traces does that.
    If you rate *this* form medium, the score halves to 4.5 but the order still cannot change. The rule starts to
    matter when several modes compete, as they usually do on a first pass over a less reliable agent.

    Both rules are defensible; they answer different questions. Count × severity says *what hurts users most*.
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
    assert min(lasts) == 6 and max(lasts) == 19
    assert all(last == first_fab for _, last, first_fab in results)  # one mode: last new = first seen
    ```

    Output:

    ```text
    seed 0: last new mode at  18, fabricated-evidence first at  18
    seed 1: last new mode at   8, fabricated-evidence first at   8
    seed 2: last new mode at   6, fabricated-evidence first at   6
    seed 3: last new mode at  19, fabricated-evidence first at  19
    seed 4: last new mode at  13, fabricated-evidence first at  13
    ```

    With a single mode, the last new mode is simply the first failure, and it appears anywhere from trace 6 to
    trace 19 depending only on order. A rule like "stop after 10 traces with nothing new" would end the reviews for
    seeds 0, 3, and 4 at trace 10 with no failure found at all. Seeds 1 and 2 would stop at traces 18 and 16, with
    2 and 1 of the 3 failures still unread. A mode that occurs in only one trace could appear anywhere from 1 to
    100.

    Practical consequences: review in a **random** order (not by date or by topic, which clusters similar
    failures); use a long window (about 20 traces with nothing new) *and* a minimum (about 100); and make sure the
    sample covers every kind of question, because a mode that only occurs for one question type cannot appear until
    you read that type. Module 4 builds test sets with that coverage on purpose.
