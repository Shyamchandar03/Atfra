# Autonomous Test Failure Resolution Agent (Playwright/Pytest)

This repository includes an **Autonomous Test Failure Resolution Agent** that:

1. Detects failing GitHub Actions runs for Playwright tests
2. Downloads and parses failure logs
3. Classifies the failure (timeout / locator / assertion / network)
4. Uses **Gemini** to propose a *minimal, anchored* edit plan
5. Applies the change locally, commits it to a new branch (via GitHub API)
6. Dispatches the Playwright workflow to validate the fix
7. Creates a Pull Request when tests pass

## Architecture (text diagram)

```
GitHub Actions (Playwright Tests)
        |
        | workflow_run (failure)
        v
GitHub Actions (Autofix Agent)
        |
        |-- GitHubClient: download logs, create branch/commit, dispatch workflow, open PR
        |-- Log Parser: extract stack traces + error excerpt
        |-- Failure Classifier: timeout/locator/assertion/network
        |-- LLM (Gemini): JSON fix plan with anchored edits
        |-- Code Fix Engine: apply anchored edits (and optional AST patches)
        |-- Validation Loop: rerun CI, retry N times
        v
Pull Request (autofix/run-<id>-a<attempt> -> main)
```

## How it works (workflow)

1. `Playwright Tests` fails.
2. `.github/workflows/autofix-agent.yml` triggers on `workflow_run: completed` when conclusion is `failure`.
3. Agent checks out the failing commit SHA for accurate code context.
4. Agent downloads logs ZIP from the failed run and extracts the first failure signature.
5. Agent calls Gemini to produce a **JSON-only** fix plan (minimal anchored edits).
6. Agent applies the edits, commits them to a new branch using GitHub REST git endpoints.
7. Agent dispatches the `Playwright Tests` workflow on that branch (`workflow_dispatch`) and waits.
8. If green → open PR. If red → retry (up to `AUTOFIX_MAX_ATTEMPTS`).

## Configuration

### GitHub Actions secrets

Set in repo settings:

- `GEMINI_API_KEY`: Gemini API key.

### Environment variables (Agent)

- `GEMINI_MODEL` (default `gemini-1.5-pro`)
- `PLAYWRIGHT_WORKFLOW_FILE` (default `playwright.yml`)
- `DEFAULT_BRANCH` (default `main`)
- `AUTOFIX_MAX_ATTEMPTS` (default `3`)
- `AUTOFIX_FLAKY_RERUN_ONCE` (default `true`)
- `SLACK_WEBHOOK_URL` (optional)

## Local usage (optional)

Install agent dependencies:

```bash
pip install -r requirements-agent.txt
```

Run an edit plan locally:

```bash
python -m scripts.code_modifier --plan /path/to/plan.json
```

### Dashboard

The agent stores fix history in `.autofix/memory.sqlite`.

```bash
streamlit run dashboard/app.py
```

### Webhook listener (self-hosted)

```bash
export GITHUB_WEBHOOK_SECRET="..."
uvicorn scripts.webhook_server:app --host 0.0.0.0 --port 8080
```

## Example (illustrative)

### Sample failing test

```python
page.click("#submit")
expect(page).to_have_title("Logged In Successfully | Practice Test Automation")
```

### Typical failure log

- `TimeoutError: Timeout 30000ms exceeded. waiting for selector "#submit"`

### Agent fix (minimal + explainable)

- Insert `expect(page.locator("#submit")).to_be_visible()` before the click, or replace `page.click(...)` with a locator-based click.
- Dispatch CI, then open a PR only if the branch run passes.
