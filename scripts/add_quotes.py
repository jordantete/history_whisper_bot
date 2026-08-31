#!/usr/bin/env python3
"""Collecte : récolte des citations sourcées sur fr.wikiquote.org et les met en
staging pour sélection.

N'écrit JAMAIS dans src/quotes.json — la promotion est le rôle de
scripts/merge_quotes.py, qui n'y admet que des entrées complètes.

Le roster sert d'amorce : 344 noms déjà validés, dont 158 ont une page
Wikiquote FR et 154 au moins une référence, pour 3255 citations candidates.

    python -m scripts.add_quotes --from-roster
    python -m scripts.add_quotes --author "Charlie Munger" --author "Aldous Huxley"
    python -m scripts.add_quotes --from-roster --max-per-author 5
"""
import argparse
import html
import json
import os
import re
import time
import urllib.parse
import urllib.request
from collections import Counter

from src.database import Database, FIGURES_PATH, QUOTES_PATH
from src.utils import Utils

PENDING_PATH = "scripts/pending_quotes.json"
API = "https://fr.wikiquote.org/w/api.php"
USER_AGENT = "history-whisper-bot/1.0 (Telegram bot corpus builder; contact via GitHub)"

# Plafond de l'API MediaWiki pour un client non authentifié.
BATCH_SIZE = 50
# Une citation plus longue ne tient pas dans une carte lisible.
MAX_QUOTE_LENGTH = 600
# Sans plafond, Robespierre (182 réfs) et Nietzsche (110) écrasent le corpus.
MAX_PER_AUTHOR = 3
# Politesse envers un service gratuit — 7 requêtes suffisent pour tout le roster.
REQUEST_DELAY = 1.0

# Sections dont les citations n'ont pas leur place au corpus. Comparaison sur la
# forme normalisée (sans accents, en minuscules) via Utils.normalize_name.
EXCLUDED_SECTIONS = ("citations attribuees", "attribuees", "apocryphe", "a propos")

HEADING = re.compile(r"^=+\s*(.+?)\s*=+\s*$", re.M)


def strip_markup(text: str) -> str:
    """Wikitext → texte nu. Le rendu Telegram est du HTML : tout reliquat de
    balisage wiki y apparaîtrait tel quel."""
    text = re.sub(r"<ref[^>]*/>", "", text)
    text = re.sub(r"<ref[^>]*>.*?</ref>", "", text, flags=re.S)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\{\{\s*w\s*\|[^|}]*\|([^}]*)\}\}", r"\1", text)   # {{w|article|texte}}
    text = re.sub(r"\{\{\s*w\s*\|([^}]*)\}\}", r"\1", text)           # {{w|article}}
    text = re.sub(r"\[\[[^|\]]*\|([^\]]*)\]\]", r"\1", text)          # [[cible|texte]]
    text = re.sub(r"\[\[([^\]]*)\]\]", r"\1", text)                   # [[texte]]
    text = re.sub(r"'''(.*?)'''", r"\1", text, flags=re.S)
    text = re.sub(r"''(.*?)''", r"\1", text, flags=re.S)
    return Database._clean(html.unescape(text))


def iter_templates(wikitext: str):
    """Génère (nom, corps, position) pour chaque template de premier niveau.

    Un compteur d'accolades est nécessaire plutôt qu'une regex : les citations
    contiennent des {{w|…}} imbriqués qu'un motif non récursif couperait au
    premier '}}', tronquant le texte sans rien signaler."""
    index = 0
    while True:
        start = wikitext.find("{{", index)
        if start < 0:
            return
        depth, cursor = 0, start
        while cursor < len(wikitext):
            if wikitext.startswith("{{", cursor):
                depth += 1
                cursor += 2
            elif wikitext.startswith("}}", cursor):
                depth -= 1
                cursor += 2
                if depth == 0:
                    break
            else:
                cursor += 1
        if depth != 0:      # template non refermé : page malformée, on s'arrête
            return
        body = wikitext[start + 2:cursor - 2]
        yield body.split("|", 1)[0].strip(), body, start
        index = cursor


