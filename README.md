# Historical Figures Whisper Bot

Telegram bot serving historical figures. Runs as a long-running **long-polling**
process (no public endpoint required), deployed to a VPS inside a dedicated `tmux`
session. Localized EN/FR.

## Core classes

1. `HistoricalFigure` — a historical figure (name + description).
2. `Database` — holds the historical figures.
3. `Bot` — the Telegram bot: registers command handlers (`/start`, `/help`,
   `/new_figure`) and runs long-polling.

## Local run

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # then fill TELEGRAM_BOT_TOKEN
python -m src.main            # starts long-polling
```

`src/main.py` loads `.env` via `python-dotenv`, so a direct `python -m src.main`
picks up the token without sourcing the shell.

## Tests

```bash
python -m pytest tests/
```

## Deploy (VPS + tmux)

Fill the deployment vars in `.env` (`VPS_USER`, `VPS_HOST`, `VPS_BOT_PATH`,
`SSH_KEY`), then:

```bash
./scripts/deploy.sh
```

`scripts/deploy.sh` rsyncs the code to the VPS, copies `.env`, (re)creates the
venv + installs `requirements.txt`, and restarts the `history-whisper-bot` tmux
session (which runs `scripts/start.sh` → `python -m src.main`, logging to
`logs/app.log`).
