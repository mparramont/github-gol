# Agent Notes

## Verification

Always finish completed implementation work by committing, pushing, and deploying it.

Use the Testing Trophy shape for this repo:

- Static checks first: `uvx ty check`, `uvx ruff check .`, and `uvx ruff format --check .`.
- Prefer high-level behavior tests before adding narrow unit tests: `uv run pytest` exercises the CLI against a temporary bare Git remote so it can verify history rewriting without touching the real GitHub repo.
- Keep a small set of focused unit tests for Game of Life rules and grid helpers.

Before every deploy:

1. Run `uv run pytest`.
2. Run `uvx ty check`.
3. Run `uvx ruff check .`.
4. Run `uvx ruff format --check .`.
5. Run `uv run python visualize_calendar.py` to capture the current GitHub contribution graph as the read-only baseline.

After every deploy:

1. Trigger one real production run through `/Users/mparramon/Desktop/GOL_Trigger.app`.
2. Confirm the trigger reached GitHub with `gh run list --workflow animate.yml --limit 5` when using the GitHub Actions engine.
3. Run `uv run python visualize_calendar.py` again and compare it to the baseline.
4. If the Worker itself changed, also verify the trigger endpoint returns HTTP 200 before checking the profile:
   `curl -s -o /dev/null -w '%{http_code}\n' -X POST https://github-gol-trigger.mparramont.workers.dev/trigger-gol-animation-5bc3a`.
