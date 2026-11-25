# Quiz

Ten questions. Answer each, then expand to check.

**1. What is the difference between open coding and axial coding?**

??? question "Answer"
    Open coding is writing free-text notes about what went wrong in each trace, without predefined categories. Axial
    coding comes after: grouping those notes into a small set of named failure modes with definitions.

**2. Why not start from a standard list of failure categories such as "hallucination" or "helpfulness"?**

??? question "Answer"
    Generic categories may not match your system's real problems and are too broad to act on. "Hallucination" would
    cover several different failures (contradicting a tool, citing a failed tool, a wrong API level, adding one
    detail no tool returned to a correct answer) that have different fixes and need different detectors. In this
    module's traces the only failure was the last kind, which a citation check cannot see. Categories should come
    from your traces.

**3. A trace's tool call fails, the agent retries with the right argument, and the answer is correct. Pass or fail?**

??? question "Answer"
    Pass. A tool error is not a failure if the agent recovers. (You might still note it: frequent recoveries cost time
    and tokens, and suggest the tool should accept near-miss names.)

**4. In a trace where a wrong file name leads to a failed ffprobe call and then to an answer that cites ffprobe,
what is the first upstream failure, and which modes apply?**

??? question "Answer"
    The first upstream failure is the tool call with the wrong argument (`execute_tool ffprobe`). Two modes apply:
    wrong-tool-args and fabricated-evidence. Record the first failure, and tag both modes.

**5. A retrieval returned the wrong documents. What single question tells you whether to fix the prompt or the
retriever?**

??? question "Answer"
    Would a better query have found the right document? If yes, it is query formulation (the model's step: prompt or
    query rewriting). If no, it is the retriever or the knowledge base (ranking, coverage, chunking).

**6. Mode A affects 12 traces with severity 1. Mode B affects 5 traces with severity 3. Using traces × severity,
which comes first, and what else might change the order?**

??? question "Answer"
    B (priority 15) before A (12). Fixability can change the plan: if A is a five-minute fix and B needs weeks, do A
    now while starting on B. Also consider how many users ask the kinds of question where B occurs.

**7. What is theoretical saturation in error analysis, and why is "10 traces without a new mode" a weak stopping
rule?**

??? question "Answer"
    Saturation is the point where reading more traces stops revealing new failure modes or changing definitions. A
    short window is weak because rare, severe modes appear late: in the module's set the only mode first appears at
    trace 10, so a reviewer who stopped at trace 9 would have seen no failure at all, and in a shuffled order it
    first appears anywhere from trace 6 to 19. When failures are rare, a flat curve mostly means "rare", not
    "complete". Use a minimum (about 100) plus a longer window (about 20).

**8. Who should own the labels and the definitions, and why one person?**

??? question "Answer"
    A domain expert who knows what a good answer looks like for your users (a "benevolent dictator"). One owner
    keeps verdicts and definitions consistent; others can contribute and challenge, but one person decides.

**9. The automatic signals flagged 1 of 100 traces. Why not just label that one and skip the rest?**

??? question "Answer"
    None of the 3 failing traces had a signal: each is a well-formed answer whose citations are real, with one
    detail that no tool returned. And the one flagged trace (a format slip) is a pass. Signals help you choose what
    to read first; they cannot replace reading.

**10. Your Pareto chart is flat: the top three modes cover 45% of failures. What does that tell you, and how does it
change prioritisation?**

??? question "Answer"
    There are many separate problems and none dominates, which is common for a young system. Frequency alone will not
    pick a winner, so severity and fixability decide: fix severe and easy modes first, and plan the severe but harder
    ones.
