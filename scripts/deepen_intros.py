#!/usr/bin/env python3
"""Approfondit les intros trop minces : la bio (endpoint REST summary) et
l'intro dumpée pour la rédaction des faits (`exintro=1`) viennent du même
chapeau. Quand ce chapeau est court, les deux se recouvrent presque
entièrement et il ne reste rien pour écrire trois faits distincts de la bio.

Pour chaque figure en staging pas encore entièrement rédigée, et chaque
langue, si marge = len(intro) - len(bio) est sous MARGIN_THRESHOLD, va
chercher le corps complet de l'article (au lieu du seul chapeau) et
remplace l'intro — jamais si le texte récupéré est plus court que l'existant.

    python -m scripts.deepen_intros --dry-run   # liste les couples à approfondir
    python -m scripts.deepen_intros             # réécrit scripts/_intros.json
    python -m scripts.deepen_intros --threshold 800            # seuil ponctuel
    python -m scripts.deepen_intros --names "Copernic" "Fleming"  # cible nommée,
    # ignore la marge : sert les figures où la matière est épuisée malgré une
    # marge au-dessus du seuil (la longueur ne peut pas détecter ça).
"""
import argparse
import time

from scripts.add_figures import PENDING_PATH, load_json, write_json
from scripts.enrich_figures import OVERRIDES, FetchError, fetch_article_strict, resolve_titles

INTROS_PATH = "scripts/_intros.json"
MARGIN_THRESHOLD = 300
MAX_CHARS = 8000
# Délai entre deux figures, comme le reste du pipeline : Wikipédia throttle
# les requêtes concurrentes, ce qui a déjà été mal interprété comme "l'article
# n'existe pas".
FIGURE_DELAY = 0.3


def margin(intro, bio):
    """Longueur de l'intro moins longueur de la bio. None traité comme chaîne
    vide des deux côtés, pour ne jamais planter sur une figure incomplète."""
    return len(intro or "") - len(bio or "")


def is_authored(fig):
    """Une figure est entièrement rédigée quand les deux langues ont leurs 3
    faits marquants."""
    return len(fig.get("facts_fr") or []) >= 3 and len(fig.get("facts_en") or []) >= 3


def needs_deepening(fig, margin_value, threshold=MARGIN_THRESHOLD):
    """Une figure déjà entièrement rédigée n'a plus besoin d'être approfondie,
    quelle que soit sa marge — on ne retouche pas des faits déjà écrits."""
    if is_authored(fig):
        return False
    return margin_value < threshold


def deepen_pending(pending, intros, dry_run=False, threshold=MARGIN_THRESHOLD, names=None):
    """Parcourt les figures en staging pas encore rédigées et approfondit les
    intros trop minces. Mute `intros` en place (sauf en dry-run, où rien n'est
    ni récupéré ni écrit). Un FetchError sur une figure laisse son intro
    intacte et n'interrompt pas le parcours des suivantes.

    `threshold` remplace MARGIN_THRESHOLD pour cet appel — la marge reste une
    heuristique de longueur, jamais un jugement sur le contenu.

    `names`, si fourni, restreint le parcours à ces figures et approfondit
    chacune de leurs langues sans regarder la marge : sert les cas où la marge
    est au-dessus du seuil mais la matière est épuisée quand même (ex.
    Copernic, Fleming — la longueur ne peut pas détecter ça, seul un humain
    le peut). La règle de non-régression (jamais de remplacement par un texte
    plus court) et le passage par resolve_titles/OVERRIDES s'appliquent
    identiquement, sans dérogation.

    Renvoie (deepened, still_thin) :
      - deepened   = [(name, lang, marge_avant, marge_après), ...]
      - still_thin = [(name, lang, marge), ...] (couples non remplacés, que ce
        soit faute de dépasser le seuil ou faute de texte plus long)
    """
    deepened, still_thin = [], []
    target_names = set(names) if names else None

    for fig in pending:
        name = fig["name"]
        if target_names is not None and name not in target_names:
            continue
        if is_authored(fig):
            continue
        titles = resolve_titles(name, OVERRIDES)
        fig_intros = intros.get(name, {})
        forced = target_names is not None

        for lang in ("fr", "en"):
            bio = fig.get(f"bio_{lang}", "")
            intro = fig_intros.get(lang, "")
            m = margin(intro, bio)
            if not forced and not needs_deepening(fig, m, threshold=threshold):
                continue

            if dry_run:
                still_thin.append((name, lang, m))
                continue

            try:
                article = fetch_article_strict(lang, titles[lang], max_chars=MAX_CHARS)
            except FetchError as e:
                print(f"  ! {name}[{lang}]: {e}")
                still_thin.append((name, lang, m))
                time.sleep(FIGURE_DELAY)
                continue

            if len(article) > len(intro):
                fig_intros[lang] = article
                intros[name] = fig_intros
                deepened.append((name, lang, m, margin(article, bio)))
            else:
                still_thin.append((name, lang, m))
            time.sleep(FIGURE_DELAY)

    return deepened, still_thin


def report(deepened, still_thin, dry_run, threshold=MARGIN_THRESHOLD, forced=False):
    scope = "ciblé(s) par --names" if forced else f"sous le seuil ({threshold})"
    if dry_run:
        print(f"{len(still_thin)} couple(s) figure-langue {scope} seraient approfondis :")
        for name, lang, m in still_thin:
            print(f"  - {name}[{lang}] : marge {m}")
        return

    print(f"{len(deepened)} couple(s) approfondi(s) :")
    for name, lang, before, after in deepened:
        print(f"  + {name}[{lang}] : marge {before} -> {after}")

    if still_thin:
        label = "n'ont pas été remplacés (texte pas plus long)" if forced else f"restent sous le seuil ({threshold})"
        print(f"\n{len(still_thin)} couple(s) {label} :")
        for name, lang, m in still_thin:
            print(f"  - {name}[{lang}] : marge {m}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true",
                        help="lister les couples à approfondir sans les récupérer")
    parser.add_argument("--threshold", type=int, default=MARGIN_THRESHOLD,
                        help=f"marge sous laquelle une intro est jugée trop mince (défaut {MARGIN_THRESHOLD})")
    parser.add_argument("--names", nargs="+", default=None,
                        help="restreindre à ces figures et approfondir chaque langue "
                             "quelle que soit la marge (la longueur ne détecte pas "
                             "toujours une matière épuisée, ex. Copernic, Fleming)")
    args = parser.parse_args()

    pending_doc = load_json(PENDING_PATH, {"figures": []})
    pending = pending_doc.get("figures", [])
    intros = load_json(INTROS_PATH, {})

    deepened, still_thin = deepen_pending(
        pending, intros, dry_run=args.dry_run, threshold=args.threshold, names=args.names,
    )

    if not args.dry_run and deepened:
        write_json(INTROS_PATH, intros)

    report(deepened, still_thin, args.dry_run, threshold=args.threshold, forced=bool(args.names))


if __name__ == "__main__":
    main()
