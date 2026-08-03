import unittest
from unittest.mock import patch
from datetime import date
import json
import tempfile
import os
from src.database import Database, FIGURES_PATH
from src.historical_figure import HistoricalFigure
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
        self.assertEqual(len(figures), 319)
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