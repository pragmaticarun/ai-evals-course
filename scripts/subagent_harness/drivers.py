"""Direct calls into lab code paths that no CLI command replays end to end (run by consumers.sh)."""

import traceback

from mediadoctor import lab05, lab06


def main() -> None:
    for prompt, run in lab06.run_keys():  # module 6: every prompt x run, trials 0..4
        try:
            lab06.run_traces(prompt, run)
        except Exception:  # noqa: BLE001 - keep exploring the other runs
            traceback.print_exc()
    # Paths only the docs' exercise solutions take (tests/test_docs_snippets.py runs them in
    # probe mode, because some solutions perturb requests on purpose).
    calls = [lambda s=s: lab05.likert_scores(s) for s in ("train", "dev", "test")]
    calls += [lambda p=p: lab06.helpfulness(p) for p in lab06.PROMPTS]
    for call in calls:
        try:
            call()
        except Exception:  # noqa: BLE001
            traceback.print_exc()


if __name__ == "__main__":
    main()
