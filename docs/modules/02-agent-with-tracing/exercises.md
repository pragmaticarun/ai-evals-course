# Exercises

Try each exercise before opening its solution. Code solutions are tested in CI and run from the repo root.

## Exercise 1: Read a trace for latency

Open the m2q04 trace (`uv run evalkit view runs/m2_traces.jsonl m2q04`). The agent requested `logcat_grep`,
`codec_caps`, and `search_kb` in its first response, then answered. Where does the 6.25 s go, how would the trace
look if the agent had called the tools one at a time, and what is the trade-off?

??? success "Solution"
    Almost all of it is the two model calls: 2.35 s for the first and 3.88 s for the second. The three tool spans
    take 2 to 10 ms each and start at the same offset, because the model returned three `tool_use` blocks in one
    response. Every recorded case works this way: each of the eight traces has exactly two `chat` spans.

    Calling the tools one at a time would add one model call per extra tool: a third and fourth `chat` span, each
    resending the growing conversation, which, judging by the recorded calls, means roughly 2 to 4 s and 1,000 to 1,500 input tokens more per step.
    Here the calls are independent (the decoder limit for the lumen-l3 does not depend on what the log says), so
    requesting them together costs nothing. The trade-off appears when they are not independent: calling tools
    speculatively wastes work when the first result would have made the second unnecessary. Measure it with the
    `step_budget` check and the latency column, not by eye.

## Exercise 2: Did the agent use the tools it needed?

Each case in `data/datasets/module02_cases.jsonl` lists `expected_tools`. Write `check_expected_tools(trace, case)`:
it passes only if every expected tool has at least one *successful* `execute_tool` span. Which cases fail?

??? success "Solution"
    ```python
    # exercise-solution
    import copy

    from evalkit.viewer import group_traces, root_of
    from mediadoctor.lab02 import load_cases, run_cases


    def check_expected_tools(trace, case):
        ok = {
            s["attributes"]["gen_ai.tool.name"]
            for s in trace
            if s["attributes"].get("gen_ai.operation.name") == "execute_tool"
            and s["status"]["code"] != "ERROR"
        }
        return set(case["expected_tools"]) <= ok


    cases = {c["id"]: c for c in load_cases()}
    traces = {
        root_of(t)["attributes"]["mediadoctor.case.id"]: t for t in group_traces(run_cases()).values()
    }
    failing = sorted(cid for cid, t in traces.items() if not check_expected_tools(t, cases[cid]))
    print(failing)
    assert failing == []

    # What the check would catch: the same m2q03 trace with its ffprobe call marked as failed.
    broken = copy.deepcopy(traces["m2q03"])
    for s in broken:
        if s["name"] == "execute_tool ffprobe":
            s["status"] = {"code": "ERROR", "message": "media file not found"}
    print(check_expected_tools(broken, cases["m2q03"]))
    assert not check_expected_tools(broken, cases["m2q03"])
    ```

    Output:

    ```text
    []
    False
    ```

    No case fails: in the recorded runs every expected tool was called with valid arguments and succeeded (m2q01,
    m2q03, m2q04, and m2q05 also called `search_kb`, which their cases do not list). The edited copy shows what the
    check is for: if m2q03's ffprobe call had failed, the case would fail even though its answer reads the same.
    This check overlaps with `evidence_is_real` but is not the same. `evidence_is_real` asks "did the answer claim
    evidence it lacked?", while this one asks "did the agent gather the evidence it should have?" An agent that skips ffprobe and *honestly* answers from background knowledge
    fails this check but passes the other.

## Exercise 3: Where does the money go?

Using the spans, compute each case's share of the total cost, and the input tokens of each model call in m2q08. Is
any question an outlier, and why do the input tokens grow?

