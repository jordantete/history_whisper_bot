#!/usr/bin/env python3
"""Build-time enrichment: fetch bio + portrait from Wikipedia for each figure,
write an enriched src/figures.json, and dump the intros for authoring faits.

Run from the project root:  python -m scripts.enrich_figures
Faits marquants (facts_en/facts_fr) are authored separately, grounded on the
intros dumped to scripts/_intros.json, then merged into figures.json.
"""
import json
import time
import urllib.parse
import urllib.request

FIGURES_PATH = "src/figures.json"
INTROS_PATH = "scripts/_intros.json"
USER_AGENT = "history-whisper-bot/1.0 (contact: [redacted])"

# name -> {"fr": title, "en": title, "wikidata_id": id} for ambiguous/legendary names.
OVERRIDES = {
    # Ambiguous / legendary (disambiguation control)
    "Aristide": {"fr": "Aristide le Juste", "en": "Aristides", "wikidata_id": "Q184960"},
    "Francis Bacon": {"fr": "Francis Bacon (philosophe)", "en": "Francis Bacon", "wikidata_id": "Q37388"},
    "Sadi Carnot": {"fr": "Sadi Carnot (physicien)", "en": "Nicolas Léonard Sadi Carnot", "wikidata_id": "Q188905"},
    "Lucrèce": {"fr": "Lucrèce", "en": "Lucretius", "wikidata_id": "Q189441"},
    "Bourbon": {"fr": "Maison de Bourbon", "en": "House of Bourbon", "wikidata_id": "Q216901"},
    "Scaramouche": {"fr": "Scaramouche (personnage)", "en": "Scaramouche", "wikidata_id": "Q1988917"},
    "Icare et Dédale": {"fr": "Icare", "en": "Icarus"},
    # Full-name / correct-title resolution (avoid disambiguation pages & cross-lang titles)
    "Colbert": {"fr": "Jean-Baptiste Colbert", "en": "Jean-Baptiste Colbert"},
    "De Lesseps": {"fr": "Ferdinand de Lesseps", "en": "Ferdinand de Lesseps"},
    "De Vinci": {"fr": "Léonard de Vinci", "en": "Leonardo da Vinci"},
    "César": {"fr": "Jules César", "en": "Julius Caesar"},
    "Richelieu": {"fr": "Armand Jean du Plessis de Richelieu", "en": "Cardinal Richelieu"},
    "Fouché": {"fr": "Joseph Fouché", "en": "Joseph Fouché"},
    "Ivan le Terrible": {"fr": "Ivan le Terrible", "en": "Ivan the Terrible"},
    "Ivan Kriloff": {"fr": "Ivan Krylov", "en": "Ivan Krylov"},
    "Plutarque": {"fr": "Plutarque", "en": "Plutarch"},
    "Parménide": {"fr": "Parménide", "en": "Parmenides"},
    "Héraclite": {"fr": "Héraclite", "en": "Heraclitus"},
    "Cicéron": {"fr": "Cicéron", "en": "Cicero"},
    "Kennedy": {"fr": "John Fitzgerald Kennedy", "en": "John F. Kennedy"},
    "Eisenhower": {"fr": "Dwight D. Eisenhower", "en": "Dwight D. Eisenhower"},
    "Barnum": {"fr": "Phineas Taylor Barnum", "en": "P. T. Barnum"},
    "Bismarck": {"fr": "Otto von Bismarck", "en": "Otto von Bismarck"},
    "Henri IV": {"fr": "Henri IV (roi de France)", "en": "Henry IV of France"},
    "Jaurès": {"fr": "Jean Jaurès", "en": "Jean Jaurès"},
    # Wrong-entity bios detected during faits authoring (disambiguation in one language)
    "Prométhée": {"fr": "Prométhée", "en": "Prometheus"},
    "Machiavel": {"fr": "Nicolas Machiavel", "en": "Niccolò Machiavelli"},
    "Mazarin": {"fr": "Jules Mazarin", "en": "Cardinal Mazarin"},
    "Socrate": {"fr": "Socrate", "en": "Socrates"},
    "Ovide": {"fr": "Ovide", "en": "Ovid"},
    "Hercule": {"fr": "Hercule", "en": "Hercules"},
    "Platon": {"fr": "Platon", "en": "Plato"},
    "La Pérouse": {"fr": "Jean-François de La Pérouse", "en": "Jean-François de Galaup, comte de Lapérouse"},
    "Cromwell": {"fr": "Oliver Cromwell", "en": "Oliver Cromwell"},
    "Planck": {"fr": "Max Planck", "en": "Max Planck"},
    "Musset": {"fr": "Alfred de Musset", "en": "Alfred de Musset"},
    "Maurice de Saxe": {"fr": "Maurice de Saxe", "en": "Maurice de Saxe"},
    "Velázquez": {"fr": "Diego Vélasquez", "en": "Diego Velázquez"},
    "Goya": {"fr": "Francisco de Goya", "en": "Francisco Goya"},
    # Top-tier additional subjects (China / Revolution / Victorian / semiotics)
    "Cixi": {"fr": "Cixi", "en": "Empress Dowager Cixi"},  # vs the Zhejiang city
    "Tchang Kaï-chek": {"fr": "Tchang Kaï-chek", "en": "Chiang Kai-shek"},  # accented FR transliteration
    "Danton": {"fr": "Georges Jacques Danton", "en": "Georges Danton"},
    "Saint-Just": {"fr": "Louis Antoine de Saint-Just", "en": "Louis Antoine de Saint-Just"},
    "Marat": {"fr": "Jean-Paul Marat", "en": "Jean-Paul Marat"},
    "Sieyès": {"fr": "Emmanuel-Joseph Sieyès", "en": "Emmanuel Joseph Sieyès"},
    "Lazare Carnot": {"fr": "Lazare Nicolas Marguerite Carnot", "en": "Lazare Carnot"},  # NOT Sadi Carnot (already present)
    "Victoria": {"fr": "Victoria (reine du Royaume-Uni)", "en": "Queen Victoria"},
    "Darwin": {"fr": "Charles Darwin", "en": "Charles Darwin"},
    "Dickens": {"fr": "Charles Dickens", "en": "Charles Dickens"},
    "Faraday": {"fr": "Michael Faraday", "en": "Michael Faraday"},
    "Nightingale": {"fr": "Florence Nightingale", "en": "Florence Nightingale"},
    # Greek antiquity: Peloponnesian War actors + sea-monster myths
    "Périclès": {"fr": "Périclès", "en": "Pericles"},
    "Thucydide": {"fr": "Thucydide", "en": "Thucydides"},
    "Alcibiade": {"fr": "Alcibiade", "en": "Alcibiades"},
    "Lysandre": {"fr": "Lysandre", "en": "Lysander"},
    "Scylla": {"fr": "Scylla (monstre)", "en": "Scylla"},  # legendary entry, like Prométhée/Hercule
    "Charybde": {"fr": "Charybde", "en": "Charybdis"},
    # Revolution (rest) + Victorian engineers (rest)
    "Barras": {"fr": "Paul Barras", "en": "Paul Barras"},
    "Tallien": {"fr": "Jean-Lambert Tallien", "en": "Jean-Lambert Tallien"},
    "Babeuf": {"fr": "Gracchus Babeuf", "en": "François-Noël Babeuf"},  # EN/FR titles differ
    "Hébert": {"fr": "Jacques-René Hébert", "en": "Jacques Hébert"},
    "Couthon": {"fr": "Georges Couthon", "en": "Georges Couthon"},
    "Brunel": {"fr": "Isambard Kingdom Brunel", "en": "Isambard Kingdom Brunel"},  # NOT Marc Isambard Brunel (father)
    "Stephenson": {"fr": "George Stephenson", "en": "George Stephenson"},  # NOT Robert Stephenson (son)
    # China Tier B + bench (Three Kingdoms / Ming / antiquity / Qing)
    "Zhu Yuanzhang": {"fr": "Zhu Yuanzhang", "en": "Hongwu Emperor"},  # titled by birth name in FR
    "Kangxi": {"fr": "Kangxi", "en": "Kangxi Emperor"},
    "Yongle": {"fr": "Ming Chengzu", "en": "Yongle Emperor"},  # FR "Yongle" is a disambiguation page
    "Laozi": {"fr": "Lao Tseu", "en": "Laozi"},
    # Psychology (rest) + semiotics (rest) + Sumatra
    "Skinner": {"fr": "Burrhus Frederic Skinner", "en": "B. F. Skinner"},
    "Zimbardo": {"fr": "Philip Zimbardo", "en": "Philip Zimbardo"},
    "John B. Watson": {"fr": "John Broadus Watson", "en": "John B. Watson"},  # vs many other Watsons
    "Peirce": {"fr": "Charles Sanders Peirce", "en": "Charles Sanders Peirce"},
    "Jakobson": {"fr": "Roman Jakobson", "en": "Roman Jakobson"},
    "Greimas": {"fr": "Algirdas Julien Greimas", "en": "Algirdas Julien Greimas"},
}


