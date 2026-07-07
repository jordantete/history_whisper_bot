from dotenv import load_dotenv
from src.bot import Bot
from src.database import Database
from src.logger import LOGGER


def main():
    load_dotenv()
    LOGGER.info("Starting Historical Figures Whisper Bot")
    database = Database()
    bot = Bot(database=database)
    bot.run()


if __name__ == "__main__":
    main()
