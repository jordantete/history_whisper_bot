# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A Telegram bot ("Historical Figures Whisper Bot") that serves random historical figures on command. It runs as a single AWS Lambda function behind an HTTP webhook, deployed with the Serverless Framework. Each incoming Telegram update is a fresh invocation — the bot builds, initializes, processes one update, and shuts down within a single request.

## Commands

```bash
# Install
pip install -r requirements.txt
npm install                      # serverless-python-requirements plugin

# Run all tests (must run from project root — imports use the `src.` package prefix)
python -m pytest tests/

# Run a single test file / test
python -m pytest tests/test_database.py
python -m pytest tests/test_database.py::TestDatabase::test_get_random_figure

# Deploy to AWS (requires TELEGRAM_BOT_TOKEN in env; region eu-west-3, stage dev)
serverless deploy
```

## Architecture

Request flow: Telegram → API Gateway → `src/main.py:lambda_handler` → `Bot.start(event)` → python-telegram-bot dispatches to a `CommandHandler`.

- **`src/main.py`** — Lambda entrypoint. `lambda_handler` wraps the async `main()` with `run_until_complete`. `main()` always returns `OK_RESPONSE` (200) on success or `ERROR_RESPONSE` (400) on any exception — the bot never propagates errors to the Lambda runtime.
- **`src/bot.py`** — `Bot` wraps a python-telegram-bot `Application`. `start()` registers command handlers (`/start`, `/help`, `/new_figure`), then `initialize()` → `process_update()` → `shutdown()` for the single update in `event["body"]`. Handlers are private (`__start_handler` etc.), so tests reach them via name-mangled `_Bot__start_handler`.
- **`src/database.py`** — `Database` currently holds an in-memory hardcoded list of `HistoricalFigure`s. The Postgres/`psycopg2` connection is stubbed out (commented) — this is the intended future backing store.
- **`src/utils.py`** — `Utils.get_environment_varibale` reads config from `secrets.json` when that file exists (local dev), otherwise from `os.environ` (Lambda). `load_localizable_data` / `localize` implement the i18n lookup.
- **`src/logger.py`** — exports a configured `loguru` `LOGGER` singleton used everywhere.

## Conventions & gotchas

- **Config resolution**: `secrets.json` (gitignored) is the local override; presence of the file short-circuits env-var lookup. `serverless.yaml` injects `TELEGRAM_BOT_TOKEN` from the deploy environment.
- **Localization**: strings live in `src/localizable.json`, keyed by language then message key (`en`, `fr`). `Bot.selected_language` defaults to `"en"`. Add new user-facing strings there and fetch via `Utils.localize(key, lang, strings)` rather than hardcoding.
- **Tests are a mix of `unittest` and `pytest`**, and some are currently broken/aspirational — e.g. `tests/test_bot.py` patches `'bot.Update'` (should be `'src.bot.Update'`) and its async test isn't marked; `tests/test_main.py` references `asyncio` without importing it. Verify a test actually passes before treating it as a regression signal. Async tests rely on `pytest-asyncio` (`@pytest.mark.asyncio`), which is not yet in `requirements.txt`.
- **Note the typo `get_environment_varibale`** in `Utils` — it's the real method name; match it when calling.

## Working guidelines (Karpathy / Multica)

Behavioral principles for working in this repo, adapted from [multica-ai/andrej-karpathy-skills](https://github.com/multica-ai/andrej-karpathy-skills/blob/main/CLAUDE.md). These are general working defaults — **the project conventions and commands above take precedence** whenever they conflict. Bias toward caution over speed, but use judgment on trivial tasks.

1. **Think before coding** — State assumptions explicitly. When a request has multiple reasonable interpretations, surface them instead of silently picking one. If a simpler approach exists, say so. If something is genuinely unclear, stop and ask rather than guess.
2. **Simplicity first** — Write the minimum code that solves the problem. Nothing speculative: no unrequested features, no abstractions for a single use, no error handling for impossible cases. If it took 200 lines to do what 50 could, rewrite it. Would a senior engineer find this overcomplicated?
3. **Surgical changes** — Touch only what the task requires. Don't refactor or "improve" adjacent working code. Match the existing style. Flag pre-existing dead code rather than deleting it; only clean up orphans your own edits created (e.g. an import your change made unused).
4. **Goal-driven execution** — Turn the task into verifiable success criteria ("fix the bug" → "write a test that reproduces it, then make it pass"). Sketch a brief multi-step plan and verify at each step, so you can iterate independently instead of needing constant clarification.
