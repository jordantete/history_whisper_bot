import os
import html
import time
from datetime import date, time as dtime
from zoneinfo import ZoneInfo

from src.database import Database
from src.subscribers import SubscriberStore
from src.utils import Utils
from src.logger import LOGGER
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ForceReply, BotCommand
from telegram.constants import ChatAction, ParseMode
from telegram.error import TelegramError, Forbidden
from telegram.ext import (
    ApplicationBuilder, ContextTypes, CommandHandler, CallbackQueryHandler,
    ConversationHandler, MessageHandler, TypeHandler, ApplicationHandlerStop,
    AIORateLimiter, filters,
)

# ConversationHandler state: waiting for the user's feedback message.
FEEDBACK_WAITING = 0

# When the daily figure is delivered to subscribers (single timezone for now).
DAILY_TIME = dtime(hour=12, minute=0, tzinfo=ZoneInfo("Europe/Paris"))


class Bot:
    # Minimum delay between two feedback submissions forwarded to the owner,
    # per user — protects the owner's chat from a single user flooding it.
    FEEDBACK_COOLDOWN_SECONDS = 30

    def __init__(self, database: Database, subscriber_store: SubscriberStore = None):
        token = Utils.get_environment_variable("TELEGRAM_BOT_TOKEN")
        # AIORateLimiter paces outgoing API calls so a burst of traffic can't
        # trip Telegram's token-wide flood limits (which would mute the bot).
        # post_init publishes the localized command menu + profile descriptions.
        self.application = (
            ApplicationBuilder()
            .token(token)
            .rate_limiter(AIORateLimiter())
            .post_init(self._post_init)
            .build()
        )
        self.database = database
        self.localizable_strings = Utils.load_localizable_data()
        self._feedback_last = {}  # user_id -> monotonic timestamp of last forwarded feedback
        self.subscribers = subscriber_store or SubscriberStore(
            os.environ.get("SUBSCRIBERS_FILE", "subscribers.json"))

    def _locale(self, update: Update) -> str:
        language_code = update.effective_user.language_code if update.effective_user else None
        return Utils.resolve_locale(language_code)

    def _t(self, key: str, update: Update) -> str:
        return Utils.localize(key, self._locale(update), self.localizable_strings)

    def _tl(self, key: str, locale: str) -> str:
        return Utils.localize(key, locale, self.localizable_strings)

    async def _post_init(self, application) -> None:
        """Publish the localized command menu and profile descriptions to
        Telegram once, at startup. Default (no language_code) carries English;
        French is registered explicitly. Shown in the '/' menu and on the
        bot's start screen / profile."""
        menu = ("today", "random", "subscribe", "unsubscribe", "feedback", "help")
        for locale, language_code in (("en", None), ("fr", "fr")):
            commands = [BotCommand(cmd, self._tl(f"cmd-{cmd}", locale)) for cmd in menu]
            await application.bot.set_my_commands(commands, language_code=language_code)
            await application.bot.set_my_short_description(
                self._tl("bot-short-description", locale), language_code=language_code)
            await application.bot.set_my_description(
                self._tl("bot-description", locale), language_code=language_code)
        # Schedule the daily figure delivery to subscribers.
        # misfire_grace_time widens APScheduler's default 1s window: if the event
        # loop is briefly blocked at noon (e.g. a Telegram getUpdates retry storm),
        # the job still fires within the hour instead of being silently dropped.
        if application.job_queue:
            application.job_queue.run_daily(
                self._send_daily, time=DAILY_TIME, name="daily-figure",
                job_kwargs={"misfire_grace_time": 3600})
            LOGGER.info(f"Scheduled daily delivery at {DAILY_TIME}")
        else:
            LOGGER.warning("JobQueue unavailable — daily delivery not scheduled")

    def _figure_bio(self, figure, locale: str) -> str:
        primary = figure.bio_fr if locale == "fr" else figure.bio_en
        secondary = figure.bio_en if locale == "fr" else figure.bio_fr
        return primary or secondary or figure.description or ""

    def _figure_facts(self, figure, locale: str) -> list:
        primary = figure.facts_fr if locale == "fr" else figure.facts_en
        secondary = figure.facts_en if locale == "fr" else figure.facts_fr
        return primary or secondary or []

    @staticmethod
    def _build_caption(name: str, bio: str, facts, header: str, limit: int = 1024) -> str:
        """Render an HTML caption (bold name, italic bio, bold header + bullets).
        All dynamic content is HTML-escaped. Telegram's caption limit counts the
        *visible* text (tags/entities excluded), so truncation is budgeted on the
        raw text length while the output carries the markup."""
        def esc(s):
            return html.escape(s, quote=False)

        separator = "\n\n"
        # facts block: visible form drives the budget, html form is emitted.
        facts_visible = ""
        facts_html = ""
        if facts:
            facts_visible = separator + header + "\n" + "\n".join(f"• {f}" for f in facts)
            facts_html = separator + f"<b>{esc(header)}</b>\n" + "\n".join(f"• {esc(f)}" for f in facts)

        name_html = f"<b>{esc(name)}</b>"
        full_visible = len(name) + (len(separator) + len(bio) if bio else 0) + len(facts_visible)
        if full_visible <= limit:
            body = name_html if not bio else f"{name_html}{separator}<i>{esc(bio)}</i>"
            return body + facts_html
        # Over the limit: truncate the bio (visible budget), keep name + facts.
        ellipsis = "…"
        budget = limit - len(name) - len(separator) - len(ellipsis) - len(facts_visible)
        if budget > 0:
            truncated = bio[:budget].rstrip()
            return f"{name_html}{separator}<i>{esc(truncated)}{ellipsis}</i>{facts_html}"
        # No room for any bio: drop it, keep name + facts.
        if len(name) + len(facts_visible) <= limit:
            return name_html + facts_html
        # Last resort: even name + facts exceed the limit. Hard-clamp the visible
        # text to guarantee the invariant, at the cost of formatting/content.
        return esc((name + facts_visible)[:limit])

    @staticmethod
    def _read_more_url(figure, locale: str):
        """Wikidata redirect to the figure's Wikipedia article in the given
        locale, resolved from its Wikidata id (robust to title mismatches).
        Returns None when the figure has no Wikidata id."""
        if not figure.wikidata_id:
            return None
        site = "frwiki" if locale == "fr" else "enwiki"
        return f"https://www.wikidata.org/wiki/Special:GoToLinkedPage?site={site}&itemid={figure.wikidata_id}"

    def _figure_keyboard(self, locale: str, figure) -> InlineKeyboardMarkup:
        rows = [[
            InlineKeyboardButton(self._tl("btn-another", locale), callback_data="random"),
            InlineKeyboardButton(self._tl("btn-today", locale), callback_data="today"),
        ]]
        url = self._read_more_url(figure, locale)
        if url:
            rows.append([InlineKeyboardButton(self._tl("btn-read-more", locale), url=url)])
        return InlineKeyboardMarkup(rows)

    async def _deliver_figure(self, context: ContextTypes.DEFAULT_TYPE, chat_id, locale: str, figure) -> None:
        """Send a rendered figure card to a specific chat in a specific locale.
        Shared by interactive commands and the daily job. Forbidden (user blocked
        the bot) propagates so callers can react (e.g. drop the subscriber)."""
        bio = self._figure_bio(figure, locale)
        facts = self._figure_facts(figure, locale)
        caption = self._build_caption(figure.name, bio, facts, self._tl("highlights-header", locale))
        keyboard = self._figure_keyboard(locale, figure)
        if figure.image_url:
            try:
                await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.UPLOAD_PHOTO)
                await context.bot.send_photo(chat_id=chat_id, photo=figure.image_url,
                                             caption=caption, parse_mode=ParseMode.HTML, reply_markup=keyboard)
                return
            except Forbidden:
                raise
            except TelegramError as e:
                LOGGER.warning(f"send_photo failed for {figure.name} ({figure.image_url}): {e}; falling back to text")
        await context.bot.send_message(chat_id=chat_id, text=caption,
                                       parse_mode=ParseMode.HTML, reply_markup=keyboard)

    async def _send_figure(self, update: Update, context: ContextTypes.DEFAULT_TYPE, figure) -> None:
        if not figure:
            await context.bot.send_message(chat_id=update.effective_chat.id, text=self._t("no-figures", update))
            return
        await self._deliver_figure(context, update.effective_chat.id, self._locale(update), figure)

    async def _send_daily(self, context: ContextTypes.DEFAULT_TYPE) -> None:
        """JobQueue callback: deliver the figure of the day to all subscribers,
        each in their own locale. Subscribers who blocked the bot are dropped."""
        figure = self.database.get_figure_of_the_day(date.today())
        if not figure:
            LOGGER.warning("No figure of the day — skipping daily delivery")
            return
        recipients = self.subscribers.all()
        LOGGER.info(f"Daily delivery starting for {len(recipients)} subscriber(s)")
        sent = 0
        for chat_id, locale in recipients:
            try:
                await self._deliver_figure(context, chat_id, locale, figure)
                sent += 1
            except Forbidden:
                LOGGER.info(f"Subscriber {chat_id} blocked the bot — removing")
                self.subscribers.unsubscribe(chat_id)
            except TelegramError as e:
                LOGGER.warning(f"Daily delivery to {chat_id} failed: {e}")
        LOGGER.info(f"Daily delivery done: {sent}/{len(recipients)} sent")

    async def __group_guard(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Runs before every handler. The bot is private-only: in any group /
        supergroup / channel it stays silent, leaves the chat, and stops all
        further handling. No per-user access control — the bot is public."""
        chat = update.effective_chat
        if not chat or chat.type == "private":
            return
        LOGGER.info(f"Non-private chat {chat.id} ({chat.type}) — leaving and ignoring")
        try:
            await context.bot.leave_chat(chat_id=chat.id)
        except Exception as e:
            LOGGER.warning(f"Failed to leave chat {chat.id}: {e}")
        raise ApplicationHandlerStop

    async def __start_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        LOGGER.info("Start handler command called")
        text = self._t("start-message", update)
        buttons = [
            InlineKeyboardButton("🎲 Random", callback_data="random"),
            InlineKeyboardButton("📅 Today", callback_data="today"),
            InlineKeyboardButton("❓ Help", callback_data="help"),
        ]
        reply_markup = InlineKeyboardMarkup([buttons])
        await context.bot.send_message(chat_id=update.effective_chat.id, text=text, reply_markup=reply_markup)

    async def __help_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        LOGGER.info("Help handler command called")
        await context.bot.send_message(chat_id=update.effective_chat.id, text=self._t("help-message", update))

    async def __random_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        LOGGER.info("Random handler command called")
        figure = self.database.get_random_figure()
        await self._send_figure(update, context, figure)

    async def __today_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        LOGGER.info("Today handler command called")
        figure = self.database.get_figure_of_the_day(date.today())
        await self._send_figure(update, context, figure)

    async def __button_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        LOGGER.info(f"Button pressed: {query.data}")
        if query.data == "random":
            await self._send_figure(update, context, self.database.get_random_figure())
        elif query.data == "today":
            await self._send_figure(update, context, self.database.get_figure_of_the_day(date.today()))
        elif query.data == "help":
            await context.bot.send_message(chat_id=update.effective_chat.id, text=self._t("help-message", update))

    async def __subscribe_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        LOGGER.info("Subscribe handler command called")
        chat_id = update.effective_chat.id
        newly = self.subscribers.subscribe(chat_id, self._locale(update))
        key = "subscribe-done" if newly else "subscribe-already"
        await context.bot.send_message(chat_id=chat_id, text=self._t(key, update))

    async def __unsubscribe_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        LOGGER.info("Unsubscribe handler command called")
        chat_id = update.effective_chat.id
        was_subscribed = self.subscribers.unsubscribe(chat_id)
        key = "unsubscribe-done" if was_subscribed else "unsubscribe-none"
        await context.bot.send_message(chat_id=chat_id, text=self._t(key, update))

    def _feedback_allowed(self, user_id, now: float) -> bool:
        """Per-user cooldown gate. Returns True (and records `now`) if the user
        may submit feedback; False if they're still within the cooldown window.
        Only allowed submissions update the timestamp, so continuous spam stays
        capped at one forward per cooldown window."""
        last = self._feedback_last.get(user_id)
        if last is not None and now - last < self.FEEDBACK_COOLDOWN_SECONDS:
            return False
        self._feedback_last[user_id] = now
        return True

    async def _forward_feedback(self, update: Update, context: ContextTypes.DEFAULT_TYPE, text: str) -> None:
        user = update.effective_user
        if user and not self._feedback_allowed(user.id, time.monotonic()):
            LOGGER.info(f"Feedback from {user.id} throttled (cooldown)")
            await context.bot.send_message(chat_id=update.effective_chat.id, text=self._t("feedback-cooldown", update))
            return
        owner_chat_id = os.environ.get("OWNER_CHAT_ID")
        if owner_chat_id:
            who = f"@{user.username}" if user and user.username else (str(user.id) if user else "unknown")
            try:
                await context.bot.send_message(chat_id=owner_chat_id, text=f"Feedback from {who}:\n{text}")
            except Exception as e:
                LOGGER.error(f"Failed to forward feedback to owner: {e}")
        else:
            LOGGER.warning("OWNER_CHAT_ID not set — feedback not forwarded")
        await context.bot.send_message(chat_id=update.effective_chat.id, text=self._t("feedback-thanks", update))

    async def __feedback_entry(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        LOGGER.info("Feedback command called")
        text = " ".join(context.args).strip() if context.args else ""
        if text:
            await self._forward_feedback(update, context, text)
            return ConversationHandler.END
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=self._t("feedback-ask", update),
            reply_markup=ForceReply(input_field_placeholder=self._t("feedback-placeholder", update)),
        )
        return FEEDBACK_WAITING

    async def __feedback_receive(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        LOGGER.info("Feedback received via conversation")
        text = (update.message.text or "").strip()
        await self._forward_feedback(update, context, text)
        return ConversationHandler.END

    async def __feedback_cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        LOGGER.info("Feedback cancelled")
        await context.bot.send_message(chat_id=update.effective_chat.id, text=self._t("feedback-cancel", update))
        return ConversationHandler.END

    def register_handlers(self):
        # Global gate (runs before all group-0 handlers): private-chat-only.
        self.application.add_handler(TypeHandler(Update, self.__group_guard), group=-1)
        self.application.add_handler(CommandHandler('start', self.__start_handler))
        self.application.add_handler(CommandHandler('help', self.__help_handler))
        self.application.add_handler(CommandHandler('random', self.__random_handler))
        self.application.add_handler(CommandHandler('today', self.__today_handler))
        self.application.add_handler(CommandHandler('subscribe', self.__subscribe_handler))
        self.application.add_handler(CommandHandler('unsubscribe', self.__unsubscribe_handler))
        self.application.add_handler(ConversationHandler(
            entry_points=[CommandHandler('feedback', self.__feedback_entry)],
            states={FEEDBACK_WAITING: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.__feedback_receive)]},
            fallbacks=[CommandHandler('cancel', self.__feedback_cancel)],
        ))
        self.application.add_handler(CallbackQueryHandler(self.__button_handler))

    def run(self):
        LOGGER.info("Bot starting in long-polling mode")
        self.register_handlers()
        self.application.run_polling()
