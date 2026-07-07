from src.database import Database
from src.utils import Utils
from src.logger import LOGGER
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler


class Bot:
    def __init__(self, database: Database):
        token = Utils.get_environment_variable("TELEGRAM_BOT_TOKEN")
        self.application = ApplicationBuilder().token(token).build()
        self.database = database
        self.localizable_strings = Utils.load_localizable_data()
        self.selected_language = "en"

    async def __start_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        LOGGER.info("Start handler command called")
        text = Utils.localize("start-message", self.selected_language, self.localizable_strings)
        buttons = [
            InlineKeyboardButton("start", callback_data="start"),
            InlineKeyboardButton("help", callback_data="help"),
            InlineKeyboardButton("new_figure", callback_data="new_figure"),
        ]

        reply_markup = InlineKeyboardMarkup([buttons])
        await context.bot.send_message(chat_id=update.effective_chat.id, text=text, reply_markup=reply_markup)

    async def __help_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        LOGGER.info("Help handler command called")
        text = Utils.localize("help-message", self.selected_language, self.localizable_strings)
        await context.bot.send_message(chat_id=update.effective_chat.id, text=text)

    async def __new_figure_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        LOGGER.info("New figure handler command called")
        historical_figure = self.database.get_random_figure()
        if historical_figure:
            text = f"{historical_figure.name}\n{historical_figure.description}"
            await context.bot.send_message(chat_id=update.effective_chat.id, text=text)
        else:
            await context.bot.send_message(chat_id=update.effective_chat.id, text="No figures found, please try again.")

    def register_handlers(self):
        self.application.add_handler(CommandHandler('start', self.__start_handler))
        self.application.add_handler(CommandHandler('help', self.__help_handler))
        self.application.add_handler(CommandHandler('new_figure', self.__new_figure_handler))

    def run(self):
        LOGGER.info("Bot starting in long-polling mode")
        self.register_handlers()
        self.application.run_polling()
