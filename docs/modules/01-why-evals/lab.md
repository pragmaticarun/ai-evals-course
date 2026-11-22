# Lab 1: Run, check, compare (offline)

**Time:** about 1.5 hours. **Needs:** Ubuntu (or any Linux/macOS), `git`, and [`uv`](https://docs.astral.sh/uv/).
**Does not need:** an API key. Everything runs in replay mode from committed fixtures.

## 1. Set up

```bash
git clone https://github.com/pragmaticarun/ai-evals-course.git
cd ai-evals-course
uv sync                      # installs Python 3.14 if needed, plus pinned dependencies
uv run pytest -q             # all tests run offline in replay mode
```

`uv sync` reads `.python-version` (3.14) and `uv.lock`, so you get exactly the versions listed on the
[Versions checked](../../versions.md) page.

## 2. How replay works

Every Claude call in this course goes through `evalkit.llm.LLM`:

```python
from evalkit import LLM, text_of

llm = LLM(namespace="mediadoctor-seed")  # mode from EVALS_LLM_MODE, default "replay"
resp = llm.create(model=..., max_tokens=..., system=..., messages=[...])
print(text_of(resp))
```

- The request dict is serialized as canonical JSON (sorted keys, no whitespace) and hashed with SHA-256.
- In **replay** mode the hash is looked up in `fixtures/recorded/<namespace>.jsonl`. No network, no key.
  A miss raises `FixtureMissingError` with instructions to re-record.
- In **record** mode the real API is called and the response is saved under that hash.
- In **live** mode the API is called and nothing is saved.

Because the model ID is part of the request, editing `config/models.toml` invalidates the fixtures. That is
deliberate: a silent fallback to an old model's answer would make every comparison meaningless.

!!! question "Try it"
    Open `fixtures/recorded/mediadoctor-seed.jsonl` and look at one line. Find the `request_sha256` (the fixture key), the full `request`
    (system prompt, retrieved context, question) and the `response`. Then change one word in
    `labs/mediadoctor/src/mediadoctor/prompts.py`, run step 3, read the error, and revert the change.

## 3. Run prompt v1

```bash
uv run mediadoctor-lab01 run --prompt v1 --out runs/v1.jsonl
```

You should see 20 lines of `PASS` or `FAIL <checks>` and a summary ending in `ALL 16/20`.
`runs/` is git-ignored; it is your scratch space.

## 4. Read before you count

Read at least these answers in full:

```bash
uv run mediadoctor-lab01 show q07
uv run mediadoctor-lab01 show q11
uv run mediadoctor-lab01 show q05
```

For each one, write one line in a notes file: what is wrong, if anything, and *why* you think it happened. Keep
your notes. Module 3 turns this habit into a method.

## 5. Compare v1 and v2

```bash
uv run mediadoctor-lab01 compare v1 v2
```

Confirm the result from the lesson: v2 fixes q07 and q18, breaks q03, q09, and q14, and is worse overall. Open
`labs/mediadoctor/src/mediadoctor/prompts.py` and decide which sentence in v2 most likely caused the regressions.

## 6. Write your eval plan

Copy this into `notes/eval-plan.md` (any location you like) and fill it in; it is the module 1 artifact.

```markdown
# MediaDoctor eval plan (v0)
- Users and their top 3 tasks:
- What a good answer must do (3 to 5 bullets):
- Failure modes seen so far (from step 4):
- Code checks I have: format, cites_kb, length
- Checks I want next (code or judge, and why):
- What would make me block a prompt change:
```

## 7. Optional: re-record with your own key

Only if you want real Claude output. Your key stays in your shell or a git-ignored `.env`, never in the repo.

```bash
export ANTHROPIC_API_KEY=...            # or put it in .env
EVALS_LLM_MODE=record uv run mediadoctor-lab01 compare v1 v2
git diff --stat fixtures/               # records now say "source": "live"
```

Real answers will not reproduce the planted failures exactly, so `tests/test_lab01.py`, which pins the lesson's
numbers, will fail after re-recording. Restore the course fixtures with `git checkout fixtures/` when you are done.

## Checkpoint

- [ ] `uv run pytest -q` passes
- [ ] You can explain why v2 is worse than v1 even though it fixed what it targeted
- [ ] You found the confidently wrong answer that passes every check
- [ ] `eval-plan.md` exists
