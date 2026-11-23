# Exercises

Try each exercise before opening its solution. Code solutions are tested in CI and run from the repo root.

## Exercise 1: A threshold rule that does not flake at n=100

A team gates merges with "block if the pass rate drops at all". With 100 cases and a pass rate around 0.85, how often
does that rule block a change that changes nothing? Simulate it:

1. Model a live CI run: the baseline's outcomes, then a candidate that re-samples a share of cases (run-to-run
   noise: 8% for code-checked outcomes, 30% for something noisier such as a judge on new answers) and, optionally,
   loses 10 points for real.
2. Compare three rules: no drop allowed, a 3-point tolerance, and `evalkit.gate.evaluate_gate` with its default-like
   settings (alpha 0.05, margin 0.05, minimum effect 0.02).
3. Report how often each rule blocks with no real change (false blocks) and with a real 10-point drop (power).
   Which rule would you put on every PR, and what would you do about its power?

??? success "Solution"
    ```python
    # exercise-solution: a threshold rule that does not flake at n=100
    import random

    from evalkit.gate import GateRule, Status, evaluate_gate, naive_gate

    N, P, SIMS = 100, 0.85, 200
    rule = GateRule(alpha=0.05, margin=0.05, min_effect=0.02, draws=200)


    def simulate(flip: float, drop: float, seed: int) -> tuple[bool, bool, bool]:
        """One CI run: a baseline, then a candidate that re-samples a share `flip` of the cases
        (run-to-run noise) and, with `drop` > 0, also breaks that share of all cases."""
        rng = random.Random(seed)
        base = {f"q{i}": rng.random() < P for i in range(N)}
        head = {}
        for cid, ok in base.items():
            if rng.random() < flip:
                ok = rng.random() < P  # a fresh sample from the same model
            if ok and rng.random() < drop / P:
                ok = False
            head[cid] = ok
        a, b = sum(base.values()) / N, sum(head.values()) / N
        return (
            naive_gate(a, b) is Status.FAIL,
            naive_gate(a, b, 0.03) is Status.FAIL,
            evaluate_gate({"m": (base, head)}, rule).blocked,
        )


    print("share of runs blocked (n=100, pass rate 0.85)")
    print(f"{'run-to-run flips':<18}{'true change':<13}{'no drop':>9}{'3-pt tol.':>11}{'paired':>8}")
    for flip in (0.08, 0.30):
        for drop in (0.0, 0.10):
            runs = [simulate(flip, drop, seed) for seed in range(SIMS)]
            rates = [sum(r[i] for r in runs) / SIMS for i in range(3)]
            print(
                f"{flip:<18.2f}{-drop:<+13.2f}"
                + "".join(f"{x:>{w}.2f}" for x, w in zip(rates, (9, 11, 8), strict=True))
            )
    ```

    Output:

    ```text
    share of runs blocked (n=100, pass rate 0.85)
    run-to-run flips  true change    no drop  3-pt tol.  paired
    0.08              -0.00             0.34       0.01    0.00
    0.08              -0.10             1.00       0.98    0.80
    0.30              -0.00             0.48       0.10    0.01
    0.30              -0.10             0.99       0.96    0.61
    ```

    The no-drop rule blocks a third to a half of harmless changes: people would learn to re-run it until it passes.
    A 3-point tolerance looks good at low noise but flakes 10% of the time at higher noise; the right tolerance
    depends on n and on the noise, which is exactly what the paired test works out for you. The paired gate's false
    blocks stay near alpha/2 at both noise levels. Its price is power: at n=100 it catches a 10-point drop 61% to
    80% of the time. Raise power with more cases (`n_paired` from module 6), not
    by loosening alpha, and treat a warn as "read the flips" rather than as a pass.

## Exercise 2: Check that the held-out set is never used for tuning

`HoldoutGuard` protects code that asks it. Write a check that does not rely on that:

1. Run a "tuning step" (any function) and record every case id the agent is run on, without changing the step.
2. Flag held-out ids among them, held-out ids among the judges' few-shot examples, and held-out text that appears in
   an agent prompt (8-word runs).
3. Show that it passes for the gate's tiers and catches a shortcut that replays every labelled case to find the worst
   ones.

