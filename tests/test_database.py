import unittest
from unittest.mock import patch
from datetime import date
import json
import tempfile
import os
from src.database import Database, FIGURES_PATH
from src.historical_figure import HistoricalFigure
from src.quote import Quote
from src.utils import Utils

class TestDatabase(unittest.TestCase):
    def setUp(self):
        self.database = Database()

    def test_get_all_figures(self):
        figures = self.database.get_all_figures()
        self.assertIsInstance(figures, list)
        self.assertTrue(all(isinstance(figure, HistoricalFigure) for figure in figures))

    @patch('random.randint', return_value=0)
    def test_get_random_figure(self, mock_randint):
        figure = self.database.get_random_figure()
        self.assertIsInstance(figure, HistoricalFigure)

    def test_get_figure_of_the_day_is_deterministic(self):
        day = date(2026, 1, 3)
        first = self.database.get_figure_of_the_day(day)
        second = self.database.get_figure_of_the_day(day)
        self.assertIs(first, second)

    def test_get_figure_of_the_day_indexes_by_day_of_year(self):
        figures = self.database.get_all_figures()
        # 2026-01-03 -> tm_yday == 3 -> 3 % len(figures)
        expected = figures[3 % len(figures)]
        self.assertIs(self.database.get_figure_of_the_day(date(2026, 1, 3)), expected)

    def test_loads_full_roster_from_json(self):
        figures = self.database.get_all_figures()
        self.assertEqual(len(figures), 344)
        self.assertTrue(all(f.name and f.description for f in figures))

    def test_raw_json_prose_is_free_of_line_breaks(self):
        """Bios and facts land verbatim in the Telegram caption, so a newline
        renders as a broken card (the bug seen on Freud and Périclès). Database
        ._clean() scrubs this at load time; this guards the source data itself,
        which is also what the enrichment script writes."""
        with open(FIGURES_PATH, encoding="utf-8") as f:
            raw = json.load(f)
        for item in raw:
            name = item["name"]
            for key in ("description", "bio_fr", "bio_en"):
                text = item.get(key)
                if text:
                    self.assertNotIn("\n", text, f"{name}.{key}")
                    self.assertEqual(text, text.strip(), f"{name}.{key}")
            for key in ("facts_fr", "facts_en"):
                for i, fact in enumerate(item.get(key) or []):
                    self.assertNotIn("\n", fact, f"{name}.{key}[{i}]")
                    self.assertEqual(fact, fact.strip(), f"{name}.{key}[{i}]")

    def test_every_figure_has_three_facts_in_both_languages(self):
        for figure in self.database.get_all_figures():
            self.assertEqual(len(figure.facts_fr), 3, f"{figure.name}.facts_fr")
            self.assertEqual(len(figure.facts_en), 3, f"{figure.name}.facts_en")

    def test_every_figure_has_both_bios(self):
        for figure in self.database.get_all_figures():
            self.assertTrue(figure.bio_fr, f"{figure.name}.bio_fr")
            self.assertTrue(figure.bio_en, f"{figure.name}.bio_en")

    def test_roster_names_are_unique(self):
        """merge_figures.promote() has no membership check, and --force
        bypasses the only dedup (at collect time). A true duplicate staged
        via --force would otherwise reach src/figures.json unnoticed and
        get served twice by /today."""
        names = [figure.name for figure in self.database.get_all_figures()]
        self.assertEqual(len(names), len(set(names)))

        normalized = [Utils.normalize_name(name) for name in names]
        self.assertEqual(len(normalized), len(set(normalized)))

    def test_clean_collapses_whitespace_but_keeps_non_breaking_spaces(self):
        self.assertEqual(Database._clean("\n\n\nSigmund Freud, né le 6 mai"),
                         "Sigmund Freud, né le 6 mai")
        self.assertEqual(Database._clean("a Greek statesman \nand general"),
                         "a Greek statesman and general")
        self.assertEqual(Database._clean("Ier\xa0siècle\xa0av. J.-C."), "Ier\xa0siècle\xa0av. J.-C.")

    def test_loads_enriched_and_minimal_entries(self):
        data = [
            {"name": "Rich", "description": "d", "image_url": "http://img",
             "bio_fr": "bio fr", "bio_en": "bio en", "facts_fr": ["f1"], "facts_en": ["e1"]},
            {"name": "Minimal", "description": "only desc"},
        ]
        fd, path = tempfile.mkstemp(suffix=".json")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f)
        try:
            db = Database(figures_path=path)
        finally:
            os.remove(path)
        figures = db.get_all_figures()
        self.assertEqual(figures[0].image_url, "http://img")
        self.assertEqual(figures[0].bio_fr, "bio fr")
        self.assertEqual(figures[0].facts_en, ["e1"])
        self.assertIsNone(figures[1].image_url)
        self.assertEqual(figures[1].facts_fr, [])
    def test_get_figure_by_slug_finds_a_figure(self):
        database = Database()
        figure = database.get_figure_by_slug("george-sand")
        self.assertIsNotNone(figure)
        self.assertEqual(figure.name, "George Sand")

    def test_get_figure_by_slug_returns_none_when_absent(self):
        database = Database()
        self.assertIsNone(database.get_figure_by_slug("figure-qui-nexiste-pas"))

    def test_get_figure_by_slug_ignores_case_and_accents(self):
        database = Database()
        self.assertIsNotNone(database.get_figure_by_slug("GEORGE-SAND"))
        self.assertIsNotNone(database.get_figure_by_slug("George Sand"))

    def test_get_figure_by_slug_handles_empty_payload(self):
        database = Database()
        self.assertIsNone(database.get_figure_by_slug(""))

    def test_slug_collision_keeps_the_first_figure_and_warns(self):
        """Deux noms produisant le même slug ne doivent pas s'écraser en
        silence : le premier gagne et la collision est tracée."""
        payload = [
            {"name": "Lucrèce", "description": "d"},
            {"name": "LUCRECE", "description": "d"},
        ]
        handle, path = tempfile.mkstemp(suffix=".json")
        os.close(handle)
        self.addCleanup(os.unlink, path)
        with open(path, "w", encoding="utf-8") as file:
            json.dump(payload, file)
        with patch("src.database.LOGGER.warning") as warning:
            database = Database(path)
        self.assertEqual(database.get_figure_by_slug("lucrece").name, "Lucrèce")
        warning.assert_called_once()

    def _database_with_quotes(self, entries):
        """Database adossée à un corpus de citations jetable. Le roster réel est
        conservé : seul le corpus varie d'un test à l'autre."""
        fd, path = tempfile.mkstemp(suffix=".json")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(entries, f, ensure_ascii=False)
        self.addCleanup(lambda: os.path.exists(path) and os.unlink(path))
        return Database(quotes_path=path)

    def test_loads_quotes_from_json(self):
        database = self._database_with_quotes([{
            "id": "abc1234567", "author": "Napoléon Ier", "lang": "fr",
            "text_fr": "Les vraies conquêtes sont celles que l'on fait sur l'ignorance.",
            "source_fr": "La campagne d'Égypte, Belin, 2018, p. 111",
            "wikiquote_fr": "Napoléon Ier",
        }])
        quotes = database.get_all_quotes()
        self.assertEqual(len(quotes), 1)
        self.assertIsInstance(quotes[0], Quote)
        self.assertEqual(quotes[0].author, "Napoléon Ier")
        self.assertEqual(quotes[0].wikiquote_fr, "Napoléon Ier")

    def test_quote_prose_is_cleaned_at_load_time(self):
        """Même raison que pour les bios : le texte atterrit verbatim dans le
        message, donc un retour à la ligne casse la carte."""
        database = self._database_with_quotes([{
            "id": "abc1234567", "author": "Voltaire", "lang": "fr",
            "text_fr": "  Le mieux est\n l'ennemi   du bien.  ",
            "source_fr": " Dictionnaire philosophique,\n 1770 ",
        }])
        quote = database.get_all_quotes()[0]
        self.assertEqual(quote.text_fr, "Le mieux est l'ennemi du bien.")
        self.assertEqual(quote.source_fr, "Dictionnaire philosophique, 1770")

    def test_get_quote_of_the_day_indexes_by_day_of_year(self):
        entries = [{"id": f"{i:010x}", "author": f"A{i}", "lang": "fr",
                    "text_fr": f"Citation {i}", "source_fr": "S"} for i in range(5)]
        database = self._database_with_quotes(entries)
        # 2026-01-03 -> tm_yday == 3 -> 3 % 5
        self.assertIs(database.get_quote_of_the_day(date(2026, 1, 3)),
                      database.get_all_quotes()[3])

    def test_get_quote_of_the_day_is_deterministic(self):
        entries = [{"id": f"{i:010x}", "author": f"A{i}", "lang": "fr",
                    "text_fr": f"Citation {i}", "source_fr": "S"} for i in range(5)]
        database = self._database_with_quotes(entries)
        day = date(2026, 1, 3)
        self.assertIs(database.get_quote_of_the_day(day), database.get_quote_of_the_day(day))

    def test_get_quote_by_id(self):
        database = self._database_with_quotes([
            {"id": "abc1234567", "author": "Voltaire", "lang": "fr",
             "text_fr": "Le mieux est l'ennemi du bien.", "source_fr": "S"}])
        self.assertEqual(database.get_quote_by_id("abc1234567").author, "Voltaire")
        self.assertIsNone(database.get_quote_by_id("0000000000"))

    def test_empty_corpus_is_a_supported_state(self):
        """État du dépôt entre la livraison du code et le premier lot promu :
        le bot doit servir la figure seule, pas planter."""
        database = self._database_with_quotes([])
        self.assertEqual(database.get_all_quotes(), [])
        self.assertIsNone(database.get_quote_of_the_day(date(2026, 1, 3)))
        self.assertIsNone(database.get_random_quote())
        self.assertIsNone(database.get_quote_by_id("abc1234567"))

    def test_missing_corpus_file_is_a_supported_state(self):
        database = Database(quotes_path="src/quotes-does-not-exist.json")
        self.assertEqual(database.get_all_quotes(), [])
        self.assertIsNone(database.get_quote_of_the_day(date(2026, 1, 3)))

    def test_duplicate_quote_ids_keep_the_first_and_warn(self):
        """merge_quotes.promote() n'a pas de contrôle d'appartenance, comme
        merge_figures. Un doublon promu ne doit pas rendre un deep link ambigu."""
        database = self._database_with_quotes([
            {"id": "abc1234567", "author": "Premier", "lang": "fr", "text_fr": "T", "source_fr": "S"},
            {"id": "abc1234567", "author": "Second", "lang": "fr", "text_fr": "T", "source_fr": "S"},
        ])
        self.assertEqual(database.get_quote_by_id("abc1234567").author, "Premier")

    def test_corpus_ids_are_unique(self):
        ids = [quote.id for quote in Database().get_all_quotes()]
        self.assertEqual(len(ids), len(set(ids)))

    def test_corpus_size(self):
        """Compteur en dur, à bumper à chaque lot promu — même convention que
        test_loads_full_roster_from_json pour le roster."""
        self.assertEqual(len(Database().get_all_quotes()), 200)
