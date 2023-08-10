from database import Database
from typing import List
from historical_figure import HistoricalFigure
from utils import Utils
from logger import LOGGER
import asyncio, json
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters

TELEGRAM_BOT_TOKEN = Utils.get_environment_varibale("TELEGRAM_BOT_TOKEN")

class Bot:
    def __init__(self, database: Database):
        self.application = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
        self.database = database
    
    async def __start_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        LOGGER.info("Start handler command called")
        text = "Welcome to the Historical Figures Bot!"
        await context.bot.send_message(chat_id=update.effective_chat.id, text=text)

    async def __help_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        LOGGER.info("Help handler command called")
        text = "This is an helpful message ;)"
        await context.bot.send_message(chat_id=update.effective_chat.id, text=text)

    async def __new_figure_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        LOGGER.info("Help handler command called")
        historical_figure = self.database.get_random_figure()
        if historical_figure:
            text = f"{historical_figure.name}\n{historical_figure.description}"
            await context.bot.send_message(chat_id=update.effective_chat.id, text=text)
        else:
            await context.bot.send_message(chat_id=update.effective_chat.id, text="No figures found :'()")
    
    async def start(self, event):
        LOGGER.info('Bot started with Event: {}'.format(event))

        start_handler = CommandHandler('start', self.__start_handler)
        self.application.add_handler(start_handler)

        help_handler = CommandHandler('help', self.__help_handler)
        self.application.add_handler(help_handler)

        new_figure_handler = CommandHandler('new_figure', self.__new_figure_handler)
        self.application.add_handler(new_figure_handler)
        
        LOGGER.info("App initialize")
        await self.application.initialize()
        await self.application.process_update(Update.de_json(json.loads(event["body"]), self.application.bot))
        await self.application.shutdown()
        LOGGER.info("App shutdown")