def resolve_titles(name, overrides):
    o = overrides.get(name, {})
    return {
        "fr": o.get("fr", name),
        "en": o.get("en", name),
        "wikidata_id": o.get("wikidata_id"),
    }


def _get_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)


def fetch_summary(lang, title):
    """Return (extract, image_url) from the REST summary endpoint, or ('', None)."""
    url = f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{urllib.parse.quote(title)}"
    try:
        d = _get_json(url)
    except Exception as e:  # noqa: BLE001 — build tool, log and continue
        print(f"  ! summary {lang}/{title}: {e}")
        return "", None
    extract = d.get("extract", "")
    # Use the Wikimedia-generated thumbnail URL as-is (already a valid, small, served
    # size — rewriting its width yields 400s). Fall back to the original only when no
    # thumbnail exists; the runtime send_photo→send_message fallback covers oversize.
    image = (d.get("thumbnail") or d.get("originalimage") or {}).get("source")
    return extract, image


def fetch_intro(lang, title):
    """Return the full plain-text intro (for grounding faits), or ''."""
    params = urllib.parse.urlencode({
        "action": "query", "format": "json", "prop": "extracts",
        "exintro": "1", "explaintext": "1", "redirects": "1", "titles": title,
    })
    url = f"https://{lang}.wikipedia.org/w/api.php?{params}"
    try:
        pages = _get_json(url)["query"]["pages"]
        return next(iter(pages.values())).get("extract", "")
    except Exception as e:  # noqa: BLE001
        print(f"  ! intro {lang}/{title}: {e}")
        return ""