??? success "Solution"
    ```python
    # exercise-solution: check that the held-out set is never used for tuning
    import contextlib

    from evalkit.hygiene import ngram_contamination
    from evalkit.synth import prose
    from mediadoctor import lab05, lab08

    HOLDOUT = set(lab08.holdout_ids())


    @contextlib.contextmanager
    def watch_agent_runs():
        """Record the case id of every agent run made inside the block."""
        seen: list[str] = []
        real = lab08.run_agent

        def spy(*args, case_id=None, **kwargs):
            seen.append(case_id)
            return real(*args, case_id=case_id, **kwargs)

        lab08.run_agent = spy
        try:
            yield seen
        finally:
            lab08.run_agent = real


    def holdout_problems(tuning_step) -> list[str]:
        """Run one tuning step and list every way it touched the held-out split."""
        problems = []
        with watch_agent_runs() as seen:
            tuning_step()
        if touched := sorted(HOLDOUT & set(seen)):
            problems.append(f"ran the agent on {len(touched)} held-out cases, e.g. {touched[0]}")
        for name in lab08.gate_config()["tiers"]["judges"]["judges"]:
            spec = lab05.load_spec(name)
            if used := [e.case_id for e in spec.examples if e.case_id in HOLDOUT]:
                problems.append(f"judge {spec.key} uses held-out examples {used}")
        texts = {c: prose(lab08.rows()[c]["question"]) for c in HOLDOUT}
        corpus = {f"agent prompt {v}": t for v, t in lab08.AGENT_PROMPTS.items()}
        for cid, src, gram in ngram_contamination(texts, corpus, n=8):
            problems.append(f"{src} contains held-out text from {cid}: '{gram}'")
        return problems


    def gate_tuning_loop():
        """What a prompt author does while iterating: run the gate tiers and read the failures."""
        lab08.run_suite("v2", lab08.TIERS)


    def worst_cases_anywhere():
        """A tempting shortcut: replay every labelled case (guard bypassed) and tune on the worst."""
        lab08.run_traces("v2", sorted(lab08.rows()), lab08.agent_llm())


    for step in (gate_tuning_loop, worst_cases_anywhere):
        found = holdout_problems(step)
        print(f"{step.__name__}: {'clean' if not found else '; '.join(found)}")
    ```

    Output:

    ```text
    gate_tuning_loop: clean
    worst_cases_anywhere: ran the agent on 29 held-out cases, e.g. m4q008
    ```

    The spy sees every agent run inside the block, whatever path it took, so it also catches code that bypasses the
    guard. Put a check like this in `evals/` for each script your team uses while iterating (prompt sweeps,
    failure-mining notebooks), and extend the corpus to anything else people tune against: the judge prompts, tool
    descriptions, and the KB.

## Exercise 3: Read an experiment comparison

Save v1 and v2 runs with both tiers, diff them, and use the result to write the comment you would leave on the PR:

1. What do the newly failing format answers have in common?
2. Why did the one citations case flip?
3. Write a three-sentence PR comment: the decision, the evidence, and the suggested fix.

??? success "Solution"
    ```python
    # exercise-solution: read an experiment comparison and write the PR comment
    import tempfile
    from collections import Counter
    from pathlib import Path

    from evalkit.gate import flips
    from mediadoctor import lab06, lab08

    out = Path(tempfile.mkdtemp())
    for prompt in ("v1", "v2"):
        lab08.main(["run", "--prompt", prompt, "--tier", "all", "--out", str(out / f"{prompt}.json")])
    lab08.main(["diff", str(out / "v1.json"), str(out / "v2.json"), "--out", str(out / "diff.md")])
    print((out / "diff.md").read_text().splitlines()[0])

    v1, v2 = lab08.run_suite("v1", ("code",)), lab08.run_suite("v2", ("code",))
    lost, gained = flips(v1.outcomes["code"]["format"], v2.outcomes["code"]["format"])
    openers = Counter(v2.answers[c].split(":", 1)[0] for c in lost)
    print(
        f"format: {len(lost)} newly failing, {len(gained)} newly passing; first words: {dict(openers)}"
    )
    cites, _ = flips(v1.outcomes["code"]["citations"], v2.outcomes["code"]["citations"])
    for cid in cites:
        sources = next(ln for ln in v2.answers[cid].splitlines() if ln.startswith("Sources:"))
        tools = [t[0] for t in lab06.items("v2", 1)[cid].tools]
        print(f"citations: {cid} newly failing -> {sources}, tools called: {tools or 'none'}")

    comment = f"""\
    **v2 is blocked by the format check, not by its content.** {len(lost)} of 108 answers now open with
    "Premise check:" instead of "Likely cause:", which breaks every client that parses the reply. The
    judge tier (dev, n=37) shows no significant change in either direction. Suggested fix: ask for the
    premise check inside "Likely cause", re-record the gate set, and re-run the gate."""
    print(comment)
    ```

    Output:

    ```text
    wrote <tmp>/v1.json
    wrote <tmp>/v2.json
    wrote <tmp>/diff.md
    ## v1 → v2: ❌ blocked
    format: 16 newly failing, 0 newly passing; first words: {'Premise check': 16}
    citations: m4q088 newly failing -> Sources: [kb:hdr-tone-mapping], tools called: none
    **v2 is blocked by the format check, not by its content.** 16 of 108 answers now open with
    "Premise check:" instead of "Likely cause:", which breaks every client that parses the reply. The
    judge tier (dev, n=37) shows no significant change in either direction. Suggested fix: ask for the
    premise check inside "Likely cause", re-record the gate set, and re-run the gate.
    ```

    The report answers "what broke" in one table and "why" in the flips. The citations flip is v2 answering
    `m4q088` from memory, without calling `search_kb`, while still citing a KB document; it is one case and does
    not block, but it is worth a line in the comment because it is the kind of failure the false-premise fix should
    not encourage.

