# Quiz

Eight questions on experiment design, and on measuring cost and latency. Answer each, then expand to check.

**1. Configuration A costs $0.0020 per task and succeeds on 60% of tasks. Configuration B costs $0.0025 per task and
succeeds on 90%. Which is cheaper, and by what measure?**

??? question "Answer"
    B, per successful task: $0.0025 / 0.9 = $0.0028 against $0.0020 / 0.6 = $0.0033, so B is about 17% cheaper per
    success although it costs 25% more per task, and it fails a quarter as often. A only looks cheaper per call or
    per task. Cost per successful task is the headline because the user pays (in time, retries, and support) for
    the failures too; if a failure has a cost of its own (a wrong diagnosis someone acts on), B wins by more.

**2. A teammate changed the system prompt and switched from Sonnet to Haiku in the same pull request. Success fell
from 85% to 78%, and cost fell 90%. What can you conclude, and what would you ask for?**

??? question "Answer"
    Only that the combination is worse and cheaper. You cannot say whether the prompt, the model, or their
    interaction caused the drop, so you cannot keep the good part. Ask for the ablation: the new prompt on Sonnet,
    and the old prompt on Haiku, each against the current release on the same queries, with a decision rule written
    down first (non-inferiority with a margin for the model switch, since its purpose is saving money).

**3. Why does the lab compare configurations on the same queries with a paired test, and what do the discordant
counts tell you that the difference does not?**

??? question "Answer"
    Most queries come out the same under both configurations; they carry no information about the difference, but
    in an unpaired comparison their variation is noise. Pairing removes it, so the same number of queries detects
    much smaller differences. The discordant counts (fixed by the change, broken by the change) show what the
    difference is made of: +4.2 points can be 5 fixed and 0 broken, or 25 fixed and 20 broken. The second is a
    different change, with more risk of regressing someone's case, even at the same net number.

**4. Why does module 11 run experiments on dev and touch the held-out split only once, through `confirm --release`?
What would go wrong if you checked the held-out split after every experiment?**

??? question "Answer"
    Every decision made after looking at a set fits the system a little to that set. After twenty rounds of "look
    at held-out, adjust", the held-out score is as optimistic as the dev score, and nothing is left to tell you
    how the system does on queries you have not tuned on. One look, by the configuration already chosen on dev,
    keeps it an honest check; the `HoldoutGuard` refuses other reads and the log shows how many looks there were,
    so a reviewer can tell.

**5. Your p50 latency is unchanged after a change, but p95 rose from 7.8 s to 10.4 s. What kind of change does that
suggest, how would you confirm it from traces, and why is "average latency rose 0.7 s" a poor summary?**

??? question "Answer"
    A change that adds a lot of time to a minority of tasks (a retry, an escalation, an extra tool call on some
    inputs) and little or nothing to the rest. Confirm it by splitting latency per task into spans (model calls,
    self-checks, tools) and listing the tasks that slowed most: in the lab, the slowest tasks under `retry` are the
    retried ones (up to 10.8 s slower), and two of them climb into the slowest 5%. Also check which slow tasks were
    slow before the change: there, the four slowest were already slow without the retry. The average blends a big
    delay for a few users with nothing for most; the people waiting 10 s are the ones who notice. Report p50 and
    p95 (with intervals; p95 on 119 tasks rests on about six of them) and count tasks past the timeout as failures.

**6. Prompt caching cut cost per task by 46% in the lab. Name two conditions under which the saving in
production would be much smaller, and how you would check.**

??? question "Answer"
    Low or bursty traffic: the cache lives five minutes after its last use, so if requests are further apart, many
    calls write the cache (at 1.25 times the input price) and few read it; a single call per cache lifetime costs
    more than no caching. And a prefix that is not identical between requests: anything that varies (a timestamp,
    the user's name, a reordered tool list) before the cache marker means every request writes a new entry. Also,
    if output tokens dominate the cost, caching input saves less. Check the production cache hit rate (cache-read
    tokens over all input tokens, from the usage fields) and cost per success, not the lab's number.

**7. In the lab, a Haiku-first cascade that escalates to Sonnet when Haiku's answer fails the code checks was 78%
cheaper per success than Sonnet with caching, and the reference labels find no failure in its answers, while Haiku
alone skipped the investigation in 7 of 119. Why does the router work here, and when would it stop working?**

??? question "Answer"
    The router decides which answers are bad, and it can only see what the code checks see (format, citations,
    whether a tool ran). Haiku's only failure in this data, answering without the investigation the question
    needed, fails the `investigated` or `citations` check, so all 7 were escalated and Sonnet's second attempt was
    fine. It would stop working on failures that produce well-formed, properly cited, wrong answers, such as
    adopting a false premise or contradicting the tool output: they pass every code check and reach the user. So
    measure the router's recall on labelled data that contains the failures that matter; if they are missing from
    your data, you have not tested the router on them. A router that can see those modes (a validated judge on the
    premise and the cause, with its own TPR and TNR) is a new one-change configuration with its added cost and
    latency.

**8. In the lab, every configuration's task success is 63% to 71% by the automated grader, but the reference labels
find a failure in only 15 of the 833 dev answers. The pre-registered rule keeps nothing and recommends staying on v1.
Write the sentence about uncertainty that belongs in the memo, and one sentence that does not.**

??? question "Answer"
    Belongs: "Our automated grader fails all 15 answers the reference labels call defective, and also 251 of the
    818 they call correct (most of them answers that asked for a device the question did not name), so the success
    rates are stricter than accuracy; no change passed its registered rule, so we recommend keeping v1, and the
    cascade, 74% cheaper per success with no labelled failures, should be tested against v1 next." Does not
    belong: "v1 is 66% accurate" or "v3 is 6.7 points better than v2" (both read the grader's numbers as accuracy), or "the
    configurations are equivalent" (the labels say they are close, but 7 skipped investigations for Haiku against
    0 for v1 is a difference; and "no difference we could detect" needs the size we could detect, about 8 points).
    Name the measurement's weakness, give the numbers that show it, and say what would change the decision.
