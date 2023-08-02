import os, random, telebot
from database import Database
from typing import List
from historical_figure import HistoricalFigure
from utils import Utils

TELEGRAM_BOT_TOKEN = Utils.get_environment_varibale("TELEGRAM_BOT_TOKEN")

class Bot:
    def __init__(self):
        self.bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)
        self.database = Database()

    def send_daily_message(self):
        figure = self.database.get_random_figure()
        message = f"{figure.name}\n{figure.description}"
        self.send_message("CHAT_ID", message)
    
    def start(self):
        @self.bot.message_handler(commands=['start'])
        def handle_start(message):
            self.send_message(message.chat.id, "Welcome to the Historical Figure Bot!")

        @self.bot.message_handler(commands=['help'])
        def handle_help(message):
            help_message = Database.get_help_message()
            self.send_message(message.chat.id, help_message)

        @self.bot.message_handler(commands=['new_figure'])
        def handle_new_figure(message):
            historical_figure = Database.get_random_historical_figure()
            if historical_figure:
                message_text = f"{historical_figure.name}\n{historical_figure.description}"
                self.send_message(message.chat.id, message_text)
            else:
                self.send_message(message.chat.id, "No historical figures found.")

        self.bot.polling()
    
    def send_message(self, chat_id: str, message: str):
        self.bot.send_message(chat_id, message)

    def get_users(self) -> List[str]:
        # TODO: Implement function to get all users subscribed to the bot
        pass

