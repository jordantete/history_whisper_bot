import asyncio, json
from bot import Bot
from database import Database
from logger import LOGGER

OK_RESPONSE = {'statusCode': 200, 'headers': {'Content-Type': 'application/json'}, 'body': json.dumps('ok')}
ERROR_RESPONSE = {'statusCode': 400, 'body': json.dumps('Oops, something went wrong!')}

def lambda_handler(event=0, context=0):
    return asyncio.get_event_loop().run_until_complete(main(event, context))

async def main(event=0, context=0):
    LOGGER.info("Webhook is triggered")
    database = Database()
    bot = Bot(database=database)
    try:
        await bot.start(event=event)
        LOGGER.info("Return OK RESPONSE")
        return OK_RESPONSE
    except:
        LOGGER.info("Return ERROR RESPONSE")
        return ERROR_RESPONSE


if __name__ == "__main__":
    asyncio.get_event_loop().run_until_complete(main())