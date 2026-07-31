#!/usr/bin/env python3
"""Collecte : vérifie des candidats contre la contrainte dure (article FR + EN
+ portrait) et les met en staging pour rédaction.

N'écrit JAMAIS dans src/figures.json — la promotion est le rôle de
scripts/merge_figures.py, qui n'y admet que des figures complètes. Le roster
reste ainsi conforme à l'invariant des 3+3 faits, et la suite de tests verte
pendant toute la durée de la rédaction.

    python -m scripts.add_figures "Vauban" "Lyautey"
    python -m scripts.add_figures --from-queue
    python -m scripts.add_figures --force "Philippe Auguste"
"""
import argparse
import json
import os
import time

from src.utils import Utils
from scripts.enrich_figures import (
    OVERRIDES, FetchError, fetch_intro_strict, fetch_summary_strict, resolve_titles,
)

FIGURES_PATH = "src/figures.json"
PENDING_PATH = "scripts/pending_figures.json"
INTROS_PATH = "scripts/_intros.json"

RETRY_ATTEMPTS = 3
RETRY_BASE_DELAY = 2.0
# Délai entre deux figures. Wikipédia throttle au-delà : c'est ce throttling,
# avalé silencieusement, qui avait produit 40 faux rejets.
FIGURE_DELAY = 0.3


def load_json(path, default):
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path, data):
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, path)


def known_names(figures, pending):
    """Noms déjà connus : roster promu + staging en cours de rédaction."""
    return [f["name"] for f in figures] + [p["name"] for p in pending]


def with_retry(fn, *args, attempts=RETRY_ATTEMPTS, base_delay=RETRY_BASE_DELAY):
    """Réessaie sur FetchError avec un backoff. Relève l'erreur après le dernier
    essai : l'appelant doit signaler « à relancer », jamais « rejetée »."""
    for attempt in range(1, attempts + 1):
        try:
            return fn(*args)
        except FetchError:
            if attempt == attempts:
                raise
            time.sleep(base_delay * attempt)


def build_entry(name):
    """Vérifie une figure et construit son entrée de staging.

    Renvoie (entry, None) si la contrainte dure est satisfaite, (None, motif)
    si une réponse valide de Wikipédia ne la satisfait pas.
    Lève FetchError si le réseau a empêché de trancher.
    """
    titles = resolve_titles(name, OVERRIDES)
    bio_fr, img_fr = with_retry(fetch_summary_strict, "fr", titles["fr"])
    bio_en, img_en = with_retry(fetch_summary_strict, "en", titles["en"])
    image = img_fr or img_en

    missing = [label for label, value in
               (("bio_fr", bio_fr), ("bio_en", bio_en), ("portrait", image)) if not value]
    if missing:
        return None, ", ".join(missing)

    entry = {
        "name": name,
        "description": "",
        "bio_fr": bio_fr,
        "bio_en": bio_en,
        "image_url": image,
        "facts_fr": [],
        "facts_en": [],
    }
    if titles["wikidata_id"]:
        entry["wikidata_id"] = titles["wikidata_id"]
    return entry, None


def collect(names, force=False):
    """Traite une liste de noms. Renvoie (added, skipped, rejected, retryable)."""
    figures = load_json(FIGURES_PATH, [])
    pending_doc = load_json(PENDING_PATH, {"figures": []})
    pending = pending_doc.get("figures", [])
    intros = load_json(INTROS_PATH, {})
    known = known_names(figures, pending)

    added, skipped, rejected, retryable = [], [], [], []

    for name in names:
        near = [k for k in known if Utils.names_match(name, k)]
        if near and not force:
            skipped.append((name, near))
            continue

        # Toute itération à partir d'ici touche l'API : espacer inconditionnellement,
        # y compris après un rejet ou une erreur. C'est la cadence qui protège du
        # throttling, pas le fait d'avoir réussi.
        try:
            entry, reason = build_entry(name)
            if entry is None:
                rejected.append((name, reason))
                continue

            # Deuxième résolution volontaire : build_entry garde une signature
            # d'un seul argument, et resolve_titles n'est qu'une lecture de dict.
            titles = resolve_titles(name, OVERRIDES)
            intros[name] = {
                "fr": with_retry(fetch_intro_strict, "fr", titles["fr"]),
                "en": with_retry(fetch_intro_strict, "en", titles["en"]),
            }
            pending.append(entry)
            known.append(name)
            added.append(name)
            print(f"  + {name}")
        except FetchError as e:
            retryable.append((name, str(e)))
        finally:
            time.sleep(FIGURE_DELAY)

    if added:
        write_json(PENDING_PATH, {"figures": pending})
        write_json(INTROS_PATH, intros)

    return added, skipped, rejected, retryable


def report(added, skipped, rejected, retryable, pending_total):
    print(f"\n{len(added)} figure(s) mise(s) en staging. Staging : {pending_total}.")
    if skipped:
        print(f"\nÉcartées, déjà connues ({len(skipped)}) :")
        for name, near in skipped:
            print(f"  - {name} → proche de {', '.join(near)}")
        print("  Si c'est un faux positif, relancer ce nom avec --force.")
    if rejected:
        print(f"\nRejetées, contrainte dure non satisfaite ({len(rejected)}) :")
        for name, reason in rejected:
            print(f"  ✗ {name} : {reason} manquant")
    if retryable:
        print(f"\nÀ RELANCER — Wikipédia n'a pas répondu ({len(retryable)}) :")
        for name, err in retryable:
            print(f"  ? {name} : {err}")
        print("  Ce ne sont PAS des rejets. Relancer la commande sur ces noms.")
    if added:
        print("\nÉtape suivante : rédiger description + 3 faits FR + 3 faits EN")
        print(f"dans {PENDING_PATH}, en s'appuyant sur {INTROS_PATH},")
        print("puis : python -m scripts.merge_figures --dry-run")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("names", nargs="*", help="noms de figures à ajouter")
    parser.add_argument("--from-queue", action="store_true",
                        help="drainer suggestions.json depuis le VPS")
    parser.add_argument("--force", action="store_true",
                        help="ajouter malgré un rapprochement avec un nom connu")
    args = parser.parse_args()

    names = list(args.names)
    if args.from_queue:
        from scripts.queue_reader import read_remote_queue
        names += read_remote_queue()

    if not names:
        parser.error("aucun nom fourni (passer des noms ou --from-queue)")

    added, skipped, rejected, retryable = collect(names, force=args.force)
    pending_total = len(load_json(PENDING_PATH, {"figures": []}).get("figures", []))
    report(added, skipped, rejected, retryable, pending_total)


if __name__ == "__main__":
    main()