## Exercise 4: When must you re-record?

For each change, predict whether the gate's replay misses (and where), then check with the code: (a) a typo fix in
prompt v1, (b) a new agent model ID, (c) a sentence added to a tool's description, (d) an edit to a KB document,
(e) a reworded judge pass definition, (f) a corrected label.

??? success "Solution"
    ```python
    # exercise-solution: which changes force a re-record?
    import contextlib
    import copy
    import dataclasses
    import tempfile
    from pathlib import Path

    from evalkit import repo_root
    from evalkit.golden import check_manifest, load_manifest
    from mediadoctor import lab05, lab08, toolagent

    GATE = lab08.ids_in(lab08.tier_splits("code"))


    @contextlib.contextmanager
    def patched(obj, name, value):
        old = getattr(obj, name)
        setattr(obj, name, value)
        try:
            yield
        finally:
            setattr(obj, name, old)


    def prompt_typo():
        fixed = toolagent.AGENT_PROMPTS["v1"].replace("gather evidence", "gather the evidence")
        return patched(toolagent, "AGENT_PROMPTS", {**toolagent.AGENT_PROMPTS, "v1": fixed})


    def model_bump():
        real = toolagent.load_models
        roles = dict(real())
        roles["agent"] = dataclasses.replace(roles["agent"], model="claude-sonnet-5-6")
        return patched(toolagent, "load_models", lambda: roles)


    def tool_description():
        tools = copy.deepcopy(toolagent.TOOLS)
        tools[0]["description"] += " Results are cached."
        return patched(toolagent, "TOOLS", tools)


    def kb_edit():
        real = toolagent.run_tool

        def run_tool(name, args, tracer=None):
            out = real(name, args, tracer=tracer)
            return out + "\n(reviewed 2026-11)" if name == "search_kb" else out

        return patched(toolagent, "run_tool", run_tool)


    def judge_wording():
        real = lab05.load_spec

        def load_spec(name, version=None):
            spec = real(name, version)
            return dataclasses.replace(spec, pass_def=spec.pass_def + " Be strict.")

        return patched(lab05, "load_spec", load_spec)


    def count_misses(tier):
        try:
            run = lab08.run_suite("v1", (tier,))
        except lab08.ReplayMissError as exc:
            return len(exc.missing), "n/a"  # the agent missed, so the judges never ran
        return 0, len(run.judge_misses) if tier == "judges" else "n/a"


    print(f"{'change':<22}{'preflight':>10}{'agent':>7}{'judge':>7}")
    for change in (prompt_typo, model_bump, tool_description, kb_edit, judge_wording):
        with change():
            first = len(lab08.preflight("v1", GATE))
            agent, _ = count_misses("code")
            _, judge = count_misses("judges")
        print(f"{change.__name__:<22}{first:>10}{agent:>7}{judge!s:>7}")

    # A relabel changes no request, so nothing misses; the manifest catches it instead.
    labels = "data/labels/module06_runs.csv"
    root = Path(tempfile.mkdtemp())
    (root / labels).parent.mkdir(parents=True)
    text = (repo_root() / labels).read_text()
    assert "v2,1,m4q088,fail" in text
    (root / labels).write_text(text.replace("v2,1,m4q088,fail", "v2,1,m4q088,pass", 1))
    manifest = load_manifest(lab08.manifest_path())
    print("relabel:", [p for p in check_manifest(manifest, root) if labels in p])
    ```

    Output:

    ```text
    change                 preflight  agent  judge
    prompt_typo                  108    108    n/a
    model_bump                   108    108    n/a
    tool_description             108    108    n/a
    kb_edit                        0     57    n/a
    judge_wording                  0      0    107
    relabel: ['data/labels/module06_runs.csv: changed since version 1.0.1']
    ```

    - Prompt, model, and tool definitions are part of every request: all 108 cases miss at the first turn, and
      `preflight` catches it in milliseconds. Re-record the gate set (and then the judges on the new answers).
    - A KB edit changes no first request, so preflight passes; it changes the `search_kb` result, and with it the
      second request of the 57 cases that search. Only a full replay finds those misses, which is why the suite
      catches misses during the run as well.
    - A judge wording change misses all 107 judge calls but no agent call: re-record the judge tier, then
      re-validate the judge against labels (module 5) before trusting it.
    - A relabel changes no request, so nothing misses. It changes a file in the golden manifest, so CI fails until
      the version is bumped (a minor bump: same cases, new labels), and every number that used the old label should
      be re-read.

