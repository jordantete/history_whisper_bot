import unittest
from unittest.mock import patch
from datetime import date
import json
import tempfile
import os
from src.database import Database
from src.historical_figure import HistoricalFigure

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
        self.assertEqual(len(figures), 136)
        self.assertTrue(all(f.name and f.description for f in figures))

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