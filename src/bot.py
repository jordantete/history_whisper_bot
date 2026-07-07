import os
from datetime import date

from src.database import Database
from src.utils import Utils
from src.logger import LOGGER
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, CallbackQueryHandler


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

    def register_handlers(self):
        self.application.add_handler(CommandHandler('start', self.__start_handler))
        self.application.add_handler(CommandHandler('help', self.__help_handler))

    def run(self):
        LOGGER.info("Bot starting in long-polling mode")
        self.register_handlers()
        self.application.run_polling()