def _split_fields(body: str):
    """Découpe le corps d'un template sur ses '|' de premier niveau. Les '|' à
    l'intérieur d'un [[…]] ou d'un {{…}} imbriqué ne séparent pas des champs.

    La profondeur ne suit que les jetons à DEUX caractères ('{{', '}}', '[[',
    ']]'), jamais une accolade ou un crochet isolé. Un crochet seul et mal
    apparié dans la prose — intervalle mathématique « [0,1[ », artefact de
    transcription « ] » orphelin — désynchroniserait sinon durablement le
    compteur et masquerait le '|' de premier niveau qui sépare réellement les
    champs, laissant fuir le template suivant dans le texte de la citation.
    Les liens externes ('[url texte]') séparent leur libellé par un espace,
    jamais un '|' : un crochet simple n'a donc jamais besoin d'être protégé."""
    parts, depth, current, index = [], 0, [], 0
    while index < len(body):
        two = body[index:index + 2]
        if two in ("{{", "[["):
            depth += 1
            current.append(two)
            index += 2
            continue
        if two in ("}}", "]]"):
            depth = max(0, depth - 1)
            current.append(two)
            index += 2
            continue
        char = body[index]
        if char == "|" and depth == 0:
            parts.append("".join(current))
            current = []
        else:
            current.append(char)
        index += 1
    parts.append("".join(current))
    return parts


def template_field(body: str, field: str):
    """Valeur d'un champ nommé. À défaut, le premier argument positionnel —
    certaines pages écrivent {{Citation|texte}} sans nommer le champ."""
    parts = _split_fields(body)
    for part in parts[1:]:
        if "=" in part:
            key, value = part.split("=", 1)
            if key.strip().lower() == field:
                return value.strip()
    if field == "citation":
        for part in parts[1:]:
            if "=" not in part and part.strip():
                return part.strip()
    return None


def format_ref(body: str) -> str:
    """Ligne de source lisible : « Titre, éditeur, année, p. N ». Vide quand le
    template ne porte rien d'exploitable — la citation est alors traitée comme
    non sourcée."""
    bits = []
    for field, prefix in (("titre", ""), ("source", ""), ("éditeur", ""),
                          ("année", ""), ("page", "p. ")):
        value = template_field(body, field)
        if value:
            cleaned = strip_markup(value)
            if cleaned:
                bits.append(prefix + cleaned)
    return ", ".join(bits)


def _section_at(headings, position: int) -> str:
    """Titre de la section qui contient `position`."""
    current = ""
    for start, title in headings:
        if start > position:
            break
        current = title
    return current


def _is_excluded(section: str) -> bool:
    normalized = Utils.normalize_name(strip_markup(section))
    return any(marker in normalized for marker in EXCLUDED_SECTIONS)


def _following_ref(templates, index: int):
    """Source de la citation d'indice `index` : le premier {{Réf …}} qui suit,
    sauf si une autre citation s'intercale — auquel cas la référence appartient
    à celle-là, pas à celle-ci."""
    for name, body, _ in templates[index + 1:]:
        normalized = Utils.normalize_name(name)
        if normalized.startswith("citation"):
            return None
        if normalized.startswith("ref"):
            return format_ref(body)
    return None


def parse_page(author: str, title: str, wikitext: str, max_per_author: int = MAX_PER_AUTHOR):
    """Extrait les citations retenues d'une page Wikiquote FR.

    Renvoie (entrées de staging, compteur de rejets par motif). Le compteur
    distingue « non sourcé » de « non parsé » pour que le rapport dise la
    couverture réelle plutôt qu'un taux d'échec indifférencié.

    `author` est le nom du roster — c'est lui qui s'affiche sur la carte ;
    `title` est le titre Wikiquote après redirection, qui sert de lien.
    """
    kept, rejected, seen = [], Counter(), set()
    headings = [(match.start(), match.group(1)) for match in HEADING.finditer(wikitext)]
    templates = list(iter_templates(wikitext))

    for index, (name, body, position) in enumerate(templates):
        if Utils.normalize_name(name) != "citation":
            continue
        if len(kept) >= max_per_author:
            break
        if _is_excluded(_section_at(headings, position)):
            rejected["section exclue"] += 1
            continue
        raw = template_field(body, "citation")
        text = strip_markup(raw) if raw else ""
        if not text:
            rejected["non parsé"] += 1
            continue
        source = _following_ref(templates, index)
        if not source:
            rejected["non sourcé"] += 1
            continue
        if len(text) > MAX_QUOTE_LENGTH:
            rejected["trop long"] += 1
            continue
        quote_id = Utils.quote_id(text)
        if quote_id in seen:
            rejected["doublon"] += 1
            continue
        seen.add(quote_id)
        kept.append({
            "id": quote_id,
            "author": author,
            "lang": "fr",
            "text_fr": text,
            "source_fr": source,
            "wikiquote_fr": title,
        })
    return kept, rejected


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


