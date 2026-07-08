import os
import time
from datetime import date

from src.database import Database
from src.utils import Utils
from src.logger import LOGGER
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ForceReply
from telegram.error import TelegramError
from telegram.ext import (
    ApplicationBuilder, ContextTypes, CommandHandler, CallbackQueryHandler,
    ConversationHandler, MessageHandler, TypeHandler, ApplicationHandlerStop,
    AIORateLimiter, filters,
)

# ConversationHandler state: waiting for the user's feedback message.
FEEDBACK_WAITING = 0


class Bot:
    # Minimum delay between two feedback submissions forwarded to the owner,
    # per user — protects the owner's chat from a single user flooding it.
    FEEDBACK_COOLDOWN_SECONDS = 30

    def __init__(self, database: Database):
        token = Utils.get_environment_variable("TELEGRAM_BOT_TOKEN")
        # AIORateLimiter paces outgoing API calls so a burst of traffic can't
        # trip Telegram's token-wide flood limits (which would mute the bot).
        self.application = ApplicationBuilder().token(token).rate_limiter(AIORateLimiter()).build()
        self.database = database
        self.localizable_strings = Utils.load_localizable_data()
        self._feedback_last = {}  # user_id -> monotonic timestamp of last forwarded feedback

    def _locale(self, update: Update) -> str:
        language_code = update.effective_user.language_code if update.effective_user else None
        return Utils.resolve_locale(language_code)

    def _t(self, key: str, update: Update) -> str:
        return Utils.localize(key, self._locale(update), self.localizable_strings)

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
        facts_block = ""
        if facts:
            facts_block = "\n\n" + header + "\n" + "\n".join(f"• {f}" for f in facts)
        head = name if not bio else f"{name}\n\n{bio}"
        caption = head + facts_block
        if len(caption) <= limit:
            return caption
        # Over the limit: truncate the bio, keep name + facts block.
        ellipsis = "…"
        separator = "\n\n"
        budget = limit - len(name) - len(separator) - len(ellipsis) - len(facts_block)
        if budget > 0:
            truncated_bio = bio[:budget].rstrip() + ellipsis
            return f"{name}{separator}{truncated_bio}{facts_block}"
        # No room for any bio (name + facts block alone are already at/over the
        # limit): drop the bio entirely.
        without_bio = name + facts_block
        if len(without_bio) <= limit:
            return without_bio
        # Last resort: even name + facts block exceed the limit. Hard-clamp to
        # guarantee the length invariant holds, at the cost of content quality.
        return without_bio[:limit]

    async def _send_figure(self, update: Update, context: ContextTypes.DEFAULT_TYPE, figure) -> None:
        if not figure:
            await context.bot.send_message(chat_id=update.effective_chat.id, text=self._t("no-figures", update))
            return
        locale = self._locale(update)
        bio = self._figure_bio(figure, locale)
        facts = self._figure_facts(figure, locale)
        caption = self._build_caption(figure.name, bio, facts, self._t("highlights-header", update))
        if figure.image_url:
            try:
                await context.bot.send_photo(chat_id=update.effective_chat.id, photo=figure.image_url, caption=caption)
                return
            except TelegramError as e:
                LOGGER.warning(f"send_photo failed for {figure.name} ({figure.image_url}): {e}; falling back to text")
        await context.bot.send_message(chat_id=update.effective_chat.id, text=caption)

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
        await context.bot.send_message(chat_id=update.effective_chat.id, text=self._t("subscribe-soon", update))

    async def __unsubscribe_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        LOGGER.info("Unsubscribe handler command called")
        await context.bot.send_message(chat_id=update.effective_chat.id, text=self._t("unsubscribe-soon", update))

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
