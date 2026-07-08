import os
from datetime import date

from src.database import Database
from src.utils import Utils
from src.logger import LOGGER
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ForceReply
from telegram.ext import (
    ApplicationBuilder, ContextTypes, CommandHandler, CallbackQueryHandler,
    ConversationHandler, MessageHandler, filters,
)

# ConversationHandler state: waiting for the user's feedback message.
FEEDBACK_WAITING = 0


class Bot:
    def __init__(self, database: Database):
        token = Utils.get_environment_variable("TELEGRAM_BOT_TOKEN")
        self.application = ApplicationBuilder().token(token).build()
        self.database = database
        self.localizable_strings = Utils.load_localizable_data()

    def _locale(self, update: Update) -> str:
        language_code = update.effective_user.language_code if update.effective_user else None
        return Utils.resolve_locale(language_code)

    def _t(self, key: str, update: Update) -> str:
        return Utils.localize(key, self._locale(update), self.localizable_strings)

    @staticmethod
    def _format_figure(figure) -> str:
        return f"{figure.name}\n{figure.description}"

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
        # Over the limit: truncate the bio, keep name + faits block.
        ellipsis = "…"
        budget = limit - len(name) - len("\n\n") - len(ellipsis) - len(facts_block)
        truncated_bio = bio[: max(0, budget)].rstrip() + ellipsis
        return f"{name}\n\n{truncated_bio}{facts_block}"

    async def _send_figure(self, update: Update, context: ContextTypes.DEFAULT_TYPE, figure) -> None:
        if figure:
            text = self._format_figure(figure)
        else:
            text = self._t("no-figures", update)
        await context.bot.send_message(chat_id=update.effective_chat.id, text=text)

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

    async def _forward_feedback(self, update: Update, context: ContextTypes.DEFAULT_TYPE, text: str) -> None:
        owner_chat_id = os.environ.get("OWNER_CHAT_ID")
        if owner_chat_id:
            user = update.effective_user
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
