# Quiz

Ten questions across the four architectures. Answer each, then expand to check.

**1. A RAG system's answers are often wrong. Why evaluate retrieval separately instead of just judging the answers?**

??? question "Answer"
    Because the fix depends on where it broke. If the answering passage never reached the model, no prompt change
    will help; if it did and the model ignored or embellished it, a better retriever will not help. Retrieval
    metrics on a labelled relevance set (recall@k, MRR, nDCG) are cheap, deterministic, and need no judge, so you
    can compare chunking and ranking choices quickly, then attribute each failed answer to retrieval or generation.

**2. Your generator reads the top 3 passages. Retriever A has MRR 0.85 and recall@3 0.71; retriever B has MRR 0.80
and recall@3 0.76. Which matters more here, and why might precision@3 be low for both?**

??? question "Answer"
    Recall@3 (or hit@3 on the answering passages): the generator sees all three passages, so the rank of the first
    relevant one inside the top 3 matters less than whether the needed passages are there at all. MRR matters more
    for a list people scan. Precision@3 is low when most queries have only one or two relevant passages: even a
    perfect top 3 then has precision 0.33 to 0.67. Low precision is a problem only if the irrelevant passages
    distract the generator, which the generation evals will show.

**3. Codec recall@5 went from 0.51 to 0.62 after a chunking change, on 14 codec queries. Can you report that the
change fixed codec retrieval?**

??? question "Answer"
    No. The paired bootstrap interval on those 14 queries is about [−0.04, +0.29]: it includes zero. Report the
    overall gain (+0.17 on 48 queries, interval excluding zero) and say the codec slice is too small to show a
    change. Then look at the codec misses: most are vocabulary gaps that chunking cannot fix, which is a better
    guide to the next change than the slice number.

**4. An answer is correct, but the fact it states is not in any retrieved passage. Does it pass a faithfulness
check? Should it?**

??? question "Answer"
    It fails, and it should. Faithfulness (groundedness) asks whether the answer is supported by the context, not
    whether it is true. An answer from the model's general knowledge is right by luck; the same behaviour produces
    confident wrong answers when the knowledge is missing or out of date, and nothing in the system can catch it.
    Track correctness separately if you need it, but keep faithfulness strict.

**5. An answer cites `[kb:mediacodec-errors@40]`, which was in the context. Is the citation correct?**

??? question "Answer"
    Not necessarily. "Valid" (the cited id was among the retrieved passages) is only the first check; the second
    is whether the cited passage is relevant to the question and supports the claim. In the worked example the
    citation was valid but pointed to a passage that did not answer the question. Both checks are code, given the
    relevance labels.

**6. Why score a conversation at the session level before the turn level?**

??? question "Answer"
    Because the session outcome is what the user experiences: did they get a correct diagnosis, or did the assistant
    give up? Turn-level checks (retention, needless questions, one question per turn) explain *why* a session went
    wrong and catch friction in sessions that still succeeded, but a session can pass every turn check and still
    fail the user. Some failures, like giving up too early, exist only at the session level.

**7. A simulated user in your harness sometimes answers questions it was not asked. Why does that matter, and what
do you do about it?**

??? question "Answer"
    It makes the agent look better than it is: the agent never has to ask for the missing fact, so clarification
    failures disappear from the results. (The opposite fault, a simulator that invents or contradicts facts, makes
    the agent look worse.) Check the simulator's turns with code (did it answer what was asked, did it add facts),
    report how many sessions had simulator faults, and exclude or fix them. Where you have real conversations,
    N−1 testing (replay real prefixes, evaluate the next turn) avoids the simulator.

**8. What does a transition-failure matrix show that a pass rate does not?**

??? question "Answer"
    Where runs break. For each failed run it records the last state that succeeded and the first that failed (route,
    handoff, a specific tool call, evidence, answer), and counts the pairs. Hot cells show which component to fix
    first, and upstream failures (routing, handoffs) are counted once instead of being blamed on everything after
    them. In the lab, a third of failures were one tool-argument mistake by one specialist.

**9. In a planner-and-specialists system, what is a handoff error, and how can you detect it with code?**

??? question "Answer"
    A handoff error is information lost or distorted at the boundary between agents: the planner's brief drops the
    file name, device, or log the user mentioned, so the specialist guesses (and its tool calls fail or inspect the
    wrong thing). Detect it by checking each brief against the entities in the user's message (every file, device,
    and log name must appear), and confirm with the downstream state (tool errors or missing evidence).

**10. Your vision judge flags 3 of 3 severe banding frames and 1 of 3 mild ones, with 1 false alarm on 10 other
frames. What do you report, and what do you do next?**

??? question "Answer"
    Report per severity, with intervals: severe 3/3 [0.44, 1.00], mild 1/3 [0.06, 0.79], false alarms 1/10. The
    judge is usable for gross artifacts and unproven for subtle ones; the sample is too small to say more. Next:
    generate more labelled frames per severity (about 30 to 45 for ±0.15), and review the false alarm, which may be a
    labelling gap (a heavily quantised gradient really does band) rather than a judge error.