## Exercise 5: Budget the judge tier

1. From the recorded usage, what does one dev case cost to re-record live (agent and judges), and how long do its
   calls take?
2. How often do v1 and v2 get different verdicts from each judge? What drop can 37 cases detect with 80% power?
3. How many cases would detect a 10-point drop, and does re-recording that many fit a $1.00 nightly budget?

??? success "Solution"
    ```python
    # exercise-solution: budget the judge tier
    from evalkit.gate import Usage
    from evalkit.stats import mdd_paired, n_paired
    from mediadoctor import lab08

    b = lab08.budget()
    v1 = lab08.run_suite("v1", lab08.TIERS)
    v2 = lab08.run_suite("v2", lab08.TIERS)
    judges, agent = v1.usage["judges"], v1.usage["agent"]
    n_dev = len(lab08.ids_in(lab08.tier_splits("judges")))
    per_case = Usage(
        agent.calls / len(v1.answers) + judges.calls / n_dev,
        0, 0,
        agent.cost_usd / len(v1.answers) + judges.cost_usd / n_dev,
        agent.latency_s / len(v1.answers) + judges.latency_s / n_dev,
    )  # fmt: skip
    print(
        f"one dev case, live: {per_case.calls:.1f} calls, ${per_case.cost_usd:.4f}, {per_case.latency_s:.0f} s of calls"
    )

    # How often do v1 and v2 disagree, per judge? That share drives the sample size.
    disc = {}
    for name in lab08.gate_config()["tiers"]["judges"]["judges"]:
        a, h = v1.outcomes["judges"][name], v2.outcomes["judges"][name]
        both = [c for c in a if a[c] is not None and h.get(c) is not None]
        disc[name] = sum(a[c] != h[c] for c in both) / len(both)
    d = max(disc.values())
    print("discordant share per judge:", {k: round(v, 3) for k, v in disc.items()})
    mdd = mdd_paired(n_dev, d)
    print(
        f"n={n_dev} detects a paired drop of {mdd:.2f}"
        if mdd == mdd  # nan when no drop below the discordant share is detectable
        else f"n={n_dev} cannot reliably detect any drop smaller than the {d:.2f} disagreement rate"
    )
    n = n_paired(d, 0.10)
    print(f"to detect a 10-point drop: n={n} cases")

    nightly = 1.00  # dollars per night for re-recording the judge tier live
    cost_n = n * per_case.cost_usd
    minutes = n * per_case.latency_s / b.concurrency / 60
    print(
        f"re-recording n={n} live: ${cost_n:.2f}, {minutes:.0f} min at {b.concurrency} parallel "
        f"({'within' if cost_n <= nightly else 'over'} a ${nightly:.2f} nightly budget)"
    )
    ```

    Output:

    ```text
    one dev case, live: 5.1 calls, $0.0058, 6 s of calls
    discordant share per judge: {'false-premise': 0.162, 'tool-grounding': 0.182, 'next-step': 0.081}
    n=37 cannot reliably detect any drop smaller than the 0.18 disagreement rate
    to detect a 10-point drop: n=141 cases
    re-recording n=141 live: $0.82, 4 min at 4 parallel (within a $1.00 nightly budget)
    ```

    At 37 cases the judge tier cannot see a drop smaller than the rate at which the two prompts disagree, so its
    warns are expected and its passes mean little. About 141 cases would detect a 10-point paired drop, and
    re-recording them every night costs about $0.82 at these token counts: affordable, but it uses most of a $1.00
    budget, so a weekly run with alerts on warn may be the better trade. These sizes assume the judge is right; a
    judge with low TNR (false-premise, 0.44 on dev) shrinks every difference and needs more cases still.
