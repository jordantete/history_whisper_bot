#!/usr/bin/env bash
# start.sh — lance le bot en avant-plan (appelé par la session tmux dans deploy.sh).
# Le bot tourne en continu en long-polling ; la sortie est journalisée dans
# logs/app.log tout en restant visible dans le pane tmux.

set -euo pipefail
cd "$(dirname "$0")/.."

mkdir -p logs

if [[ -f .env ]]; then
    set -a
    source .env
    set +a
fi

echo "Démarrage history-whisper-bot à $(date -u +%Y-%m-%dT%H:%M:%SZ) ..." >> logs/app.log
# Long-polling en continu ; toute la sortie va dans logs/app.log (suivre avec tail -f).
exec ./.venv/bin/python -m src.main >> logs/app.log 2>&1
