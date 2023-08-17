import unittest
from unittest.mock import patch, Mock
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