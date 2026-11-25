# Exercises

Try each exercise before opening its solution. Solutions are collapsed; click to expand.
Code solutions are tested in CI (`tests/test_docs_snippets.py`), so they run as written from the repo root.

## Exercise 1: Pick the evaluator

For each failure, choose **code check**, **model judge**, or **human review** as the *first* detector you would
build, and give a one-line reason.

1. The answer is not valid JSON when the caller asked for JSON.
2. The answer recommends an API that was removed in the device's Android version.
3. The answer cites `[kb:...]` ids that do not exist.
4. The "next step" is vague ("check your configuration").
5. Users say the assistant "sounds condescending".
6. The answer is over 120 words.
7. The answer contradicts the document it cites.
8. You have no idea yet what goes wrong for questions about DRM.
9. A tool call passes a file name outside `data/media/`.
10. The answer leaks the system prompt.

??? success "Solution"
    1. **Code**: parse it. 2. **Code** if you keep a table of API levels (a lookup beats a judge); otherwise a
    judge. 3. **Code**: set membership. 4. **Judge**: "actionable" is fuzzy, so validate it on labels.
    5. **Human** first, to find out what users mean, then maybe a judge. 6. **Code**. 7. **Judge** (a grounding
    check), validated against labels. 8. **Human**: this is discovery, not measurement, so read traces.
    9. **Code**: path validation, and also a guardrail (module 10). 10. **Code** for exact substrings of the
    prompt, plus a judge for paraphrases.

    The pattern: anything checkable by rule gets a rule. Judges cover fuzzy criteria. Humans own discovery
    and ground truth.

## Exercise 2: A stricter citation check

`cites_kb` only checks that cited ids *exist*. Write `cites_retrieved(case, output)`, which also requires every cited
id to be one of the documents the retriever actually returned for that question. Which v1 cases does it fail?

??? success "Solution"
    ```python
    # exercise-solution
    import re

    from mediadoctor.kb import load_kb
    from mediadoctor.lab01 import evaluate, load_cases

    KB = load_kb()


    def cites_retrieved(case, output):
        cited = re.findall(r"\[kb:([a-z0-9\-]+)\]", output)
        retrieved = {d.id for d in KB.search(case["query"], k=2)}
        return bool(cited) and set(cited) <= retrieved


    outputs = evaluate("v1")["outputs"]
    failing = [c["id"] for c in load_cases() if not cites_retrieved(c, outputs[c["id"]])]
    print(failing)
    assert failing == ["q11"]
    ```

    With the course fixtures it fails q11 (no citation). Every other v1 answer cites a document that was retrieved,
    so on this data the stricter check adds little. That is a useful finding: a check that never fires on
    real failures costs maintenance and gives nothing back. Keep it only if error analysis shows citation
    hallucination happening.

## Exercise 3: Can a regex catch an AV1 mistake?

q05 asks whether hardware AV1 decoding can be assumed on every Android 10+ phone. A classic wrong answer says yes,
that it is guaranteed or a requirement. Write `no_absolute_claims(case, output)` that fails answers containing
absolute phrases ("every device", "any device", "all devices", "guaranteed", "requirement"). Run it on v1. Then
answer: should this check gate CI?

??? success "Solution"
    ```python
    # exercise-solution
    import re

    from mediadoctor.lab01 import evaluate

    ABSOLUTES = re.compile(r"\b(every|any|all) devices?\b|\bguaranteed\b|\brequirement\b", re.I)


    def no_absolute_claims(case, output):
        return ABSOLUTES.search(output) is None


    outputs = evaluate("v1")["outputs"]
    flagged = sorted(cid for cid, out in outputs.items() if not no_absolute_claims({}, out))
    print(flagged)
    assert flagged == []
    assert not no_absolute_claims({}, "Hardware AV1 decoding is guaranteed on every device.")
    ```

    Output:

    ```text
    []
    ```

    It flags nothing on v1, and that is the right result here: q05 answers correctly (Android 10 "only guarantees a
    software AV1 decoder"; hardware support depends on the SoC), and "guarantees" is not one of the listed words.
    Note how close that was: had the regex matched `guarantee\w*`, it would have flagged the *correct* answer. On
    an answer that made the classic mistake ("hardware AV1 decoding is guaranteed on every device") it does fire, as
    the second assert shows. It should **not** gate CI on its own:

    - It is a proxy. Plenty of correct answers say "every device" ("check this on every device you support"),
      and plenty of wrong answers contain no absolute words at all.
    - What you actually want to know is "is this factually consistent with the knowledge base". That is a
      judge's job (module 5), validated against labels.

    A cheap proxy like this is fine as a *flag for human review*, which is a good use of a weak signal.

## Exercise 4: Root-cause q11

q11 fails `cites_kb`. Explain the root cause and propose two fixes, one in retrieval and one in the prompt. Which fix
should come first?

??? success "Solution"
    The question ("navigation prompts are drowned out by our video playback") shares almost no keywords with the
    audio-focus note, so the naive keyword retriever returned `av-sync` and `hdr-tone-mapping`. The model behaved
    well: it said the context did not cover the question. The failure is upstream.

    - **Retrieval fix**: add synonyms and terms ("ducking", "drowned out", "navigation") to the note, or move to
      embedding or hybrid retrieval (module 7), and measure recall@k on a retrieval set.
    - **Prompt fix**: allow `Sources: none` when the context does not cover the question, and treat that as a
      *correct abstention* in the check, not a failure.

    Retrieval first: it fixes the user's actual problem. The prompt fix makes the metric fairer, but on its own
    it leaves the user without an answer. Both matter, and they are different failure modes in your taxonomy.

## Exercise 5: Who decides?

Your v2 prompt makes answers about half as long (median 76.5 to 38 words), and users have asked for brevity. On the
20 cases the three checks see no difference (19 of 20 pass under both, nothing fixed, nothing broken). Write three
sentences: what the engineer should present, what the product owner should decide, and what experiment would
settle it.

??? success "Solution"
    The engineer presents the per-case diff (nothing fixed, nothing broken), says that 20 cases is a small sample
    and that the checks only cover format, citations and length, and shows the length distribution before and
    after with a few v1/v2 answers side by side. The product owner decides whether the shorter answers still carry
    what users need (a usable next step, the citation as a trust signal) and whether brevity is worth any loss of
    detail. The experiment is to run both prompts on a larger case set with the citation and format checks as hard
    gates, plus a validated judge (or a human review sample) for "the next step is actionable", since that is the
    property the brevity instruction is most likely to hurt.