def main():
    with open(FIGURES_PATH, "r", encoding="utf-8") as f:
        figures = json.load(f)

    intros = {}
    for fig in figures:
        name = fig["name"]
        titles = resolve_titles(name, OVERRIDES)
        if titles["wikidata_id"]:
            fig["wikidata_id"] = titles["wikidata_id"]
        bio_fr, img_fr = fetch_summary("fr", titles["fr"])
        bio_en, img_en = fetch_summary("en", titles["en"])
        if bio_fr:
            fig["bio_fr"] = bio_fr
        if bio_en:
            fig["bio_en"] = bio_en
        image = img_fr or img_en
        if image:
            fig["image_url"] = image
        intros[name] = {
            "fr": fetch_intro("fr", titles["fr"]),
            "en": fetch_intro("en", titles["en"]),
        }
        print(f"{name}: bio_fr={'Y' if bio_fr else '-'} bio_en={'Y' if bio_en else '-'} img={'Y' if image else '-'}")
        time.sleep(0.3)

    with open(FIGURES_PATH, "w", encoding="utf-8") as f:
        json.dump(figures, f, ensure_ascii=False, indent=2)
        f.write("\n")
    with open(INTROS_PATH, "w", encoding="utf-8") as f:
        json.dump(intros, f, ensure_ascii=False, indent=2)

    missing = [fig["name"] for fig in figures if not fig.get("image_url")]
    print(f"\nDone. {len(figures)} figures. Missing image: {missing}")


if __name__ == "__main__":
    main()
