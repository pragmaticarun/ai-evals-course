# Exercises

Try each exercise before opening its solution. Code solutions are tested in CI and run from the repo root.

## Exercise 1: Read a trace for latency

Open the m2q04 trace (`uv run evalkit view runs/m2_traces.jsonl m2q04`). The agent called `logcat_grep`, waited for
another model call, then called `codec_caps`. How could the same evidence have been gathered faster, and what is the
trade-off?

??? success "Solution"
    The two tool calls are independent: the decoder limit for the lumen-l3 does not depend on what the log says. The
    model could have requested both in its first response (Claude can return several `tool_use` blocks at once, as
    in m2q01 and m2q07), which saves one model call: about 0.9 s and about 1,000 input tokens here.

    The trade-off: calling tools speculatively wastes work when the first result would have made the second
    unnecessary. A system prompt line such as "request independent tools in the same turn" usually helps. Measure it
    with the `step_budget` check and the latency column, not by eye.

## Exercise 2: Did the agent use the tools it needed?

Each case in `data/datasets/module02_cases.jsonl` lists `expected_tools`. Write `check_expected_tools(trace, case)`:
it passes only if every expected tool has at least one *successful* `execute_tool` span. Which cases fail?

??? success "Solution"
    ```python
    # exercise-solution
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
    assert failing == ["m2q03"]
    ```

    Only m2q03 fails: it never obtained a successful ffprobe result. This check overlaps with `evidence_is_real` but is
    not the same. `evidence_is_real` asks "did the answer claim evidence it lacked?", while this one asks "did the agent
    gather the evidence it should have?" An agent that skips ffprobe and *honestly* answers from background knowledge
    fails this check but passes the other.

## Exercise 3: Where does the money go?

Using the spans, compute each case's share of the total cost, and the input tokens of each model call in m2q08. Why
do the input tokens grow?

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
    assert tokens == sorted(tokens) and tokens[-1] > 4 * tokens[0]
    assert max(rows, key=lambda r: r.cost_usd).case_id == "m2q08"
    ```

    m2q08 takes about 30% of the cost. Input tokens grow from 590 to 2,494 because every call resends the system
    prompt, the tool schemas, and the whole conversation so far, including every tool result. Cost per step therefore
    rises with each step, and total cost grows faster than linearly with the number of steps. Prompt caching
    ([Anthropic docs](https://platform.claude.com/docs/en/build-with-claude/prompt-caching)) reduces the price of the
    repeated prefix; module 11 measures that.

## Exercise 4: Fix m2q03, but where?

Propose one fix in each layer: the tool, the prompt, and a runtime guard. Which would you ship first, and how would
you show it worked?

??? success "Solution"
    - **Tool:** accept near-miss names (for example, a unique case-insensitive suffix match, so `late_moov.mp4`
      resolves to `progressive_late_moov.mp4`), or keep rejecting them but return the closest match in the error.
      The error already lists valid names; a "did you mean" line makes recovery more likely.
    - **Prompt:** "If a tool returns an error, fix the arguments and retry once, or say the evidence is unavailable.
      Never cite a tool whose call failed." (The v1 prompt has a softer version of this, and the model ignored it.)
    - **Runtime guard:** run `check_evidence_is_real` on the trace before returning the answer. If it fails, either
      retry with a corrective message or strip the false citation and add a caveat.

    Ship the guard first: it is deterministic, cheap, and catches the whole class of failure, not just this file name.
    Then improve the tool, which removes the root cause for this case. Prove it the same way as in module 1: rerun all
    eight cases, check that `evidence_is_real` passes everywhere, and confirm nothing else regressed (per-case diff,
    plus the cost and step columns).

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
    assert tool["kind"] == 1 and tool["status"]["code"] == 2
    ```

    `kind` 1 is `SPAN_KIND_INTERNAL` (work inside the process; model calls are 3, `CLIENT`, because they call a remote
    service). `status.code` 2 is `STATUS_CODE_ERROR` (0 is unset, 1 is OK). The numbers come from the
    [OTLP specification](https://opentelemetry.io/docs/specs/otlp/); OTLP/JSON also writes 64-bit integers such as
    timestamps and token counts as strings.
