import unittest
from unittest.mock import patch, Mock
from telegram.ext import Application
from src.database import Database
from src.bot import Bot

class TestBot(unittest.TestCase):
    def setUp(self):
        self.mock_database = Mock(spec=Database)
        self.bot = Bot(database=self.mock_database)

    def test_init(self):
        self.assertIsInstance(self.bot.application, Application)
        self.assertEqual(self.bot.database, self.mock_database)
    
    @patch('bot.Update')
    @patch('bot.ContextTypes')
    async def test_start_handler(self, mock_context_types, mock_update):
        # Mocks
        mock_context = Mock()
        mock_context.bot.send_message.return_value = None
        mock_update.return_value = mock_context

        # Call the handler
        await self.bot._Bot__start_handler(mock_update, mock_context)

        # Assertions
        mock_context.bot.send_message.assert_called_once()

    # TODO: Write Similar tests for other handlers