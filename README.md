# Historical Figures Whisper Bot

Telegram bot serving historical figures. Runs as a long-running **long-polling**
process (no public endpoint required), deployed to a VPS inside a dedicated `tmux`
session. Localized EN/FR.

## Core classes

1. `HistoricalFigure` — a historical figure (name + description).
2. `Database` — holds the historical figures.
3. `Bot` — the Telegram bot: registers command handlers (`/start`, `/help`,
   `/random`, `/today`, `/subscribe`, `/unsubscribe`, `/feedback`) plus the
   inline-button callback handler, and runs long-polling.

## Commands

| Command | Description |
|---|---|
| `/start` | Welcome message + inline keyboard (Random / Today / Help) |
| `/help` | List available commands |
| `/random` | A random historical figure |
| `/today` | The historical figure of the day |
| `/subscribe` | Daily historical figure (coming soon — stub) |
| `/unsubscribe` | Stop the daily figure (coming soon — stub) |
| `/feedback` | Suggest a figure or send feedback (`/feedback <text>`) |

These commands must also be declared to **@BotFather** via `/setcommands` so
they show up in the Telegram command menu (EN and FR lists below):

EN:
```
start - Welcome & how it works
help - List available commands
random - A random historical figure
today - The historical figure of the day
subscribe - Daily historical figure (coming soon)
unsubscribe - Stop the daily figure (coming soon)
feedback - Suggest a figure or send feedback
```

FR:
```
start - Bienvenue & fonctionnement
help - Liste des commandes
random - Une figure historique au hasard
today - La figure historique du jour
subscribe - Figure historique quotidienne (bientôt)
unsubscribe - Arrêter la figure quotidienne (bientôt)
feedback - Proposer une figure ou envoyer un retour
```

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
