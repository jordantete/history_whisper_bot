#!/usr/bin/env python3
"""Promotion : staging → roster, figures complètes uniquement.

Le prédicat de complétude reproduit l'invariant de tests/test_database.py:62-63
(exactement 3 faits par langue) en amont, pour que src/figures.json ne contienne
jamais de figure à moitié rédigée et que la suite de tests reste verte pendant
toute la campagne de rédaction.

    python -m scripts.merge_figures --dry-run
    python -m scripts.merge_figures
"""
import argparse

from scripts.add_figures import FIGURES_PATH, PENDING_PATH, load_json, write_json

REQUIRED_FACTS = 3


def missing_parts(entry):
    """Ce qu'il reste à rédiger. Liste vide = figure promouvable."""
    parts = []
    if not (entry.get("description") or "").strip():
        parts.append("description")
    for key in ("facts_fr", "facts_en"):
        facts = entry.get(key) or []
        if len(facts) != REQUIRED_FACTS:
            parts.append(f"{key} ({len(facts)}/{REQUIRED_FACTS})")
    return parts


def is_complete(entry):
    return not missing_parts(entry)


def promote(figures, pending):
    """Renvoie (roster augmenté, staging restant, noms promus)."""
    promoted = [e for e in pending if is_complete(e)]
    remaining = [e for e in pending if not is_complete(e)]
    return figures + promoted, remaining, [e["name"] for e in promoted]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true",
                        help="afficher l'état sans rien écrire")
    args = parser.parse_args()

    figures = load_json(FIGURES_PATH, [])
    pending = load_json(PENDING_PATH, {"figures": []}).get("figures", [])

    if not pending:
        print("Staging vide, rien à promouvoir.")
        return

    new_figures, remaining, promoted = promote(figures, pending)

    print(f"Prêtes ({len(promoted)}) : {', '.join(promoted) if promoted else '—'}")
    if remaining:
        print(f"\nEncore à rédiger ({len(remaining)}) :")
        for e in remaining:
            print(f"  - {e['name']} : {', '.join(missing_parts(e))}")

    if args.dry_run:
        print("\n--dry-run : rien écrit.")
        return
    if not promoted:
        print("\nAucune figure complète, rien écrit.")
        return

    write_json(FIGURES_PATH, new_figures)
    write_json(PENDING_PATH, {"figures": remaining})
    print(f"\n{len(promoted)} figure(s) promue(s). Roster : {len(new_figures)}.")
    print(f"→ Bumper tests/test_database.py:38 à {len(new_figures)}, puis :")
    print("  python -m pytest tests/")


if __name__ == "__main__":
    main()
