import asyncio
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters

from config import CV_ANALYZER_BOT_TOKEN
from bot.handlers import start, help_command, handle_document, handle_text, register_handlers
from services.storage import StorageService

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

async def main() -> None:
    # Create the StorageService
    storage_service = StorageService()

    # Prepare the PostgreSQL database
    await storage_service.prepare_postgres_database()

    # Create the Application and pass it your bot's token.
    application = Application.builder().token(CV_ANALYZER_BOT_TOKEN).build()

    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    # Register the rating handler
    register_handlers(application)

    # Start the bot
    await application.initialize()
    await application.start()
    await application.updater.start_polling(allowed_updates=Update.ALL_TYPES)

    try:
        await application.updater.stop()
    finally:
        await application.stop()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except RuntimeError as e:
        if "Event loop is closed" in str(e):
            # The event loop is already closed, which is fine
            pass
        else:
            # Some other RuntimeError occurred, so we re-raise it
            raise