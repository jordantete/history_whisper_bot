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

    async def test_subscribe_handler_acknowledges(self):
        update, context = make_update(), make_context()
        await self.bot._Bot__subscribe_handler(update, context)
        context.bot.send_message.assert_called_once()

    async def test_unsubscribe_handler_acknowledges(self):
        update, context = make_update(), make_context()
        await self.bot._Bot__unsubscribe_handler(update, context)
        context.bot.send_message.assert_called_once()

    async def test_feedback_without_text_prompts(self):
        update, context = make_update(), make_context()
        context.args = []
        await self.bot._Bot__feedback_handler(update, context)
        context.bot.send_message.assert_called_once()
        _, kwargs = context.bot.send_message.call_args
        self.assertEqual(kwargs["chat_id"], update.effective_chat.id)

    async def test_feedback_with_owner_forwards_and_thanks(self):
        update, context = make_update(), make_context()
        context.args = ["Add", "Ada", "Lovelace"]
        with patch.dict(os.environ, {"OWNER_CHAT_ID": "999"}):
            await self.bot._Bot__feedback_handler(update, context)
        self.assertEqual(context.bot.send_message.call_count, 2)
        forwarded_call = context.bot.send_message.call_args_list[0]
        self.assertEqual(forwarded_call.kwargs["chat_id"], "999")
        self.assertIn("Ada Lovelace", forwarded_call.kwargs["text"])

    async def test_feedback_without_owner_still_thanks(self):
        update, context = make_update(), make_context()
        context.args = ["hello"]
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("OWNER_CHAT_ID", None)
            await self.bot._Bot__feedback_handler(update, context)
        context.bot.send_message.assert_called_once()
        self.assertEqual(context.bot.send_message.call_args.kwargs["chat_id"], update.effective_chat.id)

    async def test_feedback_owner_send_failure_still_thanks(self):
        update, context = make_update(), make_context()
        context.args = ["hello"]
        context.bot.send_message = AsyncMock(side_effect=[Exception("boom"), None])
        with patch.dict(os.environ, {"OWNER_CHAT_ID": "999"}):
            await self.bot._Bot__feedback_handler(update, context)
        self.assertEqual(context.bot.send_message.call_count, 2)
        thanks_call = context.bot.send_message.call_args_list[1]
        self.assertEqual(thanks_call.kwargs["chat_id"], update.effective_chat.id)

    async def test_button_random_sends_figure_and_answers(self):
        figure = Mock()
        figure.name = "Marie Curie"
        figure.description = "Physicist."
        self.mock_database.get_random_figure.return_value = figure
        update, context = make_update(), make_context()
        update.callback_query = Mock()
        update.callback_query.data = "random"
        update.callback_query.answer = AsyncMock()

        await self.bot._Bot__button_handler(update, context)

        update.callback_query.answer.assert_awaited_once()
        context.bot.send_message.assert_called_once()
        self.assertIn("Marie Curie", context.bot.send_message.call_args.kwargs["text"])

    async def test_button_today_sends_figure_and_answers(self):
        figure = Mock()
        figure.name = "Leonardo da Vinci"
        figure.description = "Polymath."
        self.mock_database.get_figure_of_the_day.return_value = figure
        update, context = make_update(), make_context()
        update.callback_query = Mock()
        update.callback_query.data = "today"
        update.callback_query.answer = AsyncMock()

        await self.bot._Bot__button_handler(update, context)

        update.callback_query.answer.assert_awaited_once()
        context.bot.send_message.assert_called_once()
        self.assertIn("Leonardo da Vinci", context.bot.send_message.call_args.kwargs["text"])

    async def test_button_help_sends_help(self):
        update, context = make_update(language_code="fr"), make_context()
        update.callback_query = Mock()
        update.callback_query.data = "help"
        update.callback_query.answer = AsyncMock()

        await self.bot._Bot__button_handler(update, context)

        update.callback_query.answer.assert_awaited_once()
        self.assertIn("/today", context.bot.send_message.call_args.kwargs["text"])

    def test_register_handlers_registers_all(self):
        self.bot.register_handlers()
        handlers = self.bot.application.handlers[0]
        self.assertEqual(len(handlers), 8)  # 7 commands + 1 callback query
