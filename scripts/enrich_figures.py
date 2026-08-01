#!/usr/bin/env python3
"""Build-time enrichment: fetch bio + portrait from Wikipedia for each figure,
write an enriched src/figures.json, and dump the intros for authoring faits.

Run from the project root:  python -m scripts.enrich_figures
Faits marquants (facts_en/facts_fr) are authored separately, grounded on the
intros dumped to scripts/_intros.json, then merged into figures.json.
"""
import json
import time
import urllib.error
import urllib.parse
import urllib.request

FIGURES_PATH = "src/figures.json"
INTROS_PATH = "scripts/_intros.json"
USER_AGENT = "history-whisper-bot/1.0 (+https://github.com/jordantete/history_whisper_bot)"


class FetchError(Exception):
    """Wikipédia n'a pas pu répondre (throttling, timeout, 5xx). Ne signifie
    JAMAIS que l'article est absent — confondre les deux a déjà produit 40 faux
    rejets, dont Shakespeare et Churchill."""


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
    # Revolution / two worlds
    "Lafayette": {"fr": "Gilbert du Motier de La Fayette", "en": "Gilbert du Motier, Marquis de Lafayette", "wikidata_id": "Q186652"},
    # 2026-07 batch: Revolution & Empire / Ancien Régime / antiquity / science / letters / myths
    "Napoléon Bonaparte": {"fr": "Napoléon Ier", "en": "Napoleon"},
    "Marie-Antoinette": {"fr": "Marie-Antoinette d'Autriche", "en": "Marie Antoinette"},
    "Mirabeau": {"fr": "Honoré-Gabriel Riqueti de Mirabeau", "en": "Honoré Gabriel Riqueti, comte de Mirabeau"},
    "François Ier": {"fr": "François Ier (roi de France)", "en": "Francis I of France"},
    "Catherine de Médicis": {"fr": "Catherine de Médicis", "en": "Catherine de' Medici"},
    "Jeanne d'Arc": {"fr": "Jeanne d'Arc", "en": "Joan of Arc"},
    "Alexandre le Grand": {"fr": "Alexandre le Grand", "en": "Alexander the Great"},
    "Cléopâtre": {"fr": "Cléopâtre VII", "en": "Cleopatra"},  # FR bare title is ambiguous
    "Auguste": {"fr": "Auguste", "en": "Augustus"},
    "Hannibal": {"fr": "Hannibal Barca", "en": "Hannibal"},
    "Néron": {"fr": "Néron", "en": "Nero"},
    "Galilée": {"fr": "Galilée (savant)", "en": "Galileo Galilei"},  # vs the Galilee region
    "Lavoisier": {"fr": "Antoine Lavoisier", "en": "Antoine Lavoisier"},
    "Zola": {"fr": "Émile Zola", "en": "Émile Zola"},
    "Ulysse": {"fr": "Ulysse", "en": "Odysseus"},
    "Achille": {"fr": "Achille", "en": "Achilles"},
    "Méduse": {"fr": "Méduse (mythologie)", "en": "Medusa"},  # vs the jellyfish
    "Orphée": {"fr": "Orphée", "en": "Orpheus"},
    # Psychology (rest) + semiotics (rest) + Sumatra
    "Skinner": {"fr": "Burrhus Frederic Skinner", "en": "B. F. Skinner"},
    "Zimbardo": {"fr": "Philip Zimbardo", "en": "Philip Zimbardo"},
    "John B. Watson": {"fr": "John Broadus Watson", "en": "John B. Watson"},  # vs many other Watsons
    "Peirce": {"fr": "Charles Sanders Peirce", "en": "Charles Sanders Peirce"},
    "Jakobson": {"fr": "Roman Jakobson", "en": "Roman Jakobson"},
    "Greimas": {"fr": "Algirdas Julien Greimas", "en": "Algirdas Julien Greimas"},
    # ---- Lot 2026-07-31 (115 figures) ----
    # Sciences & mathématiques antiques
    "Archimède": {"fr": "Archimède", "en": "Archimedes"},
    "Pythagore": {"fr": "Pythagore", "en": "Pythagoras"},
    "Euclide": {"fr": "Euclide", "en": "Euclid"},
    "Hippocrate": {"fr": "Hippocrate", "en": "Hippocrates"},
    "Ératosthène": {"fr": "Ératosthène", "en": "Eratosthenes"},
    "Ptolémée": {"fr": "Claude Ptolémée", "en": "Ptolemy"},
    # Philosophie moderne
    "Descartes": {"fr": "René Descartes", "en": "René Descartes"},
    "Kant": {"fr": "Emmanuel Kant", "en": "Immanuel Kant"},
    "Nietzsche": {"fr": "Friedrich Nietzsche", "en": "Friedrich Nietzsche"},
    "Marx": {"fr": "Karl Marx", "en": "Karl Marx"},
    "Spinoza": {"fr": "Baruch Spinoza", "en": "Baruch Spinoza"},
    "Hegel": {"fr": "Georg Wilhelm Friedrich Hegel", "en": "Georg Wilhelm Friedrich Hegel"},
    "Érasme": {"fr": "Érasme", "en": "Erasmus"},
    # Renaissance & arts
    "Michel-Ange": {"fr": "Michel-Ange", "en": "Michelangelo"},
    "Raphaël": {"fr": "Raphaël (peintre)", "en": "Raphael"},  # vs l'archange
    "Botticelli": {"fr": "Sandro Botticelli", "en": "Sandro Botticelli"},
    "Vermeer": {"fr": "Johannes Vermeer", "en": "Johannes Vermeer"},
    "Dürer": {"fr": "Albrecht Dürer", "en": "Albrecht Dürer"},
    "Monet": {"fr": "Claude Monet", "en": "Claude Monet"},
    "Rodin": {"fr": "Auguste Rodin", "en": "Auguste Rodin"},
    "Le Caravage": {"fr": "Le Caravage", "en": "Caravaggio"},
    # Musique
    "Mozart": {"fr": "Wolfgang Amadeus Mozart", "en": "Wolfgang Amadeus Mozart"},
    "Beethoven": {"fr": "Ludwig van Beethoven", "en": "Ludwig van Beethoven"},
    "Jean-Sébastien Bach": {"fr": "Jean-Sébastien Bach", "en": "Johann Sebastian Bach"},
    "Chopin": {"fr": "Frédéric Chopin", "en": "Frédéric Chopin"},
    "Wagner": {"fr": "Richard Wagner", "en": "Richard Wagner"},
    "Vivaldi": {"fr": "Antonio Vivaldi", "en": "Antonio Vivaldi"},
    "Verdi": {"fr": "Giuseppe Verdi", "en": "Giuseppe Verdi"},
    # Sciences modernes
    "Einstein": {"fr": "Albert Einstein", "en": "Albert Einstein"},
    "Copernic": {"fr": "Nicolas Copernic", "en": "Nicolaus Copernicus"},
    "Kepler": {"fr": "Johannes Kepler", "en": "Johannes Kepler"},
    "Mendeleïev": {"fr": "Dmitri Mendeleïev", "en": "Dmitri Mendeleev"},
    "Mendel": {"fr": "Gregor Mendel", "en": "Gregor Mendel"},
    "Tesla": {"fr": "Nikola Tesla", "en": "Nikola Tesla"},
    "Edison": {"fr": "Thomas Edison", "en": "Thomas Edison"},
    "Turing": {"fr": "Alan Turing", "en": "Alan Turing"},
    "Fleming": {"fr": "Alexander Fleming", "en": "Alexander Fleming"},
    "Ampère": {"fr": "André-Marie Ampère", "en": "André-Marie Ampère"},
    # Explorateurs
    "Christophe Colomb": {"fr": "Christophe Colomb", "en": "Christopher Columbus"},
    "Magellan": {"fr": "Fernand de Magellan", "en": "Ferdinand Magellan"},
    "Vasco de Gama": {"fr": "Vasco de Gama", "en": "Vasco da Gama"},
    "Amundsen": {"fr": "Roald Amundsen", "en": "Roald Amundsen"},
    "Shackleton": {"fr": "Ernest Shackleton", "en": "Ernest Shackleton"},
    "Champlain": {"fr": "Samuel de Champlain", "en": "Samuel de Champlain"},
    "Livingstone": {"fr": "David Livingstone", "en": "David Livingstone"},
    # Monde arabo-musulman
    "Averroès": {"fr": "Averroès", "en": "Averroes"},
    "Avicenne": {"fr": "Avicenne", "en": "Avicenna"},
    "Ibn Khaldoun": {"fr": "Ibn Khaldoun", "en": "Ibn Khaldun"},
    "Soliman le Magnifique": {"fr": "Soliman le Magnifique", "en": "Suleiman the Magnificent"},
    "Haroun al-Rachid": {"fr": "Haroun ar-Rachid", "en": "Harun al-Rashid"},
    # Médiéval européen
    "Guillaume le Conquérant": {"fr": "Guillaume le Conquérant", "en": "William the Conqueror"},
    "Aliénor d'Aquitaine": {"fr": "Aliénor d'Aquitaine", "en": "Eleanor of Aquitaine"},
    "Saint Louis": {"fr": "Louis IX", "en": "Louis IX of France"},
    "Thomas d'Aquin": {"fr": "Thomas d'Aquin", "en": "Thomas Aquinas"},
    "Frédéric Barberousse": {"fr": "Frédéric Barberousse", "en": "Frederick Barbarossa"},
    "Philippe Auguste": {"fr": "Philippe II Auguste", "en": "Philip II of France"},
    # Russie
    "Pierre le Grand": {"fr": "Pierre Ier le Grand", "en": "Peter the Great"},  # titre nu = homonymie
    "Catherine II": {"fr": "Catherine II", "en": "Catherine the Great"},
    "Tolstoï": {"fr": "Léon Tolstoï", "en": "Leo Tolstoy"},
    "Dostoïevski": {"fr": "Fiodor Dostoïevski", "en": "Fyodor Dostoevsky"},
    "Lénine": {"fr": "Vladimir Ilitch Lénine", "en": "Vladimir Lenin"},
    "Raspoutine": {"fr": "Grigori Raspoutine", "en": "Grigori Rasputin"},
    # Japon
    "Meiji": {"fr": "Mutsuhito", "en": "Emperor Meiji"},
    # Inde
    "Gandhi": {"fr": "Mohandas Karamchand Gandhi", "en": "Mahatma Gandhi"},
    "Bouddha": {"fr": "Siddhartha Gautama", "en": "Gautama Buddha"},
    # Afrique & Égypte antique
    "Mansa Moussa": {"fr": "Mansa Moussa", "en": "Mansa Musa"},
    "Chaka Zulu": {"fr": "Chaka Zoulou", "en": "Shaka"},  # "Chaka" nu = page de renvoi
    "Ramsès II": {"fr": "Ramsès II", "en": "Ramesses II"},
    "Hatchepsout": {"fr": "Hatchepsout", "en": "Hatshepsut"},
    "Néfertiti": {"fr": "Néfertiti", "en": "Nefertiti"},
    # Amériques
    "Moctezuma": {"fr": "Moctezuma II", "en": "Moctezuma II"},
    "Cortés": {"fr": "Hernán Cortés", "en": "Hernán Cortés"},
    "Lincoln": {"fr": "Abraham Lincoln", "en": "Abraham Lincoln"},
    "Bolívar": {"fr": "Simón Bolívar", "en": "Simón Bolívar"},
    # XXe siècle
    "Churchill": {"fr": "Winston Churchill", "en": "Winston Churchill"},
    "De Gaulle": {"fr": "Charles de Gaulle", "en": "Charles de Gaulle"},
    "Roosevelt": {"fr": "Franklin Delano Roosevelt", "en": "Franklin D. Roosevelt"},
    "Martin Luther King": {"fr": "Martin Luther King", "en": "Martin Luther King Jr."},
    # Réforme & religion
    "Luther": {"fr": "Martin Luther", "en": "Martin Luther"},
    "Calvin": {"fr": "Jean Calvin", "en": "John Calvin"},
    "Saint Augustin": {"fr": "Augustin d'Hippone", "en": "Augustine of Hippo"},
    # Lettres
    "Shakespeare": {"fr": "William Shakespeare", "en": "William Shakespeare"},
    "Cervantès": {"fr": "Miguel de Cervantès", "en": "Miguel de Cervantes"},
    "Dante": {"fr": "Dante Alighieri", "en": "Dante Alighieri"},
    "Homère": {"fr": "Homère", "en": "Homer"},
    "Virgile": {"fr": "Virgile", "en": "Virgil"},
    "Baudelaire": {"fr": "Charles Baudelaire", "en": "Charles Baudelaire"},
    "Rimbaud": {"fr": "Arthur Rimbaud", "en": "Arthur Rimbaud"},
    # Mythes
    "Thésée": {"fr": "Thésée", "en": "Theseus"},
    "Persée": {"fr": "Persée", "en": "Perseus"},
    "Pandore": {"fr": "Pandore", "en": "Pandora"},
    "Sisyphe": {"fr": "Sisyphe", "en": "Sisyphus"},
    "Minotaure": {"fr": "Minotaure", "en": "Minotaur"},
    "Antigone": {"fr": "Antigone (mythologie)", "en": "Antigone"},  # titre nu = homonymie illustrée
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


