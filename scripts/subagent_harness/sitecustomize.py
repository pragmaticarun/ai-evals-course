"""Subagent fixture harness, loaded through PYTHONPATH (see scripts/subagent_fixtures.py).

Active only when SUBAGENT_HARNESS_DIR is set. It patches evalkit's FixtureStore for the course's
fixtures/recorded directory only (stores in a test's tmp directory are untouched):

  SUBAGENT_HARNESS_MODE=audit    replay the committed fixtures and log every key that is read
  SUBAGENT_HARNESS_MODE=collect  answer from <dir>/answers.jsonl; on a miss, queue the request in
                                 <dir>/pending.jsonl and return a placeholder answer so the run
                                 carries on (requests built from a placeholder are not queued)
"""

import os

if os.environ.get("SUBAGENT_HARNESS_DIR"):
    import json
    from pathlib import Path

    import evalkit.fixtures as fx

    _DIR = Path(os.environ["SUBAGENT_HARNESS_DIR"])
    _MODE = os.environ.get("SUBAGENT_HARNESS_MODE", "collect")
    MARK = "PENDING-ANSWER"
    PLACEHOLDER_TEXT = (
        f"{MARK}\nLikely cause: {MARK}\nNext step: {MARK}\nSources: [kb:{MARK.lower()}]\n"
        f"CRITIQUE: {MARK}\nVERDICT: PASS\nVERDICT: CLEAN\n"
        '{"verdict": "PASS", "pass": true, "score": 5, "label": "PASS", "critique": "'
        + MARK
        + '", "reasoning": "'
        + MARK
        + '"}'
    )
    _orig_get_record = fx.FixtureStore.get_record
    _orig_has = fx.FixtureStore.has
    _answers = None
    # Tests that build an unrecorded request on purpose and expect FixtureMissingError.
    PROBE_TESTS = (
        "test_unrecorded_decision_sequence_is_a_fixture_miss",
        "test_unrecorded_trial_fails_loudly",
        "test_v1_test_split_was_never_run",
        "test_changed_image_is_a_fixture_miss",
        "test_solution_snippet_runs",  # exercise solutions that perturb requests on purpose
    )

    def _probe():
        cur = os.environ.get("PYTEST_CURRENT_TEST", "")
        return any(t in cur for t in PROBE_TESTS)

    def _ours(store):
        try:
            return store.directory.resolve().name == "recorded" and (
                store.directory.resolve().parent.name == "fixtures"
            ) and "pytest" not in str(store.directory)
        except OSError:
            return False

    def _log(name, obj):
        with (_DIR / name).open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(obj, sort_keys=True, separators=(",", ":")) + "\n")

    def _load_answers():
        global _answers
        if _answers is None:
            _answers = {}
            p = _DIR / "answers.jsonl"
            if p.exists():
                for line in p.read_text(encoding="utf-8").splitlines():
                    if line.strip():
                        a = json.loads(line)
                        _answers[a["key"]] = a
        return _answers

    def get_record(self, request, trial=0):
        if not _ours(self):
            return _orig_get_record(self, request, trial)
        key = fx.request_key(request, trial)
        if _MODE == "audit":
            rec = _orig_get_record(self, request, trial)
            _log("audit.jsonl", {"ns": self.namespace, "key": key})
            return rec
        ans = _load_answers().get(key)
        if _probe():  # behave as the final replay will: new answers, and real misses
            if ans is None:
                raise fx.FixtureMissingError(key, self.namespace, self.path)
            _log("used.jsonl", {"ns": self.namespace, "key": key, "trial": trial})
            return {"response": ans["response"], "latency_ms": ans.get("latency_ms")}
        compact = fx.compact_request(fx.apply_generation(request))
        if ans is not None:
            _log("used.jsonl", {"ns": self.namespace, "key": key, "trial": trial})
            return {"response": ans["response"], "latency_ms": ans.get("latency_ms")}
        text = fx.canonical_json(compact)
        if MARK not in text and MARK.lower() not in text:
            _log("pending.jsonl", {"ns": self.namespace, "key": key, "trial": trial,
                                   "request": compact})
        resp = {"id": "msg_placeholder", "type": "message", "role": "assistant",
                "model": request.get("model"), "stop_reason": "end_turn",
                "content": [{"type": "text", "text": PLACEHOLDER_TEXT}],
                "usage": {"input_tokens": 1, "output_tokens": 1}}
        return {"response": resp, "latency_ms": 1000.0}

    def has(self, request, trial=0):
        if not _ours(self) or _MODE == "audit":
            return _orig_has(self, request, trial)
        return True

    fx.FixtureStore.get_record = get_record
    fx.FixtureStore.has = has
