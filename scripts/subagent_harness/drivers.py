"""Direct calls into lab code paths that no CLI command replays end to end (run by consumers.sh)."""

import traceback

from mediadoctor import lab06


def main() -> None:
    for prompt, run in lab06.run_keys():  # module 6: every prompt x run, trials 0..4
        try:
            lab06.run_traces(prompt, run)
        except Exception:  # noqa: BLE001 - keep exploring the other runs
            traceback.print_exc()


if __name__ == "__main__":
    main()
