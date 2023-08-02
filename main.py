from bot import Bot
from logger import LOGGER

def main(event=0, context=0):
    LOGGER.info("Bot is starting")
    bot = Bot()
    bot.send_daily_message()

if __name__ == "__main__":
    main()