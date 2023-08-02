from bot import Bot

def handler(event, context):
    bot = Bot()
    printt("HELLO")
    bot.send_daily_message()
