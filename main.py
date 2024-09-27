import asyncpg
import logging
from telegram.ext import Application, CommandHandler, MessageHandler, filters
from telegram.error import NetworkError, Conflict
import asyncio

from config import CV_ANALYZER_BOT_TOKEN, DB_URL

async def get_db_pool():
    return await asyncpg.create_pool(DB_URL)

async def save_db(data):
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        await conn.execute("INSERT INTO bot_data (data) VALUES ($1) ON CONFLICT (id) DO UPDATE SET data = $1", data)

async def load_db():
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        result = await conn.fetchval("SELECT data FROM bot_data WHERE id = 1")
    return result

async def setup_application():
    persistence = CustomPostgreSQLPersistence(load_db, save_db)
    
class CustomPostgreSQLPersistence:
    def __init__(self, load_func, save_func):
        self.load_func = load_func
        self.save_func = save_func
        self.data = None

    async def get_data(self):
        if self.data is None:
            self.data = await self.load_func() or {}
        return self.data

    async def update_data(self, data):
        self.data = data
        await self.save_func(data)

async def main():
    try:
        application = await setup_application()
        await application.initialize()
        await application.start()
        logging.info("Application started successfully. Press Ctrl+C to stop.")
        await application.run_polling(drop_pending_updates=True)
    except Conflict:
        logging.warning("Conflict detected. Waiting before restarting...")
        await asyncio.sleep(30)
    except Exception as e:
        logging.error(f"An error occurred: {e}")
    finally:
        if application:
            await application.shutdown()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Bot stopped by user. Shutting down.")
    except Exception as e:
        logging.exception(f"An unexpected error occurred: {e}")