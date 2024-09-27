import asyncpg
import logging
from telegram.ext import Application, CommandHandler, MessageHandler, filters, BasePersistence, ContextTypes
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

async def create_tables():
    try:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS bot_data (
                    id SERIAL PRIMARY KEY,
                    data JSONB NOT NULL
                );

                CREATE TABLE IF NOT EXISTS cv_data (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    username TEXT,
                    file_id TEXT NOT NULL,
                    analyzed_data TEXT NOT NULL,
                    model TEXT NOT NULL,
                    rating INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS cv_job_positions (
                    id SERIAL PRIMARY KEY,
                    cv_id INTEGER REFERENCES cv_data(id),
                    job_position TEXT NOT NULL
                );
            """)
        logging.info("Tables created successfully")
    except Exception as e:
        logging.error(f"Error creating tables: {e}")
        raise

class CustomPostgreSQLPersistence(BasePersistence):
    def __init__(self, load_func, save_func):
        super().__init__()
        self.load_func = load_func
        self.save_func = save_func
        self.data = None

    async def get_bot_data(self):
        if self.data is None:
            self.data = await self.load_func() or {}
        return self.data

    async def update_bot_data(self, data):
        self.data = data
        await self.save_func(json.dumps(data))

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
    
    # Add your command handlers here
    from bot.handlers import handle_document, handle_text, register_handlers
    application.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    register_handlers(application)
    
    # Add error handler
    application.add_error_handler(error_handler)
    
    return application

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logging.error(f"Exception while handling an update: {context.error}")

async def main():
    application = None
    try:
        await create_tables()  # Create all necessary tables
        
        application = await setup_application()
        await application.initialize()
        await application.start()
        
        logging.info("Application started successfully. Press Ctrl+C to stop.")
        await application.run_polling(drop_pending_updates=True)
    except asyncio.CancelledError:
        logging.info("Application is shutting down...")
    except Exception as e:
        logging.error(f"An error occurred: {e}")
    finally:
        if application:
            if application.running:
                await application.stop()
            await application.shutdown()

def run_main():
    try:
        loop = asyncio.get_event_loop()
        loop.run_until_complete(main())
    except KeyboardInterrupt:
        logging.info("Bot stopped by user. Shutting down.")
    except RuntimeError as e:
        if str(e) == "Event loop is closed":
            logging.info("Event loop was closed. Application has shut down.")
        else:
            logging.exception(f"An unexpected RuntimeError occurred: {e}")
    except Exception as e:
        logging.exception(f"An unexpected error occurred: {e}")
    finally:
        if not loop.is_closed():
            loop.close()

if __name__ == '__main__':
    run_main()