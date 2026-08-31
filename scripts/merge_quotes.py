#!/usr/bin/env python3
"""Promotion : staging → corpus, citations complètes uniquement.

Le prédicat de complétude n'exige délibérément **pas** les deux langues : la
traduction EN est une dette assumée (cf. la spec), et le repli du rendu sert le
français à un lecteur anglophone plutôt que rien. Une entrée doit en revanche
porter un id, un auteur, et le texte *et* la source de sa langue d'origine.

    python -m scripts.merge_quotes --dry-run
    python -m scripts.merge_quotes
"""
import argparse

from scripts.add_quotes import PENDING_PATH, load_json, write_json
from src.database import QUOTES_PATH

LANGUAGES = ("fr", "en")


def missing_parts(entry):
    """Ce qu'il reste à compléter. Liste vide = citation promouvable."""
    parts = []
    if not (entry.get("id") or "").strip():
        parts.append("id")
    if not (entry.get("author") or "").strip():
        parts.append("author")
    lang = entry.get("lang")
    if lang not in LANGUAGES:
        parts.append("lang")
    else:
        for field in (f"text_{lang}", f"source_{lang}"):
            if not (entry.get(field) or "").strip():
                parts.append(field)
    return parts


def is_complete(entry):
    return not missing_parts(entry)


def promote(quotes, pending):
    """Renvoie (corpus augmenté, staging restant, ids promus).

    La déduplication sur l'id est ici et nulle part ailleurs : Database avertit
    d'une collision mais ne peut plus la corriger, et un id dupliqué rendrait
    un deep link partagé ambigu."""
    known = {entry["id"] for entry in quotes}
    promoted, remaining = [], []
    for entry in pending:
        if not is_complete(entry):
            remaining.append(entry)
        elif entry["id"] in known:
            continue          # doublon : abandonné, ni promu ni conservé
        else:
            known.add(entry["id"])
            promoted.append(entry)
    return quotes + promoted, remaining, [entry["id"] for entry in promoted]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true",
                        help="afficher l'état sans rien écrire")
    args = parser.parse_args()

    quotes = load_json(QUOTES_PATH, [])
    pending = load_json(PENDING_PATH, {"quotes": []}).get("quotes", [])

    if not pending:
        print("Staging vide, rien à promouvoir.")
        return

    new_quotes, remaining, promoted = promote(quotes, pending)

    print(f"Prêtes ({len(promoted)}) sur {len(pending)} en staging.")
    if remaining:
        print(f"\nEncore à compléter ({len(remaining)}) :")
        for entry in remaining[:20]:
            print(f"  - {entry.get('author', '?')} : {', '.join(missing_parts(entry))}")
        if len(remaining) > 20:
            print(f"  … et {len(remaining) - 20} autre(s)")

    if args.dry_run:
        print("\n--dry-run : rien écrit.")
        return
    if not promoted:
        print("\nAucune citation complète, rien écrit.")
        return

    write_json(QUOTES_PATH, new_quotes)
    write_json(PENDING_PATH, {"quotes": remaining})
    print(f"\n{len(promoted)} citation(s) promue(s). Corpus : {len(new_quotes)}.")
    print(f"→ Bumper test_corpus_size dans tests/test_database.py à {len(new_quotes)}, puis :")
    print("  ./.venv/bin/python -m pytest tests/")


if __name__ == "__main__":
    main()
