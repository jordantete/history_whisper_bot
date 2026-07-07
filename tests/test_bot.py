import os
import unittest
from unittest.mock import patch, Mock, AsyncMock
from telegram.ext import Application
from src.database import Database
from src.bot import Bot


def make_update(language_code="en", chat_id=42, username="alice", user_id=7):
    update = Mock()
    update.effective_chat.id = chat_id
    update.effective_user.language_code = language_code
    update.effective_user.username = username
    update.effective_user.id = user_id
    return update


def make_context():
    context = Mock()
    context.bot.send_message = AsyncMock(return_value=None)
    context.args = []
    return context


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

    def test_locale_detection(self):
        self.assertEqual(self.bot._locale(make_update(language_code="fr-FR")), "fr")
        self.assertEqual(self.bot._locale(make_update(language_code="en")), "en")

    async def test_start_handler_sends_message_with_buttons(self):
        update, context = make_update(), make_context()
        await self.bot._Bot__start_handler(update, context)
        context.bot.send_message.assert_called_once()
        _, kwargs = context.bot.send_message.call_args
        self.assertIn("reply_markup", kwargs)

    async def test_help_handler_localized(self):
        update, context = make_update(language_code="fr"), make_context()
        await self.bot._Bot__help_handler(update, context)
        context.bot.send_message.assert_called_once()
        _, kwargs = context.bot.send_message.call_args
        self.assertIn("/today", kwargs["text"])

    async def test_random_handler_sends_figure(self):
        figure = Mock(name="Marie Curie", description="Physicist and chemist.")
        figure.name = "Marie Curie"
        figure.description = "Physicist and chemist."
        self.mock_database.get_random_figure.return_value = figure
        update, context = make_update(), make_context()

        await self.bot._Bot__random_handler(update, context)

        context.bot.send_message.assert_called_once()
        _, kwargs = context.bot.send_message.call_args
        self.assertIn("Marie Curie", kwargs["text"])

    async def test_today_handler_uses_figure_of_the_day(self):
        figure = Mock()
        figure.name = "Leonardo da Vinci"
        figure.description = "Polymath."
        self.mock_database.get_figure_of_the_day.return_value = figure
        update, context = make_update(), make_context()

        await self.bot._Bot__today_handler(update, context)

        self.mock_database.get_figure_of_the_day.assert_called_once()
        _, kwargs = context.bot.send_message.call_args
        self.assertIn("Leonardo da Vinci", kwargs["text"])