??? success "Solution"
    ```python
    # exercise-solution
    from evalkit.viewer import group_traces, root_of, summarize_trace
    from mediadoctor.lab02 import run_cases

    spans = run_cases()
    rows = [summarize_trace(t) for t in group_traces(spans).values()]
    total = sum(r.cost_usd for r in rows)
    for r in sorted(rows, key=lambda r: -r.cost_usd):
        print(f"{r.case_id}  {r.cost_usd / total:5.1%}")

    m2q08 = next(
        t
        for t in group_traces(spans).values()
        if root_of(t)["attributes"]["mediadoctor.case.id"] == "m2q08"
    )
    calls = sorted(
        (s for s in m2q08 if s["attributes"].get("gen_ai.operation.name") == "chat"),
        key=lambda s: s["start_time_unix_nano"],
    )
    tokens = [s["attributes"]["gen_ai.usage.input_tokens"] for s in calls]
    print(tokens)
    assert tokens == sorted(tokens) and tokens[-1] > 2 * tokens[0]
    assert max(rows, key=lambda r: r.cost_usd).case_id == "m2q02"
    ```

    Output:

    ```text
    m2q02  14.2%
    m2q04  14.0%
    m2q06  13.1%
    m2q01  13.1%
    m2q05  12.0%
    m2q03  11.6%
    m2q08  11.6%
    m2q07  10.5%
    [620, 1310]
    ```

    There is no outlier: with two model calls per case, shares range from 10.5% to 14.2% (an even split would be
    12.5%), and the most expensive case, m2q02, simply has the most tokens in and out (2,118 and 292) after three
    tool calls. In m2q08 the input tokens more than double from the first call to
    the second, although the agent only added one search, because the second call resends the system prompt, the
    tool schemas, and the whole conversation so far, including the tool result. Cost per step therefore rises with
    each step, and total cost grows faster than linearly with the number of steps. On data where an agent loops (say
    four searches for an easy question), this same table is where the expensive question stands out. Prompt caching
    ([Anthropic docs](https://platform.claude.com/docs/en/build-with-claude/prompt-caching)) reduces the price of the
    repeated prefix; module 11 measures that.

## Exercise 4: Guard against fabricated evidence, but where?

In the recorded runs m2q03 asks ffprobe for the right file and cites a real result. Suppose a later run asks for
`late_moov.mp4` instead, the tool fails, and the answer still says "ffprobe shows ... [tool:ffprobe]". Propose one
fix in each layer: the tool, the prompt, and a runtime guard. Which would you ship first, and how would you show it
worked?

??? success "Solution"
    - **Tool:** accept near-miss names (for example, a unique case-insensitive suffix match, so `late_moov.mp4`
      resolves to `progressive_late_moov.mp4`), or keep rejecting them but return the closest match in the error.
      The error already lists valid names; a "did you mean" line makes recovery more likely.
    - **Prompt:** "If a tool returns an error, fix the arguments and retry once, or say the evidence is unavailable.
      Never cite a tool whose call failed." (The v1 prompt has a softer version of this.)
    - **Runtime guard:** run `check_evidence_is_real` on the trace before returning the answer. If it fails, either
      retry with a corrective message or strip the false citation and add a caveat.

    Ship the guard first: it is deterministic, cheap, and catches the whole class of failure, not just this file name.
    Then improve the tool, which removes the root cause for this case. Prove it the same way as in module 1: rerun all
    eight cases, check that `evidence_is_real` passes everywhere, and confirm nothing else regressed (per-case diff,
    plus the cost and step columns). Because the recorded runs already pass, also test the guard on a trace you
    break on purpose (mark the ffprobe span `ERROR`, as in exercise 2), so you know it fires.

## Exercise 5: Read OTLP

Convert the m2q03 trace to OTLP/JSON and find the `execute_tool ffprobe` span. What are its `kind` and
`status.code` numbers, and what do they mean?

??? success "Solution"
    ```python
    # exercise-solution
    from evalkit import to_otlp_json
    from mediadoctor.lab02 import run_cases

    body = to_otlp_json(run_cases(["m2q03"]))
    spans = body["resourceSpans"][0]["scopeSpans"][0]["spans"]
    tool = next(s for s in spans if s["name"] == "execute_tool ffprobe")
    print(tool["kind"], tool["status"])
    assert tool["kind"] == 1 and tool["status"]["code"] == 1
    ```

    Output:

    ```text
    1 {'code': 1, 'message': ''}
    ```

    `kind` 1 is `SPAN_KIND_INTERNAL` (work inside the process; model calls are 3, `CLIENT`, because they call a remote
    service). `status.code` 1 is `STATUS_CODE_OK` (0 is unset, 2 is `STATUS_CODE_ERROR`, which is what a failed tool
    call would carry). The numbers come from the
    [OTLP specification](https://opentelemetry.io/docs/specs/otlp/); OTLP/JSON also writes 64-bit integers such as
    timestamps and token counts as strings.
