import asyncpg
import logging
from telegram.ext import Application, CommandHandler, MessageHandler, filters, BasePersistence
from telegram.error import NetworkError, Conflict
import asyncio
import json

from config import DB_URL, CV_ANALYZER_BOT_TOKEN

async def get_db_pool():
    return await asyncpg.create_pool(DB_URL)

async def save_db(data):
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        await conn.execute("INSERT INTO bot_data (id, data) VALUES (1, $1) ON CONFLICT (id) DO UPDATE SET data = $1", data)

async def load_db():
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        result = await conn.fetchval("SELECT data FROM bot_data WHERE id = 1")
    return json.loads(result) if result else None

async def create_table():
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS bot_data (
                id SERIAL PRIMARY KEY,
                data JSONB NOT NULL
            )
        """)

class CustomPostgreSQLPersistence(BasePersistence):
    def __init__(self, load_func, save_func):
        super().__init__()
        self.load_func = load_func
        self.save_func = save_func
        self.data = None

    async def get_data(self):
        if self.data is None:
            self.data = await self.load_func() or {}
        return self.data

    async def update_data(self, data):
        self.data = data
        await self.save_func(json.dumps(data))

    async def get_bot_data(self):
        return await self.get_data()

    async def update_bot_data(self, data):
        await self.update_data(data)

    async def get_chat_data(self):
        return {}

    async def update_chat_data(self, chat_id, data):
        pass

    async def get_user_data(self):
        return {}

    async def update_user_data(self, user_id, data):
        pass

    async def get_conversations(self, name):
        return {}

    async def update_conversation(self, name, key, new_state):
        pass

    async def drop_chat_data(self, chat_id):
        pass

    async def drop_user_data(self, user_id):
        pass

    async def refresh_user_data(self, user_id, user_data):
        pass

    async def refresh_chat_data(self, chat_id, chat_data):
        pass

    async def refresh_bot_data(self, bot_data):
        pass

    async def flush(self):
        if self.data:
            await self.save_func(json.dumps(self.data))

    async def update_callback_data(self, data):
        pass

    async def get_callback_data(self):
        return None

async def setup_application():
    persistence = CustomPostgreSQLPersistence(load_db, save_db)
    application = Application.builder().token(CV_ANALYZER_BOT_TOKEN).persistence(persistence).build()
    
    # Add your command handlers here, for example:
    # application.add_handler(CommandHandler("start", start_command))
    # application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    return application

async def main():
    application = None
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