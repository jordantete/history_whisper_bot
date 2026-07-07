import unittest
from unittest.mock import patch
from datetime import date
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