import os
import re
import html
import tempfile
import unittest
from unittest.mock import patch, Mock, AsyncMock
from telegram import ForceReply, BotName
from telegram.error import TelegramError, Forbidden
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
    context.bot.send_chat_action = AsyncMock(return_value=None)
    context.args = []
    return context


class TestBot(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        # Point the subscriber store at a throwaway temp file so Bot tests never
        # touch a real subscribers.json in the repo.
        fd, self._subs_path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        os.unlink(self._subs_path)
        self.addCleanup(lambda: os.path.exists(self._subs_path) and os.unlink(self._subs_path))
        fd, self._sugg_path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        os.unlink(self._sugg_path)
        self.addCleanup(lambda: os.path.exists(self._sugg_path) and os.unlink(self._sugg_path))
        patcher = patch.dict(os.environ, {
            "TELEGRAM_BOT_TOKEN": "123456:ABC-test-token",
            "SUBSCRIBERS_FILE": self._subs_path,
            "SUGGESTIONS_FILE": self._sugg_path,
        })
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

    async def test_random_handler_sends_card(self):
        figure = HistoricalFigure(name="Marie Curie", description="d", image_url="http://img", bio_en="Physicist and chemist.")
        self.mock_database.get_random_figure.return_value = figure
        update, context = make_update(), make_context()
        await self.bot._Bot__random_handler(update, context)
        context.bot.send_message.assert_called_once()
        kwargs = context.bot.send_message.call_args.kwargs
        self.assertIn("Marie Curie", kwargs["text"])
        self.assertEqual(kwargs["link_preview_options"].url, "http://img")

    async def test_today_handler_sends_card(self):
        figure = HistoricalFigure(name="Leonardo da Vinci", description="d", image_url="http://img", bio_en="Polymath.")
        self.mock_database.get_figure_of_the_day.return_value = figure
        update, context = make_update(), make_context()
        await self.bot._Bot__today_handler(update, context)
        self.mock_database.get_figure_of_the_day.assert_called_once()
        self.assertIn("Leonardo da Vinci", context.bot.send_message.call_args.kwargs["text"])

    async def test_send_figure_without_image_uses_message(self):
        figure = HistoricalFigure(name="No Image", description="desc", bio_fr="bio fr")
        update, context = make_update(language_code="fr"), make_context()
        await self.bot._send_figure(update, context, figure)
        context.bot.send_message.assert_called_once()
        kwargs = context.bot.send_message.call_args.kwargs
        self.assertIn("bio fr", kwargs["text"])
        self.assertTrue(kwargs["link_preview_options"].is_disabled)

    async def test_send_figure_renders_facts_for_locale(self):
        figure = HistoricalFigure(
            name="V", description="d", image_url="http://img",
            bio_fr="bio fr", facts_fr=["fait un", "fait deux"],
        )
        update, context = make_update(language_code="fr"), make_context()
        await self.bot._send_figure(update, context, figure)
        text = context.bot.send_message.call_args.kwargs["text"]
        self.assertIn("Faits marquants", text)
        self.assertIn("• fait un", text)

    async def test_send_figure_carries_image_as_large_preview_above_text(self):
        """The portrait rides as a link preview so the card gets the 4096-char
        text budget instead of the 1024-char caption budget."""
        figure = HistoricalFigure(name="Big Img", description="d", image_url="http://img", bio_en="A bio.")
        update, context = make_update(), make_context()
        await self.bot._send_figure(update, context, figure)
        preview = context.bot.send_message.call_args.kwargs["link_preview_options"]
        self.assertEqual(preview.url, "http://img")
        self.assertTrue(preview.prefer_large_media)
        self.assertTrue(preview.show_above_text)

    async def test_subscribe_handler_registers_subscriber(self):
        update, context = make_update(chat_id=555), make_context()
        await self.bot._Bot__subscribe_handler(update, context)
        self.assertTrue(self.bot.subscribers.is_subscribed(555))
        context.bot.send_message.assert_called_once()

    async def test_subscribe_twice_reports_already(self):
        update, context = make_update(chat_id=555), make_context()
        await self.bot._Bot__subscribe_handler(update, context)
        await self.bot._Bot__subscribe_handler(update, context)
        self.assertEqual(context.bot.send_message.call_count, 2)
        first = context.bot.send_message.call_args_list[0].kwargs["text"]
        second = context.bot.send_message.call_args_list[1].kwargs["text"]
        self.assertNotEqual(first, second)  # "already subscribed" differs from "subscribed"

    async def test_unsubscribe_handler_removes_subscriber(self):
        update, context = make_update(chat_id=555), make_context()
        self.bot.subscribers.subscribe(555, "en")
        await self.bot._Bot__unsubscribe_handler(update, context)
        self.assertFalse(self.bot.subscribers.is_subscribed(555))
        context.bot.send_message.assert_called_once()

    async def test_unsubscribe_when_not_subscribed_still_replies(self):
        update, context = make_update(chat_id=555), make_context()
        await self.bot._Bot__unsubscribe_handler(update, context)
        context.bot.send_message.assert_called_once()

    async def test_suggest_ignored_for_non_owner(self):
        update, context = make_update(chat_id=999), make_context()
        context.args = ["Vauban"]
        with patch.dict(os.environ, {"OWNER_CHAT_ID": "42"}):
            await self.bot._Bot__suggest_handler(update, context)
        # Silence complet : la commande n'existe pas pour les autres.
        context.bot.send_message.assert_not_called()
        self.assertEqual(self.bot.suggestions.count(), 0)

    async def test_suggest_refused_when_owner_unset(self):
        """Fail closed : sans OWNER_CHAT_ID, personne ne passe."""
        update, context = make_update(chat_id=42), make_context()
        context.args = ["Vauban"]
        with patch.dict(os.environ, {}, clear=True):
            os.environ["TELEGRAM_BOT_TOKEN"] = "123456:ABC-test-token"
            await self.bot._Bot__suggest_handler(update, context)
        context.bot.send_message.assert_not_called()
        self.assertEqual(self.bot.suggestions.count(), 0)

    async def test_suggest_queues_name_for_owner(self):
        update, context = make_update(chat_id=42), make_context()
        context.args = ["Vauban"]
        self.mock_database.get_all_figures.return_value = []
        with patch.dict(os.environ, {"OWNER_CHAT_ID": "42"}):
            await self.bot._Bot__suggest_handler(update, context)
        self.assertEqual(self.bot.suggestions.all(), ["Vauban"])
        _, kwargs = context.bot.send_message.call_args
        self.assertIn("Vauban", kwargs["text"])

    async def test_suggest_splits_on_commas(self):
        update, context = make_update(chat_id=42), make_context()
        context.args = ["Vauban,", "Lyautey,", "Gallieni"]
        self.mock_database.get_all_figures.return_value = []
        with patch.dict(os.environ, {"OWNER_CHAT_ID": "42"}):
            await self.bot._Bot__suggest_handler(update, context)
        self.assertEqual(self.bot.suggestions.all(), ["Vauban", "Lyautey", "Gallieni"])

    async def test_suggest_warns_on_roster_collision_but_still_queues(self):
        """Le cas Lesseps : le roster stocke une forme courte. On signale, mais
        c'est l'humain qui tranche — l'heuristique produit des faux positifs."""
        update, context = make_update(chat_id=42), make_context()
        context.args = ["Ferdinand", "de", "Lesseps"]
        self.mock_database.get_all_figures.return_value = [
            HistoricalFigure(name="De Lesseps", description="d")
        ]
        with patch.dict(os.environ, {"OWNER_CHAT_ID": "42"}):
            await self.bot._Bot__suggest_handler(update, context)
        _, kwargs = context.bot.send_message.call_args
        self.assertIn("De Lesseps", kwargs["text"])
        self.assertEqual(self.bot.suggestions.all(), ["Ferdinand de Lesseps"])

    async def test_suggest_reports_already_queued(self):
        update, context = make_update(chat_id=42), make_context()
        self.mock_database.get_all_figures.return_value = []
        with patch.dict(os.environ, {"OWNER_CHAT_ID": "42"}):
            context.args = ["Vauban"]
            await self.bot._Bot__suggest_handler(update, context)
            context.args = ["Vauban"]
            await self.bot._Bot__suggest_handler(update, context)
        self.assertEqual(self.bot.suggestions.count(), 1)

    async def test_suggest_without_args_shows_usage(self):
        update, context = make_update(chat_id=42), make_context()
        context.args = []
        with patch.dict(os.environ, {"OWNER_CHAT_ID": "42"}):
            await self.bot._Bot__suggest_handler(update, context)
        _, kwargs = context.bot.send_message.call_args
        self.assertIn("/suggest", kwargs["text"])
        self.assertEqual(self.bot.suggestions.count(), 0)

    def test_suggest_absent_from_published_menu(self):
        """Owner-only : la commande ne doit apparaître dans aucun menu."""
        import inspect
        source = inspect.getsource(self.bot._post_init)
        self.assertNotIn("suggest", source)

    async def test_send_daily_delivers_localized_to_all_subscribers(self):
        figure = HistoricalFigure(name="Ada Lovelace", description="d", bio_en="EN bio", bio_fr="FR bio")  # no image
        self.mock_database.get_figure_of_the_day.return_value = figure
        self.bot.subscribers.subscribe(111, "en")
        self.bot.subscribers.subscribe(222, "fr")
        context = make_context()
        await self.bot._send_daily(context)
        self.assertEqual(context.bot.send_message.call_count, 2)
        texts = {c.kwargs["chat_id"]: c.kwargs["text"] for c in context.bot.send_message.call_args_list}
        self.assertEqual(set(texts), {111, 222})
        self.assertIn("EN bio", texts[111])
        self.assertIn("FR bio", texts[222])

    async def test_send_daily_removes_blocked_subscriber(self):
        figure = HistoricalFigure(name="X", description="d", bio_en="bio")  # no image
        self.mock_database.get_figure_of_the_day.return_value = figure
        self.bot.subscribers.subscribe(111, "en")
        context = make_context()
        context.bot.send_message = AsyncMock(side_effect=Forbidden("bot was blocked by the user"))
        await self.bot._send_daily(context)
        self.assertFalse(self.bot.subscribers.is_subscribed(111))

    async def test_send_daily_skips_when_no_figure(self):
        self.mock_database.get_figure_of_the_day.return_value = None
        self.bot.subscribers.subscribe(111, "en")
        context = make_context()
        await self.bot._send_daily(context)
        context.bot.send_message.assert_not_called()

    async def test_post_init_schedules_daily_job_at_noon_paris(self):
        app = Mock()
        app.bot.set_my_commands = AsyncMock()
        app.bot.set_my_description = AsyncMock()
        app.bot.set_my_short_description = AsyncMock()
        app.bot.get_my_name = AsyncMock(return_value=BotName("stale name"))
        app.bot.set_my_name = AsyncMock()
        app.job_queue.run_daily = Mock()
        await self.bot._post_init(app)
        app.job_queue.run_daily.assert_called_once()
        scheduled = app.job_queue.run_daily.call_args.kwargs["time"]
        self.assertEqual(scheduled.hour, 12)
        self.assertEqual(str(scheduled.tzinfo), "Europe/Paris")
        # A brief event-loop stall at noon must not silently drop the delivery.
        job_kwargs = app.job_queue.run_daily.call_args.kwargs["job_kwargs"]
        self.assertGreaterEqual(job_kwargs["misfire_grace_time"], 60)

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

    async def test_button_random_sends_card_and_answers(self):
        figure = HistoricalFigure(name="Marie Curie", description="d", image_url="http://img", bio_en="Physicist.")
        self.mock_database.get_random_figure.return_value = figure
        update, context = make_update(), make_context()
        update.callback_query = Mock()
        update.callback_query.data = "random"
        update.callback_query.answer = AsyncMock()
        await self.bot._Bot__button_handler(update, context)
        update.callback_query.answer.assert_awaited_once()
        self.assertIn("Marie Curie", context.bot.send_message.call_args.kwargs["text"])

    async def test_button_today_sends_card_and_answers(self):
        figure = HistoricalFigure(name="Leonardo da Vinci", description="d", image_url="http://img", bio_en="Polymath.")
        self.mock_database.get_figure_of_the_day.return_value = figure
        update, context = make_update(), make_context()
        update.callback_query = Mock()
        update.callback_query.data = "today"
        update.callback_query.answer = AsyncMock()
        await self.bot._Bot__button_handler(update, context)
        update.callback_query.answer.assert_awaited_once()
        self.assertIn("Leonardo da Vinci", context.bot.send_message.call_args.kwargs["text"])

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

    def test_build_card_text_html_with_and_without_facts(self):
        cap = Bot._build_card_text("Voltaire", "A bio.", ["f1", "f2"], "Highlights")
        self.assertIn("<b>Voltaire</b>", cap)
        self.assertIn("<i>A bio.</i>", cap)
        self.assertIn("<b>Highlights</b>", cap)
        self.assertIn("• f1", cap)
        no_facts = Bot._build_card_text("Voltaire", "A bio.", [], "Highlights")
        self.assertNotIn("Highlights", no_facts)
        self.assertIn("<b>Voltaire</b>", no_facts)

    def test_build_card_text_escapes_html_in_content(self):
        cap = Bot._build_card_text("A & B <x>", "bio & <i>hi</i>", ["m & n"], "Head <>")
        self.assertIn("<b>A &amp; B &lt;x&gt;</b>", cap)
        self.assertIn("bio &amp; &lt;i&gt;hi&lt;/i&gt;", cap)
        self.assertIn("• m &amp; n", cap)
        self.assertIn("<b>Head &lt;&gt;</b>", cap)

    def test_build_card_text_truncates_over_limit(self):
        cap = Bot._build_card_text("Name", "x" * 6000, ["short fact"], "Highlights")
        self.assertLessEqual(visible_len(cap), 4096)
        self.assertIn("Name", cap)
        self.assertIn("Highlights", cap)
        self.assertIn("short fact", cap)

    def test_build_card_text_never_exceeds_limit_even_with_large_facts(self):
        cap = Bot._build_card_text("Name", "", ["x" * 5000], "Highlights")
        self.assertLessEqual(visible_len(cap), 4096)

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
        markup = context.bot.send_message.call_args.kwargs["reply_markup"]
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
        app.bot.get_my_name = AsyncMock(return_value=BotName("stale name"))
        app.bot.set_my_name = AsyncMock()
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
        name_calls = app.bot.set_my_name.call_args_list
        self.assertEqual(len(name_calls), 2)  # default (en) + fr
        self.assertEqual({c.kwargs.get("language_code") for c in name_calls}, {None, "fr"})
        names = [c.args[0] if c.args else c.kwargs["name"] for c in name_calls]
        self.assertEqual(names, ["History Bot · Historical Figures Daily",
                                 "Histoire · Figures Historiques du Jour"])

    async def test_post_init_skips_name_write_when_already_current(self):
        """Telegram rate-limits name changes, so an unchanged name must not be rewritten."""
        app = Mock()
        app.bot.set_my_commands = AsyncMock()
        app.bot.set_my_description = AsyncMock()
        app.bot.set_my_short_description = AsyncMock()
        app.bot.get_my_name = AsyncMock(side_effect=[
            BotName("History Bot · Historical Figures Daily"),
            BotName("Histoire · Figures Historiques du Jour"),
        ])
        app.bot.set_my_name = AsyncMock()
        await self.bot._post_init(app)
        app.bot.set_my_name.assert_not_called()

    async def test_post_init_survives_name_rate_limit(self):
        """A rejected name change must not abort startup — commands still get published."""
        app = Mock()
        app.bot.set_my_commands = AsyncMock()
        app.bot.set_my_description = AsyncMock()
        app.bot.set_my_short_description = AsyncMock()
        app.bot.get_my_name = AsyncMock(return_value=BotName("stale name"))
        app.bot.set_my_name = AsyncMock(side_effect=TelegramError("Too Many Requests"))
        await self.bot._post_init(app)
        self.assertEqual(app.bot.set_my_commands.call_count, 2)

    def test_group_guard_registered_in_low_group(self):
        self.bot.register_handlers()
        self.assertIn(-1, self.bot.application.handlers)
        guard_handlers = self.bot.application.handlers[-1]
        self.assertEqual(len(guard_handlers), 1)
        self.assertIsInstance(guard_handlers[0], TypeHandler)

    def test_register_handlers_registers_all(self):
        self.bot.register_handlers()
        handlers = self.bot.application.handlers[0]
        self.assertEqual(len(handlers), 9)  # 7 commands + 1 feedback conversation + 1 callback query

    async def test_figure_keyboard_carries_a_share_button(self):
        self.bot._bot_username = "HistoricalFiguresWhisperBot"
        figure = HistoricalFigure(name="George Sand", description="d")
        markup = self.bot._figure_keyboard("fr", figure)
        urls = [b.url for row in markup.inline_keyboard for b in row if b.url]
        self.assertEqual(len(urls), 1)
        self.assertTrue(urls[0].startswith("https://t.me/share/url?url="))
        # Le deep link est percent-encodé dans le paramètre url.
        self.assertIn("start%3Dgeorge-sand", urls[0])

    async def test_share_button_is_omitted_without_a_known_username(self):
        """Avant _post_init l'username est inconnu : mieux vaut pas de bouton
        qu'un lien cassé."""
        self.bot._bot_username = None
        figure = HistoricalFigure(name="George Sand", description="d")
        markup = self.bot._figure_keyboard("fr", figure)
        urls = [b.url for row in markup.inline_keyboard for b in row if b.url]
        self.assertEqual(urls, [])

    async def test_share_and_read_more_share_one_row(self):
        self.bot._bot_username = "HistoricalFiguresWhisperBot"
        figure = HistoricalFigure(name="Lafayette", description="d", wikidata_id="Q184960")
        markup = self.bot._figure_keyboard("fr", figure)
        self.assertEqual(len(markup.inline_keyboard), 2)
        self.assertEqual(len(markup.inline_keyboard[1]), 2)

    async def test_share_text_is_localized_and_names_the_figure(self):
        self.bot._bot_username = "HistoricalFiguresWhisperBot"
        figure = HistoricalFigure(name="George Sand", description="d")
        url_fr = self.bot._share_url(figure, "fr")
        url_en = self.bot._share_url(figure, "en")
        self.assertIn("George%20Sand", url_fr)
        self.assertNotEqual(url_fr, url_en)

    async def test_post_init_captures_the_bot_username(self):
        app = Mock()
        app.bot.set_my_commands = AsyncMock()
        app.bot.set_my_description = AsyncMock()
        app.bot.set_my_short_description = AsyncMock()
        app.bot.get_my_name = AsyncMock(return_value=BotName("stale name"))
        app.bot.set_my_name = AsyncMock()
        app.bot.username = "HistoricalFiguresWhisperBot"
        await self.bot._post_init(app)
        self.assertEqual(self.bot._bot_username, "HistoricalFiguresWhisperBot")

    async def test_start_with_payload_delivers_the_shared_figure(self):
        figure = HistoricalFigure(name="George Sand", description="d", bio_fr="bio fr")
        self.mock_database.get_figure_by_slug.return_value = figure
        update, context = make_update(language_code="fr"), make_context()
        context.args = ["george-sand"]
        await self.bot._Bot__start_handler(update, context)
        self.mock_database.get_figure_by_slug.assert_called_once_with("george-sand")
        texts = [c.kwargs["text"] for c in context.bot.send_message.call_args_list]
        self.assertEqual(len(texts), 2)          # ligne de contexte, puis carte
        self.assertIn("/subscribe", texts[0])    # l'arrivant doit voir l'action
        self.assertIn("George Sand", texts[1])

    async def test_start_with_unknown_payload_falls_back_to_today(self):
        """L'arrivant a cliqué : il repart avec une carte, pas avec une erreur."""
        today = HistoricalFigure(name="Colbert", description="d", bio_fr="bio fr")
        self.mock_database.get_figure_by_slug.return_value = None
        self.mock_database.get_figure_of_the_day.return_value = today
        update, context = make_update(language_code="fr"), make_context()
        context.args = ["figure-disparue"]
        await self.bot._Bot__start_handler(update, context)
        texts = [c.kwargs["text"] for c in context.bot.send_message.call_args_list]
        self.assertEqual(len(texts), 2)
        self.assertIn("Colbert", texts[1])

    async def test_start_without_payload_is_unchanged(self):
        update, context = make_update(), make_context()
        context.args = []
        await self.bot._Bot__start_handler(update, context)
        context.bot.send_message.assert_called_once()
        self.mock_database.get_figure_by_slug.assert_not_called()

    async def test_shared_link_renders_in_the_recipient_locale(self):
        """La langue est celle du destinataire, pas celle de l'expéditeur."""
        figure = HistoricalFigure(name="George Sand", description="d",
                                  bio_en="EN bio", bio_fr="bio fr")
        self.mock_database.get_figure_by_slug.return_value = figure
        update, context = make_update(language_code="en"), make_context()
        context.args = ["george-sand"]
        await self.bot._Bot__start_handler(update, context)
        texts = [c.kwargs["text"] for c in context.bot.send_message.call_args_list]
        self.assertIn("EN bio", texts[1])