def fetch_pages(titles):
    """wikitext de jusqu'à 50 pages en une requête.

    Renvoie {titre demandé: (titre résolu, wikitext)}. Les redirections sont
    suivies côté API ('Napoléon Bonaparte' → 'Napoléon Ier') : le titre résolu
    est celui du lien Wikiquote, le titre demandé reste le nom du roster."""
    params = {
        "action": "query", "prop": "revisions", "rvprop": "content",
        "rvslots": "main", "redirects": "1", "format": "json",
        "formatversion": "2", "titles": "|".join(titles),
    }
    request = urllib.request.Request(f"{API}?{urllib.parse.urlencode(params)}",
                                     headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=40) as response:
        data = json.load(response)

    query = data.get("query", {})
    # 'normalized' et 'redirects' chaînent : demandé → normalisé → cible.
    alias = {}
    for entry in query.get("normalized", []):
        alias[entry["to"]] = entry["from"]
    for entry in query.get("redirects", []):
        alias[entry["to"]] = alias.get(entry["from"], entry["from"])

    pages = {}
    for page in query.get("pages", []):
        if page.get("missing"):
            continue
        try:
            wikitext = page["revisions"][0]["slots"]["main"]["content"]
        except (KeyError, IndexError):
            continue
        resolved = page["title"]
        pages[alias.get(resolved, resolved)] = (resolved, wikitext)
    return pages


def collect(names, max_per_author=MAX_PER_AUTHOR):
    """Traite une liste de noms. Renvoie (entrées ajoutées, absents, rejets)."""
    corpus_ids = {entry["id"] for entry in load_json(QUOTES_PATH, [])}
    pending = load_json(PENDING_PATH, {"quotes": []}).get("quotes", [])
    known = corpus_ids | {entry["id"] for entry in pending}

    added, missing, rejected = [], [], Counter()
    for start in range(0, len(names), BATCH_SIZE):
        batch = names[start:start + BATCH_SIZE]
        pages = fetch_pages(batch)
        for name in batch:
            if name not in pages:
                missing.append(name)
                continue
            title, wikitext = pages[name]
            kept, page_rejected = parse_page(name, title, wikitext, max_per_author)
            rejected.update(page_rejected)
            for entry in kept:
                if entry["id"] in known:
                    rejected["déjà connu"] += 1
                    continue
                known.add(entry["id"])
                added.append(entry)
        time.sleep(REQUEST_DELAY)

    write_json(PENDING_PATH, {"quotes": pending + added})
    return added, missing, rejected


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from-roster", action="store_true",
                        help="interroger Wikiquote avec les noms de src/figures.json")
    parser.add_argument("--author", action="append", default=[],
                        help="ajouter un auteur nommément (répétable)")
    parser.add_argument("--max-per-author", type=int, default=MAX_PER_AUTHOR,
                        help=f"plafond de citations par auteur (défaut : {MAX_PER_AUTHOR})")
    args = parser.parse_args()

    names = list(args.author)
    if args.from_roster:
        names += [figure["name"] for figure in load_json(FIGURES_PATH, [])]
    if not names:
        parser.error("rien à faire : passer --from-roster ou --author")

    added, missing, rejected = collect(names, args.max_per_author)

    print(f"Retenues : {len(added)}")
    print(f"Sans page Wikiquote : {len(missing)}")
    if rejected:
        print("\nRejets :")
        for motif, count in rejected.most_common():
            print(f"  {count:5d}  {motif}")
    total = len(load_json(PENDING_PATH, {"quotes": []}).get("quotes", []))
    print(f"\nStaging : {total} citation(s) dans {PENDING_PATH}.")
    print("→ Relire et sélectionner, puis : python -m scripts.merge_quotes --dry-run")


if __name__ == "__main__":
    main()
