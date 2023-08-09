import os, random, logging, json, telegram
from database import Database
from typing import List
from historical_figure import HistoricalFigure
from utils import Utils
from logger import LOGGER
from asyncio import run

TELEGRAM_BOT_TOKEN = Utils.get_environment_varibale("TELEGRAM_BOT_TOKEN")
OK_RESPONSE = {'statusCode': 200, 'headers': {'Content-Type': 'application/json'}, 'body': json.dumps('ok')}
ERROR_RESPONSE = {'statusCode': 400, 'body': json.dumps('Oops, something went wrong!')}

class Bot:
    def __init__(self, database: Database):
        self.bot = telegram.Bot(TELEGRAM_BOT_TOKEN)
        self.database = database
    
    async def __send_message(self, chat_id: str, text: str):
        await self.bot.sendMessage(chat_id=chat_id, text=text)
    
    def start(self, event):
        LOGGER.info("Bot started")
        LOGGER.info('Event: {}'.format(event))

        if event.get('requestContext', {}).get('httpMethod') == 'POST' and event.get('body'): 
            LOGGER.info('Message received')
            update = telegram.Update.de_json(json.loads(event.get('body')), self.bot)
            chat_id = update.message.chat.id
            message = update.message.text
            self.__hendle_input_messages(chat_id=chat_id, message=message)
            LOGGER.info(f'Message sent to: chatID: {chat_id} - text: {message}')
            return OK_RESPONSE
        else:
            LOGGER.error('An error occured')
            return ERROR_RESPONSE
    
    def __hendle_input_messages(self, chat_id: str, message: str):
        if message == '/start':
            LOGGER.info("Handle start message")
            text = "Welcome to the Historical Figure Bot!"
            run(self.__send_message(chat_id=chat_id, text=text))
        elif message == '/help':
            LOGGER.info("Handle help message")
            text = "This is an helpful message ;)"
            run(self.__send_message(chat_id=chat_id, text=text))
        elif message == '/new_figure':
            LOGGER.info("Handle new_figure message")
            self.__handle_new_figure_message(chat_id=chat_id)
        else:
            LOGGER.info("Unknown message received")
            text = "Please enter a valid command"
            run(self.__send_message(chat_id=chat_id, text=text))

    def __handle_new_figure_message(self, chat_id: str):
        historical_figure = self.database.get_random_figure()
        if historical_figure:
            text = f"{historical_figure.name}\n{historical_figure.description}"
            run(self.__send_message(chat_id=chat_id, text=text))
        else:
            run(self.__send_message(chat_id=chat_id, text=text))
