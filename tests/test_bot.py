import os
import unittest
from unittest.mock import patch, Mock, AsyncMock
from telegram.ext import Application
from src.database import Database
from src.bot import Bot


class TestBot(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        patcher = patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "123456:ABC-test-token"})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.mock_database = Mock(spec=Database)
        self.bot = Bot(database=self.mock_database)

    def test_init(self):
        self.assertIsInstance(self.bot.application, Application)
        self.assertEqual(self.bot.database, self.mock_database)

    async def test_start_handler_sends_message(self):
        update = Mock()
        update.effective_chat.id = 42
        context = Mock()
        context.bot.send_message = AsyncMock(return_value=None)

        await self.bot._Bot__start_handler(update, context)

        context.bot.send_message.assert_called_once()

    async def test_new_figure_handler_sends_figure(self):
        figure = Mock()
        figure.name = "Marie Curie"
        figure.description = "Physicist and chemist."
        self.mock_database.get_random_figure.return_value = figure

        update = Mock()
        update.effective_chat.id = 42
        context = Mock()
        context.bot.send_message = AsyncMock(return_value=None)

        await self.bot._Bot__new_figure_handler(update, context)

        context.bot.send_message.assert_called_once()
        _, kwargs = context.bot.send_message.call_args
        self.assertIn("Marie Curie", kwargs["text"])
