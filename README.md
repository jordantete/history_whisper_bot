<p align="center">
  <img src="assets/logo.png" alt="Historical Figures Whisper Bot" width="120" height="120" />
</p>

<h1 align="center">Historical Figures Whisper Bot</h1>

<p align="center">
  <strong>A bilingual Telegram bot that serves historical figures on demand.</strong><br/>
  Figure cards, an optional daily subscription, and inline discovery, in English and French.
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white" alt="Python" />
  <img src="https://img.shields.io/badge/python--telegram--bot-22.8-2CA5E0?logo=telegram&logoColor=white" alt="python-telegram-bot" />
  <img src="https://img.shields.io/badge/i18n-EN%20%7C%20FR-8A2BE2" alt="Localization" />
  <img src="https://img.shields.io/badge/deploy-VPS%20%2B%20tmux-121011?logo=gnu-bash&logoColor=white" alt="Deployment" />
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-yellow" alt="License" /></a>
</p>

<p align="center">
  <a href="https://jordantete.github.io/history_whisper_bot/"><img src="https://img.shields.io/badge/Landing_page-Visit-e6c36c?style=for-the-badge&labelColor=241c07&logo=githubpages&logoColor=e6c36c" alt="Landing page" /></a>
  &nbsp;
  <a href="https://t.me/HistoricalFiguresWhisperBot"><img src="https://img.shields.io/badge/Telegram-Open-2CA5E0?style=for-the-badge&labelColor=241c07&logo=telegram&logoColor=2CA5E0" alt="Open in Telegram" /></a>
</p>

---

## About

Historical Figures Whisper Bot sends you a historical figure whenever you ask for one. Use `/random`
for a figure at random, `/today` for the figure of the day, `/quote` for a sourced quote, or
`/subscribe` to get a figure and a quote automatically each day. Every figure arrives as a card with a
portrait, a short biography, a few highlights, and a link to read more on Wikipedia; every quote
arrives as its own card with its author and source.

The bot runs as a single long-polling process, so it needs no public HTTP endpoint and no webhook. It
is deployed to a VPS inside a dedicated `tmux` session. All user-facing text is available in English
and French, and the language is picked automatically from each user's Telegram settings.

## Features

|                     |                                                                                     |
| ------------------- | ----------------------------------------------------------------------------------- |
| **Curated figures** | Hand-picked historical figures with biographies and highlights, enriched from Wikidata |
| **Quote of the day** | Independent pool of sourced quotes harvested from Wikiquote FR, served on `/quote` and delivered right after the daily figure |
| **Bilingual EN/FR** | Language chosen per user from their Telegram `language_code`, with no per-user storage |
| **Figure cards**    | HTML cards with a bold name, an italic biography, highlights, a portrait, and a Wikipedia link |
| **Quote cards**     | HTML cards with the quote, its author, and its source, distinct from the figure card |
| **Daily delivery**  | Optional daily figure and quote sent to subscribers at 12:00 Europe/Paris through the JobQueue |
| **Inline buttons**  | Random, Today, Read more, and Share under a figure card; Another quote, Source, and Share under a quote card |
| **Feedback**        | `/feedback` forwards suggestions to the owner, with a per-user cooldown against flooding |
| **Private only**    | The bot leaves any group or channel and works one to one                            |
| **Rate limited**    | `AIORateLimiter` paces outgoing calls so bursts of traffic stay within Telegram's limits |

## Commands

| Command | Description |
| ------- | ----------- |
| `/start` | Welcome message with an inline keyboard (Random, Today, Help) |
| `/help` | List the available commands |
| `/random` | A random historical figure |
| `/today` | The historical figure of the day |
| `/quote` | The quote of the day |
| `/subscribe` | Start receiving the daily figure and quote |
| `/unsubscribe` | Stop the daily delivery |
| `/feedback` | Suggest a figure or send feedback, either as `/feedback <text>` or interactively |
| `/suggest` | Owner-only: queue candidate figure names for the content pipeline; not in the published menu |

## Tech Stack