def fetch_summary_strict(lang, title):
    """(extract, image_url) depuis l'endpoint REST summary.

    Un 404 est une réponse valide : l'article n'existe pas, on renvoie
    ("", None). Toute autre défaillance lève FetchError — l'appelant doit
    pouvoir réessayer plutôt que conclure à une absence."""
    url = f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{urllib.parse.quote(title)}"
    try:
        d = _get_json(url)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return "", None
        raise FetchError(f"summary {lang}/{title}: HTTP {e.code}") from e
    except Exception as e:  # noqa: BLE001 — réseau, timeout, JSON illisible
        raise FetchError(f"summary {lang}/{title}: {e}") from e
    extract = d.get("extract", "")
    # On garde l'URL de vignette générée par Wikimedia telle quelle (taille déjà
    # valide et servie — en réécrire la largeur produit des 400). Repli sur
    # l'original faute de vignette ; le fallback send_photo→send_message du
    # runtime couvre les images trop lourdes.
    image = (d.get("thumbnail") or d.get("originalimage") or {}).get("source")
    return extract, image


def fetch_intro_strict(lang, title):
    """Intro en texte brut (pour grounder les faits). Mêmes règles d'erreur que
    fetch_summary_strict."""
    params = urllib.parse.urlencode({
        "action": "query", "format": "json", "prop": "extracts",
        "exintro": "1", "explaintext": "1", "redirects": "1", "titles": title,
    })
    url = f"https://{lang}.wikipedia.org/w/api.php?{params}"
    try:
        pages = _get_json(url)["query"]["pages"]
        # L'accès au payload reste DANS le try : une réponse valide mais vide
        # ({"query": {"pages": {}}}) ferait lever StopIteration à next(), que le
        # wrapper indulgent ne rattraperait pas — l'exception traverserait
        # jusqu'à main() et interromprait le parcours du roster.
        return next(iter(pages.values())).get("extract", "")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return ""
        raise FetchError(f"intro {lang}/{title}: HTTP {e.code}") from e
    except Exception as e:  # noqa: BLE001
        raise FetchError(f"intro {lang}/{title}: {e}") from e


def fetch_summary(lang, title):
    """Variante indulgente : journalise et poursuit. main() parcourt tout le
    roster et ne doit pas s'arrêter sur une figure."""
    try:
        return fetch_summary_strict(lang, title)
    except FetchError as e:
        print(f"  ! {e}")
        return "", None


def fetch_intro(lang, title):
    """Variante indulgente, cf. fetch_summary."""
    try:
        return fetch_intro_strict(lang, title)
    except FetchError as e:
        print(f"  ! {e}")
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
