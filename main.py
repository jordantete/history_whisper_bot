from bot import Bot
from logger import LOGGER
from database import Database

def main(event=0, context=0):
    LOGGER.info("Webhook is triggered")
    database = Database()
    bot = Bot(database=database)
    bot.start(event=event)

if __name__ == "__main__":
    main()