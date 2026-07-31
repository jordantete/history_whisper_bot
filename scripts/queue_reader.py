#!/usr/bin/env python3
"""Lecture de la file de suggestions déposée par /suggest sur le VPS.

Isolé de add_figures.py pour que celui-ci reste testable sans réseau ni SSH.
Réutilise les variables de deploy.sh — une seule description de la cible.
"""
import json
import os
import subprocess
import sys

from dotenv import dotenv_values

QUEUE_FILENAME = "suggestions.json"


def load_env(path=".env"):
    """Config de déploiement depuis .env, complétée par l'environnement."""
    values = dict(dotenv_values(path))
    for key in ("VPS_USER", "VPS_HOST", "VPS_BOT_PATH", "SSH_KEY"):
        if os.environ.get(key):
            values[key] = os.environ[key]
    return values


def build_ssh_command(env):
    user, host = env.get("VPS_USER"), env.get("VPS_HOST")
    if not user or not host:
        sys.exit("VPS_USER et VPS_HOST doivent être définis dans .env")
    bot_path = env.get("VPS_BOT_PATH") or "/root/history_whisper_bot"
    key = env.get("SSH_KEY") or os.path.expanduser("~/.ssh/id_ed25519")
    # '|| true' : une file encore inexistante n'est pas une erreur.
    return ["ssh", "-i", key, f"{user}@{host}",
            f"cat {bot_path}/{QUEUE_FILENAME} 2>/dev/null || true"]


def parse_queue_payload(payload):
    """Noms contenus dans la file. Une file absente, vide ou illisible donne une
    liste vide — jamais une exception : elle n'est qu'une source de noms."""
    if not payload.strip():
        return []
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        print(f"  ! {QUEUE_FILENAME} distant illisible, file ignorée")
        return []
    names = data.get("suggestions", []) if isinstance(data, dict) else []
    return names if isinstance(names, list) else []


def read_remote_queue():
    env = load_env()
    try:
        result = subprocess.run(build_ssh_command(env), capture_output=True,
                                text=True, check=True, timeout=30)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        sys.exit(f"Lecture de la file distante impossible : {e}")
    names = parse_queue_payload(result.stdout)
    print(f"File distante : {len(names)} nom(s).")
    return names
