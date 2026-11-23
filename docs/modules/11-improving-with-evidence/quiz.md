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
    difference is made of: +4.6 points can be 5 fixed and 0 broken, or 25 fixed and 20 broken. The second is a
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
    self-checks, tools) and listing the tasks that slowed most: in the lab, every task in the slowest 5% was a
    retried one. The average blends a big delay for a few users with nothing for most; the people waiting 10 s
    are the ones who notice. Report p50 and p95 (with intervals; p95 on 108 tasks rests on about five of them) and
    count tasks past the timeout as failures.

**6. Prompt caching cut cost per success by 59% in the lab. Name two conditions under which the saving in
production would be much smaller, and how you would check.**

??? question "Answer"
    Low or bursty traffic: the cache lives five minutes after its last use, so if requests are further apart, many
    calls write the cache (at 1.25 times the input price) and few read it; a single call per cache lifetime costs
    more than no caching. And a prefix that is not identical between requests: anything that varies (a timestamp,
    the user's name, a reordered tool list) before the cache marker means every request writes a new entry. Also,
    if output tokens dominate the cost, caching input saves less. Check the production cache hit rate (cache-read
    tokens over all input tokens, from the usage fields) and cost per success, not the lab's number.

**7. A Haiku-first cascade that escalates to Sonnet when Haiku's answer fails the code checks was 83% cheaper per
success but 16 points less accurate. Why, and what would you try next?**

??? question "Answer"
    The router decides which answers are bad, and it can only see what the code checks see (format, citations,
    whether a tool ran). Haiku's main failures, adopting a false premise and contradicting the tool output, produce
    well-formed, properly cited answers, so the router passes them and none were escalated. Next: a router that can
    see those modes, such as a validated judge on the premise and the cause (with its own TPR and TNR measured on
    labelled data), tested as a new one-change configuration with its added cost and latency.

**8. The experiment log says the retry configuration passed its rule (CI +0.9 to +9.3 points; 5 fixed, 0 broken),
and the decision memo recommends it. Write the sentence about uncertainty that belongs in the memo, and one sentence
that does not.**

??? question "Answer"
    Belongs: "The retry step rests on five queries that changed outcome (exact McNemar p = 0.06); its gain is likely
    but not proven, and the held-out check (29 queries) is consistent with it but too small to confirm it." Does not
    belong: "Retry improves accuracy by 4.6%" (no interval, no n, and it reads as a production promise), or "the
    improvement is statistically significant" on its own (which test? the bootstrap and McNemar disagree at this
    size). Name the test you pre-registered, give the interval, and say what would change the decision.