- Python 3.10+ with `asyncio`
- [python-telegram-bot](https://python-telegram-bot.org/) 22.8, using the `rate-limiter` and `job-queue` extras for flood control and the daily scheduler
- loguru for logging to `logs/app.log`
- python-dotenv for `.env` configuration
- JSON files for storage: figures in `src/figures.json`, quotes in `src/quotes.json`, subscribers in
  `subscribers.json`, and owner-submitted figure suggestions in `suggestions.json`

## Quick Start

```bash
# Clone
git clone https://github.com/jordantete/history_whisper_bot.git
cd history_whisper_bot

# Install
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Configure
cp .env.example .env          # then fill TELEGRAM_BOT_TOKEN

# Run (long-polling)
python -m src.main
```

`src/main.py` loads `.env` via python-dotenv, so `python -m src.main` picks up the token without
sourcing your shell.

> Only one process can poll a given bot token at a time. If you run the bot locally while the VPS
> instance is live with the same token, Telegram returns a `getUpdates` conflict. Use a separate
> token for development.

## Configuration

All configuration lives in `.env` (gitignored). Copy `.env.example` and fill it in.

| Variable | Required | Description |
| -------- | :------: | ----------- |
| `TELEGRAM_BOT_TOKEN` | Yes | Bot token from [@BotFather](https://t.me/BotFather) |
| `OWNER_CHAT_ID` | No | Chat that receives forwarded `/feedback` messages |
| `SUBSCRIBERS_FILE` | No | Path to the daily-delivery subscribers file (default `subscribers.json`) |
| `VPS_USER`, `VPS_HOST`, `VPS_BOT_PATH`, `SSH_KEY` | Deploy | VPS target used by `scripts/deploy.sh` |

### BotFather setup

Set the avatar and command menu through [@BotFather](https://t.me/BotFather):

- `/setuserpic` uploads `assets/logo.png` as the bot avatar.
- `/setcommands` is optional, because the localized menus are published automatically at startup in `Bot._post_init`.

## Tests

```bash
python -m pytest tests/
```

Run the tests from the project root. Imports use the `src.` package prefix, so pytest has to run from
the root for them to resolve.

## Deployment (VPS + tmux)

Fill the deployment variables in `.env` (`VPS_USER`, `VPS_HOST`, `VPS_BOT_PATH`, `SSH_KEY`), then run:

```bash
./scripts/deploy.sh
```

`scripts/deploy.sh` rsyncs the code to the VPS, copies `.env` separately, recreates the venv, installs
`requirements.txt`, and restarts the `history-whisper-bot` `tmux` session. That session runs
`scripts/start.sh`, which execs `python -m src.main` and logs to `logs/app.log`.

```bash
# Follow the logs
ssh $VPS_USER@$VPS_HOST 'tail -f $VPS_BOT_PATH/logs/app.log'

# Attach to the session (detach with Ctrl-b then d)
ssh $VPS_USER@$VPS_HOST 'tmux attach -t history-whisper-bot'
```

## Project Structure

```
src/
├── main.py               # entrypoint: load_dotenv, build Database + Bot, bot.run()
├── bot.py                # Bot: handlers, figure/quote cards, daily job, feedback
├── database.py           # Database: loads and serves figures + quotes
├── subscribers.py        # SubscriberStore: JSON-persisted daily subscribers
├── suggestions.py        # SuggestionStore: JSON-persisted /suggest queue
├── historical_figure.py  # HistoricalFigure model
├── quote.py              # Quote model
├── utils.py              # env vars, i18n (localize, resolve_locale), slugs/ids
├── logger.py             # configured loguru LOGGER singleton
├── figures.json          # curated figures (bios, facts, Wikidata ids)
├── quotes.json           # curated, sourced quotes (Wikiquote FR)
└── localizable.json      # EN/FR strings, keyed by locale
scripts/
├── deploy.sh             # rsync, venv, restart the tmux session
├── start.sh              # exec python -m src.main (what tmux runs)
├── enrich_figures.py     # Wikidata enrichment for the figure dataset
├── add_figures.py        # stage candidate figures for the roster
├── merge_figures.py      # promote complete staged figures into figures.json
├── add_quotes.py         # harvest sourced quotes from Wikiquote FR into staging
└── merge_quotes.py       # promote complete staged quotes into quotes.json
tests/                    # pytest suite
```

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.
