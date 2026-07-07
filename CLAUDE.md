# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A Telegram bot ("Historical Figures Whisper Bot") that serves historical figures on command. It runs as a long-running **long-polling** process (`Application.run_polling()`) — no public HTTP endpoint needed — deployed to a VPS inside a dedicated `tmux` session. Localized EN/FR.

## Commands

```bash
# Install
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Configure secrets (local dev)
cp .env.example .env          # then fill TELEGRAM_BOT_TOKEN

# Run the bot locally (long-polling)
python -m src.main

# Run all tests (must run from project root — imports use the `src.` package prefix)
python -m pytest tests/

# Run a single test file / test
python -m pytest tests/test_database.py
python -m pytest tests/test_database.py::TestDatabase::test_get_random_figure

# Deploy to the VPS (reads VPS_* + TELEGRAM_BOT_TOKEN from .env)
./scripts/deploy.sh
```

## Architecture

Flow: `python -m src.main` → `Bot.run()` → `Application.run_polling()` → python-telegram-bot polls Telegram (`getUpdates`) and dispatches to a `CommandHandler`. It's a single continuous process, not a per-request invocation.

- **`src/main.py`** — Entrypoint. Calls `load_dotenv()` (so a direct `python -m src.main` picks up `.env` without shell sourcing), then builds `Database` + `Bot` and calls `bot.run()`.
- **`src/bot.py`** — `Bot` wraps a python-telegram-bot `Application`. The token is read from `os.environ` in `__init__` (after `load_dotenv`). `register_handlers()` registers `/start`, `/help`, `/random`, `/today`, `/subscribe`, `/unsubscribe`, `/feedback`, plus a `CallbackQueryHandler` for the inline buttons; `run()` starts long-polling. Handlers are private (`__start_handler` etc.), so tests reach them via name-mangled `_Bot__start_handler`.
- **`src/database.py`** — `Database` currently holds an in-memory hardcoded list of `HistoricalFigure`s. The Postgres/`psycopg2` connection is stubbed out (commented) — this is the intended future backing store.
- **`src/utils.py`** — `Utils.get_environment_variable` reads from `os.environ`. `load_localizable_data` / `localize` implement the i18n lookup.
- **`src/logger.py`** — exports a configured `loguru` `LOGGER` singleton used everywhere.

## Deployment

Deployment mirrors the sibling bots (`arbitrage-bot`, `funding-rate-bot`, `encheres-scanner`): an SSH/rsync script that runs the bot in a `tmux` session on a VPS. There is **no AWS/serverless anymore** — don't reintroduce Lambda, API Gateway, webhooks, or the Serverless Framework.

- **`scripts/deploy.sh`** — sources `.env`, rsyncs the code to `$VPS_HOST:$VPS_BOT_PATH` (excluding `.env`, `.venv`, `logs/`, caches), copies `.env` separately, (re)creates the venv + `pip install -r requirements.txt`, then restarts the `history-whisper-bot` tmux session.
- **`scripts/start.sh`** — sources `.env` and `exec`s `python -m src.main`, logging to `logs/app.log`. This is what the tmux session runs.

## Conventions & gotchas

- **Secrets**: `.env` (gitignored) holds the runtime token (`TELEGRAM_BOT_TOKEN`) and the deploy target (`VPS_USER`, `VPS_HOST`, `VPS_BOT_PATH`, `SSH_KEY`). `.env.example` is the committed template. Never commit `.env`; never put tokens in git or Notion. Prefer a distinct bot/token per environment (dev/prod).
- **Localization**: strings live in `src/localizable.json`, keyed by language then message key (`en`, `fr`). `Bot.selected_language` defaults to `"en"`. Add new user-facing strings there and fetch via `Utils.localize(key, lang, strings)` rather than hardcoding.
- **Single poller per token**: only one process may poll a given token at once. Running the bot locally while the VPS instance is live (same token) causes a `getUpdates` conflict — use a separate dev token.
- **Tests**: `pytest` from the project root. `test_bot.py` uses `unittest.IsolatedAsyncioTestCase` for the async handlers and sets a dummy `TELEGRAM_BOT_TOKEN` via `patch.dict(os.environ, ...)` so `Bot.__init__` can build the `Application` without a real token.

## Working guidelines (Karpathy / Multica)

Behavioral principles for working in this repo, adapted from [multica-ai/andrej-karpathy-skills](https://github.com/multica-ai/andrej-karpathy-skills/blob/main/CLAUDE.md). These are general working defaults — **the project conventions and commands above take precedence** whenever they conflict. Bias toward caution over speed, but use judgment on trivial tasks.

1. **Think before coding** — State assumptions explicitly. When a request has multiple reasonable interpretations, surface them instead of silently picking one. If a simpler approach exists, say so. If something is genuinely unclear, stop and ask rather than guess.
2. **Simplicity first** — Write the minimum code that solves the problem. Nothing speculative: no unrequested features, no abstractions for a single use, no error handling for impossible cases. If it took 200 lines to do what 50 could, rewrite it. Would a senior engineer find this overcomplicated?
3. **Surgical changes** — Touch only what the task requires. Don't refactor or "improve" adjacent working code. Match the existing style. Flag pre-existing dead code rather than deleting it; only clean up orphans your own edits created (e.g. an import your change made unused).
4. **Goal-driven execution** — Turn the task into verifiable success criteria ("fix the bug" → "write a test that reproduces it, then make it pass"). Sketch a brief multi-step plan and verify at each step, so you can iterate independently instead of needing constant clarification.
