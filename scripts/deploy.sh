#!/usr/bin/env bash
# deploy.sh — synchronise le code local vers le VPS et (re)lance le bot dans tmux.
#
# Config attendue dans .env (à la racine du projet) :
#   VPS_USER, VPS_HOST                (obligatoires)
#   VPS_BOT_PATH   (défaut /root/history_whisper_bot)
#   SSH_KEY        (défaut ~/.ssh/id_ed25519)
#   TELEGRAM_BOT_TOKEN                 (utilisé par le bot au runtime)
#
# Le .env est copié sur le VPS (il porte le token Telegram lu par src/main.py).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
ENV_FILE="$PROJECT_DIR/.env"

if [[ -f "$ENV_FILE" ]]; then
    set -a
    source "$ENV_FILE"
    set +a
else
    echo "ERREUR : $ENV_FILE introuvable. Crée-le depuis .env.example (VPS_USER, VPS_HOST, TELEGRAM_BOT_TOKEN)." >&2
    exit 1
fi

: "${VPS_USER:?VPS_USER non défini dans .env}"
: "${VPS_HOST:?VPS_HOST non défini dans .env}"
: "${VPS_BOT_PATH:=/root/history_whisper_bot}"
: "${SSH_KEY:=$HOME/.ssh/id_ed25519}"
TMUX_SESSION="history-whisper-bot"

SSH_CMD="ssh -i $SSH_KEY $VPS_USER@$VPS_HOST"

echo "=== Déploiement vers $VPS_HOST:$VPS_BOT_PATH ==="

# 1. Dossier cible
$SSH_CMD "mkdir -p $VPS_BOT_PATH"

# 2. Sync du code (exclut secrets, venv, état runtime, caches)
rsync -av --delete \
    --exclude '.env' \
    --exclude '.venv' \
    --exclude 'logs/' \
    --exclude '.pytest_cache' \
    --exclude '.ruff_cache' \
    --exclude '__pycache__' \
    --exclude '.git' \
    -e "ssh -i $SSH_KEY" \
    "$PROJECT_DIR/" "$VPS_USER@$VPS_HOST:$VPS_BOT_PATH/"

# 3. Sync du .env séparément (exclu par sécurité du rsync ci-dessus)
rsync -av -e "ssh -i $SSH_KEY" "$ENV_FILE" "$VPS_USER@$VPS_HOST:$VPS_BOT_PATH/.env"

# 4. (Re)crée le venv et installe les deps sur le VPS
$SSH_CMD "cd $VPS_BOT_PATH && \
    { [ -d .venv ] || python3 -m venv .venv; } && \
    ./.venv/bin/pip install --quiet --upgrade pip && \
    ./.venv/bin/pip install --quiet -r requirements.txt"

# 5. Redémarre la session tmux
$SSH_CMD "tmux kill-session -t $TMUX_SESSION 2>/dev/null || true; \
    tmux new-session -d -s $TMUX_SESSION 'cd $VPS_BOT_PATH && ./scripts/start.sh'"

echo "=== Déploiement terminé ==="
echo "Logs   : $SSH_CMD 'tail -f $VPS_BOT_PATH/logs/app.log'"
echo "Session: $SSH_CMD 'tmux attach -t $TMUX_SESSION'   (détacher : Ctrl-b puis d)"
