import os
import re
import html
import unittest
from unittest.mock import patch, Mock, AsyncMock
from telegram import ForceReply
from telegram.error import TelegramError
from telegram.ext import Application, ConversationHandler, ApplicationHandlerStop, TypeHandler, AIORateLimiter
from src.database import Database
from src.bot import Bot, FEEDBACK_WAITING
from src.historical_figure import HistoricalFigure


def visible_len(html_str):
    """Length of the text Telegram counts against the caption limit: HTML tags
    are stripped and entities decoded back to single characters."""
    return len(html.unescape(re.sub(r"<[^>]+>", "", html_str)))


def make_update(language_code="en", chat_id=42, username="alice", user_id=7, chat_type="private"):
    update = Mock()
    update.effective_chat.id = chat_id
    update.effective_chat.type = chat_type
    update.effective_user.language_code = language_code
    update.effective_user.username = username
    update.effective_user.id = user_id
    return update


def make_context():
    context = Mock()
    context.bot.send_message = AsyncMock(return_value=None)
    context.bot.send_photo = AsyncMock(return_value=None)
    context.bot.send_chat_action = AsyncMock(return_value=None)
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

    async def test_random_handler_sends_photo(self):
        figure = HistoricalFigure(name="Marie Curie", description="d", image_url="http://img", bio_en="Physicist and chemist.")
        self.mock_database.get_random_figure.return_value = figure
        update, context = make_update(), make_context()
        await self.bot._Bot__random_handler(update, context)
        context.bot.send_photo.assert_called_once()
        self.assertEqual(context.bot.send_photo.call_args.kwargs["photo"], "http://img")
        self.assertIn("Marie Curie", context.bot.send_photo.call_args.kwargs["caption"])

    async def test_today_handler_sends_photo(self):
        figure = HistoricalFigure(name="Leonardo da Vinci", description="d", image_url="http://img", bio_en="Polymath.")
        self.mock_database.get_figure_of_the_day.return_value = figure
        update, context = make_update(), make_context()
        await self.bot._Bot__today_handler(update, context)
        self.mock_database.get_figure_of_the_day.assert_called_once()
        self.assertIn("Leonardo da Vinci", context.bot.send_photo.call_args.kwargs["caption"])

    async def test_send_figure_without_image_uses_message(self):
        figure = HistoricalFigure(name="No Image", description="desc", bio_fr="bio fr")
        update, context = make_update(language_code="fr"), make_context()
        await self.bot._send_figure(update, context, figure)
        context.bot.send_message.assert_called_once()
        self.assertIn("bio fr", context.bot.send_message.call_args.kwargs["text"])
        context.bot.send_photo.assert_not_called()

    async def test_send_figure_renders_facts_for_locale(self):
        figure = HistoricalFigure(
            name="V", description="d", image_url="http://img",
            bio_fr="bio fr", facts_fr=["fait un", "fait deux"],
        )
        update, context = make_update(language_code="fr"), make_context()
        await self.bot._send_figure(update, context, figure)
        caption = context.bot.send_photo.call_args.kwargs["caption"]
        self.assertIn("Faits marquants", caption)
        self.assertIn("• fait un", caption)

    async def test_send_figure_falls_back_to_message_on_photo_error(self):
        figure = HistoricalFigure(name="Big Img", description="d", image_url="http://img", bio_en="A bio.")
        update, context = make_update(), make_context()
        context.bot.send_photo = AsyncMock(side_effect=TelegramError("Photo too big"))
        await self.bot._send_figure(update, context, figure)
        context.bot.send_photo.assert_called_once()
        context.bot.send_message.assert_called_once()
        self.assertIn("Big Img", context.bot.send_message.call_args.kwargs["text"])

    async def test_subscribe_handler_acknowledges(self):
        update, context = make_update(), make_context()
        await self.bot._Bot__subscribe_handler(update, context)
        context.bot.send_message.assert_called_once()

    async def test_unsubscribe_handler_acknowledges(self):
        update, context = make_update(), make_context()
        await self.bot._Bot__unsubscribe_handler(update, context)
        context.bot.send_message.assert_called_once()

    async def test_feedback_entry_without_text_asks_with_force_reply(self):
        update, context = make_update(), make_context()
        context.args = []
        result = await self.bot._Bot__feedback_entry(update, context)
        self.assertEqual(result, FEEDBACK_WAITING)
        context.bot.send_message.assert_called_once()
        _, kwargs = context.bot.send_message.call_args
        self.assertEqual(kwargs["chat_id"], update.effective_chat.id)
        self.assertIsInstance(kwargs["reply_markup"], ForceReply)

    async def test_feedback_entry_with_text_forwards_and_ends(self):
        update, context = make_update(), make_context()
        context.args = ["Add", "Ada", "Lovelace"]
        with patch.dict(os.environ, {"OWNER_CHAT_ID": "999"}):
            result = await self.bot._Bot__feedback_entry(update, context)
        self.assertEqual(result, ConversationHandler.END)
        self.assertEqual(context.bot.send_message.call_count, 2)
        forwarded_call = context.bot.send_message.call_args_list[0]
        self.assertEqual(forwarded_call.kwargs["chat_id"], "999")
        self.assertIn("Ada Lovelace", forwarded_call.kwargs["text"])

    async def test_feedback_entry_without_owner_still_thanks(self):
        update, context = make_update(), make_context()
        context.args = ["hello"]
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("OWNER_CHAT_ID", None)
            await self.bot._Bot__feedback_entry(update, context)
        context.bot.send_message.assert_called_once()
        self.assertEqual(context.bot.send_message.call_args.kwargs["chat_id"], update.effective_chat.id)

    async def test_feedback_owner_send_failure_still_thanks(self):
        update, context = make_update(), make_context()
        context.args = ["hello"]
        context.bot.send_message = AsyncMock(side_effect=[Exception("boom"), None])
        with patch.dict(os.environ, {"OWNER_CHAT_ID": "999"}):
            await self.bot._Bot__feedback_entry(update, context)
        self.assertEqual(context.bot.send_message.call_count, 2)
        thanks_call = context.bot.send_message.call_args_list[1]
        self.assertEqual(thanks_call.kwargs["chat_id"], update.effective_chat.id)

    async def test_feedback_receive_forwards_and_ends(self):
        update, context = make_update(), make_context()
        update.message = Mock()
        update.message.text = "Please add Ada Lovelace"
        with patch.dict(os.environ, {"OWNER_CHAT_ID": "999"}):
            result = await self.bot._Bot__feedback_receive(update, context)
        self.assertEqual(result, ConversationHandler.END)
        self.assertEqual(context.bot.send_message.call_count, 2)
        self.assertIn("Ada Lovelace", context.bot.send_message.call_args_list[0].kwargs["text"])

    async def test_button_random_sends_photo_and_answers(self):
        figure = HistoricalFigure(name="Marie Curie", description="d", image_url="http://img", bio_en="Physicist.")
        self.mock_database.get_random_figure.return_value = figure
        update, context = make_update(), make_context()
        update.callback_query = Mock()
        update.callback_query.data = "random"
        update.callback_query.answer = AsyncMock()
        await self.bot._Bot__button_handler(update, context)
        update.callback_query.answer.assert_awaited_once()
        self.assertIn("Marie Curie", context.bot.send_photo.call_args.kwargs["caption"])

    async def test_button_today_sends_photo_and_answers(self):
        figure = HistoricalFigure(name="Leonardo da Vinci", description="d", image_url="http://img", bio_en="Polymath.")
        self.mock_database.get_figure_of_the_day.return_value = figure
        update, context = make_update(), make_context()
        update.callback_query = Mock()
        update.callback_query.data = "today"
        update.callback_query.answer = AsyncMock()
        await self.bot._Bot__button_handler(update, context)
        update.callback_query.answer.assert_awaited_once()
        self.assertIn("Leonardo da Vinci", context.bot.send_photo.call_args.kwargs["caption"])

    async def test_button_help_sends_help(self):
        update, context = make_update(language_code="fr"), make_context()
        update.callback_query = Mock()
        update.callback_query.data = "help"
        update.callback_query.answer = AsyncMock()

        await self.bot._Bot__button_handler(update, context)

        update.callback_query.answer.assert_awaited_once()
        self.assertIn("/today", context.bot.send_message.call_args.kwargs["text"])

    def test_figure_bio_locale_and_fallback(self):
        f = HistoricalFigure(name="V", description="desc", bio_fr="fr", bio_en="en")
        self.assertEqual(self.bot._figure_bio(f, "fr"), "fr")
        self.assertEqual(self.bot._figure_bio(f, "en"), "en")
        f2 = HistoricalFigure(name="V", description="desc", bio_en="en")  # no fr
        self.assertEqual(self.bot._figure_bio(f2, "fr"), "en")
        f3 = HistoricalFigure(name="V", description="desc")  # no bio at all
        self.assertEqual(self.bot._figure_bio(f3, "fr"), "desc")

    def test_figure_facts_locale_and_fallback(self):
        f = HistoricalFigure(name="V", description="d", facts_fr=["a"], facts_en=["b"])
        self.assertEqual(self.bot._figure_facts(f, "fr"), ["a"])
        self.assertEqual(self.bot._figure_facts(f, "en"), ["b"])
        f2 = HistoricalFigure(name="V", description="d")
        self.assertEqual(self.bot._figure_facts(f2, "fr"), [])

    def test_build_caption_html_with_and_without_facts(self):
        cap = Bot._build_caption("Voltaire", "A bio.", ["f1", "f2"], "Highlights")
        self.assertIn("<b>Voltaire</b>", cap)
        self.assertIn("<i>A bio.</i>", cap)
        self.assertIn("<b>Highlights</b>", cap)
        self.assertIn("• f1", cap)
        no_facts = Bot._build_caption("Voltaire", "A bio.", [], "Highlights")
        self.assertNotIn("Highlights", no_facts)
        self.assertIn("<b>Voltaire</b>", no_facts)

    def test_build_caption_escapes_html_in_content(self):
        cap = Bot._build_caption("A & B <x>", "bio & <i>hi</i>", ["m & n"], "Head <>")
        self.assertIn("<b>A &amp; B &lt;x&gt;</b>", cap)
        self.assertIn("bio &amp; &lt;i&gt;hi&lt;/i&gt;", cap)
        self.assertIn("• m &amp; n", cap)
        self.assertIn("<b>Head &lt;&gt;</b>", cap)

    def test_build_caption_truncates_over_limit(self):
        cap = Bot._build_caption("Name", "x" * 2000, ["short fact"], "Highlights")
        self.assertLessEqual(visible_len(cap), 1024)
        self.assertIn("Name", cap)
        self.assertIn("Highlights", cap)
        self.assertIn("short fact", cap)

    def test_build_caption_never_exceeds_limit_even_with_large_facts(self):
        cap = Bot._build_caption("Name", "", ["x" * 1200], "Highlights")
        self.assertLessEqual(visible_len(cap), 1024)

    async def test_group_guard_allows_private_chat(self):
        update, context = make_update(chat_type="private"), make_context()
        context.bot.leave_chat = AsyncMock()
        # Private chats must pass through untouched: no leave, no stop raised.
        await self.bot._Bot__group_guard(update, context)
        context.bot.leave_chat.assert_not_called()

    async def test_group_guard_leaves_group_and_stops(self):
        update, context = make_update(chat_id=-100, chat_type="group"), make_context()
        context.bot.leave_chat = AsyncMock()
        with self.assertRaises(ApplicationHandlerStop):
            await self.bot._Bot__group_guard(update, context)
        context.bot.leave_chat.assert_awaited_once_with(chat_id=-100)

    async def test_group_guard_stops_even_if_leave_fails(self):
        update, context = make_update(chat_id=-100, chat_type="supergroup"), make_context()
        context.bot.leave_chat = AsyncMock(side_effect=TelegramError("cannot leave"))
        with self.assertRaises(ApplicationHandlerStop):
            await self.bot._Bot__group_guard(update, context)
        context.bot.leave_chat.assert_awaited_once()

    async def test_group_guard_ignores_update_without_chat(self):
        update, context = make_update(), make_context()
        update.effective_chat = None
        context.bot.leave_chat = AsyncMock()
        # No chat (e.g. poll update): pass through, do not raise or leave.
        await self.bot._Bot__group_guard(update, context)
        context.bot.leave_chat.assert_not_called()

    def test_application_has_rate_limiter(self):
        # Outgoing API calls are paced to avoid token-wide Telegram flood bans.
        self.assertIsInstance(self.bot.application.bot.rate_limiter, AIORateLimiter)

    def test_feedback_allowed_enforces_per_user_cooldown(self):
        cd = self.bot.FEEDBACK_COOLDOWN_SECONDS
        self.assertTrue(self.bot._feedback_allowed(7, now=1000.0))            # first: allowed
        self.assertFalse(self.bot._feedback_allowed(7, now=1000.0 + cd - 0.1))  # too soon: blocked
        self.assertTrue(self.bot._feedback_allowed(7, now=1000.0 + cd + 0.1))   # cooldown elapsed
        self.assertTrue(self.bot._feedback_allowed(8, now=1000.0 + 1))         # other user independent

    async def test_feedback_cooldown_blocks_second_forward(self):
        update, context = make_update(), make_context()
        with patch.dict(os.environ, {"OWNER_CHAT_ID": "999"}):
            await self.bot._forward_feedback(update, context, "one")  # allowed: forward + thanks
            context.bot.send_message.reset_mock()
            await self.bot._forward_feedback(update, context, "two")  # blocked by cooldown
        context.bot.send_message.assert_called_once()  # only the cooldown notice, no owner forward
        kwargs = context.bot.send_message.call_args.kwargs
        self.assertEqual(kwargs["chat_id"], update.effective_chat.id)
        self.assertNotEqual(kwargs["chat_id"], "999")

    def test_read_more_url_uses_wikidata_and_locale(self):
        f = HistoricalFigure(name="X", description="d", wikidata_id="Q42")
        en = Bot._read_more_url(f, "en")
        fr = Bot._read_more_url(f, "fr")
        self.assertIn("Q42", en)
        self.assertIn("enwiki", en)
        self.assertIn("Q42", fr)
        self.assertIn("frwiki", fr)
        f2 = HistoricalFigure(name="X", description="d")  # no wikidata_id
        self.assertIsNone(Bot._read_more_url(f2, "en"))

    async def test_send_figure_sends_chat_action_and_keyboard_with_read_more(self):
        figure = HistoricalFigure(name="Marie Curie", description="d", image_url="http://img",
                                  bio_en="Physicist.", wikidata_id="Q7186")
        update, context = make_update(), make_context()
        await self.bot._send_figure(update, context, figure)
        context.bot.send_chat_action.assert_awaited_once()
        markup = context.bot.send_photo.call_args.kwargs["reply_markup"]
        callbacks = [b.callback_data for row in markup.inline_keyboard for b in row if b.callback_data]
        urls = [b.url for row in markup.inline_keyboard for b in row if b.url]
        self.assertIn("random", callbacks)
        self.assertIn("today", callbacks)
        self.assertTrue(any("Q7186" in u and "enwiki" in u for u in urls))

    async def test_send_figure_message_has_keyboard_without_read_more(self):
        figure = HistoricalFigure(name="No Image", description="desc", bio_fr="bio fr")  # no image, no wikidata
        update, context = make_update(language_code="fr"), make_context()
        await self.bot._send_figure(update, context, figure)
        markup = context.bot.send_message.call_args.kwargs["reply_markup"]
        callbacks = [b.callback_data for row in markup.inline_keyboard for b in row if b.callback_data]
        urls = [b.url for row in markup.inline_keyboard for b in row if b.url]
        self.assertIn("random", callbacks)
        self.assertIn("today", callbacks)
        self.assertEqual(urls, [])

    async def test_post_init_sets_localized_commands_and_descriptions(self):
        app = Mock()
        app.bot.set_my_commands = AsyncMock()
        app.bot.set_my_description = AsyncMock()
        app.bot.set_my_short_description = AsyncMock()
        await self.bot._post_init(app)
        cmd_calls = app.bot.set_my_commands.call_args_list
        self.assertEqual(len(cmd_calls), 2)  # default (en) + fr
        langs = {c.kwargs.get("language_code") for c in cmd_calls}
        self.assertEqual(langs, {None, "fr"})
        for c in cmd_calls:
            commands = c.args[0] if c.args else c.kwargs["commands"]
            self.assertGreaterEqual(len(commands), 1)
        self.assertEqual(app.bot.set_my_description.call_count, 2)
        self.assertEqual(app.bot.set_my_short_description.call_count, 2)

    def test_group_guard_registered_in_low_group(self):
        self.bot.register_handlers()
        self.assertIn(-1, self.bot.application.handlers)
        guard_handlers = self.bot.application.handlers[-1]
        self.assertEqual(len(guard_handlers), 1)
        self.assertIsInstance(guard_handlers[0], TypeHandler)

    def test_register_handlers_registers_all(self):
        self.bot.register_handlers()
        handlers = self.bot.application.handlers[0]
        self.assertEqual(len(handlers), 8)  # 6 commands + 1 feedback conversation + 1 callback query
