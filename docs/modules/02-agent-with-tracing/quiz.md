# Quiz

Eight questions. Answer each, then expand to check.

**1. Name the four kinds of span MediaDoctor emits and what each one represents.**

??? question "Answer"
    `invoke_agent` (one whole run), `chat` (one model call), `execute_tool` (one tool call), and `retrieval` (one
    knowledge-base search, nested inside the `search_kb` tool span).

**2. Why does a tool-using agent's input token count grow with each step?**

??? question "Answer"
    The Messages API is stateless: every call resends the system prompt, the tool schemas, and the whole conversation,
    including all previous tool results.

**3. An answer is correct and cites `[tool:ffprobe]`, but the trace shows the ffprobe call failed. Why is it still
counted as a failure?**

??? question "Answer"
    It cites ffprobe evidence that does not exist: the tool call failed. Being right by luck or prior knowledge does not
    hold up: the same behaviour on a different file produces a confident wrong answer with a fake citation.

**4. Why must tools be deterministic for replay mode to work?**

??? question "Answer"
    Tool output goes into the next model request, and the request's hash is the fixture key. A tool whose output changes
    (a different ffprobe version, a timestamp, a random order) changes the key, and replay finds no fixture.

**5. Why do course-specific attributes use the `mediadoctor.*` and `evalkit.*` prefixes instead of `gen_ai.*`?**

??? question "Answer"
    `gen_ai.*` is reserved for names defined by the OpenTelemetry conventions. Inventing names there risks clashing with
    future official attributes and confuses backends that interpret them.

**6. In replay mode, where do the durations of `chat` spans and `execute_tool` spans come from?**

??? question "Answer"
    `chat` durations come from the latency stored with each fixture; tool durations come from fixed simulated values. A
    virtual clock advances by those amounts, so replayed traces are identical on every run.

**7. Give one failure that a check over the final answer cannot catch but a check over the trace can.**

??? question "Answer"
    Any of: citing a tool whose call failed; repeated retrievals returning the same documents; too many model calls;
    calling a tool with arguments outside its allowed set; never calling a tool the question required.

**8. What should you decide before recording tool arguments and results in production traces?**

??? question "Answer"
    What to redact. Traces can contain user data and secrets; the GenAI conventions treat message content and tool
    arguments and results as opt-in for that reason.
