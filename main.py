import asyncio
import logging
import signal
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from bot.handlers import start, help_command, handle_document, handle_text, register_handlers
from services.storage import StorageService
from config import CV_ANALYZER_BOT_TOKEN, DB_URL

# Set the root logger to WARNING level
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", 
    level=logging.WARNING
)

# Silence all loggers except for critical messages
for logger_name in logging.root.manager.loggerDict:
    logging.getLogger(logger_name).setLevel(logging.CRITICAL)

# Set your application's logger to INFO or WARNING as needed
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)  # or logging.WARNING if you want even less output

async def main() -> None:
    # Check if required environment variables are set
    if not CV_ANALYZER_BOT_TOKEN:
        logger.error("CV_ANALYZER_BOT_TOKEN is not set in the environment variables.")
        return
    if not DB_URL:
        logger.error("DB_URL is not set in the environment variables.")
        return

    # Create the StorageService
    storage_service = StorageService(DB_URL)

    # Prepare the PostgreSQL database
    try:
        await storage_service.prepare_postgres_database()
    except Exception as e:
        logger.error(f"Failed to prepare database: {e}")
        return

    # Create the Application and pass it your bot's token.
    application = Application.builder().token(CV_ANALYZER_BOT_TOKEN).build()

    # Add handlers
    application.add_handler(CommandHandler("start", lambda update, context: start(update, context, storage_service)))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(MessageHandler(filters.Document.ALL, lambda update, context: handle_document(update, context, storage_service)))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, lambda update, context: handle_text(update, context, storage_service)))

    # Add this logging statement
    application.add_handler(MessageHandler(filters.Document.ALL, lambda update, context: logger.info(f"Received document: {update.message.document.file_name}")))

    # Register the rating handler
    register_handlers(application, storage_service)

    # Add user count handler
    async def user_count(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        try:
            users = await storage_service.get_all_users()
            await update.message.reply_text(f"Total users in database: {len(users)}")
        except Exception as e:
            logger.error(f"Error in user_count command: {e}", exc_info=True)
            await update.message.reply_text("An error occurred while retrieving user count.")

    application.add_handler(CommandHandler("user_count", user_count))

    # Set up graceful shutdown
    stop_signal = asyncio.Event()
    
    def signal_handler():
        """Handles shutdown signals"""
        stop_signal.set()

    # Get the current event loop
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, signal_handler)

    try:
        await application.initialize()
        await application.start()
        await application.updater.start_polling(allowed_updates=Update.ALL_TYPES)
        logger.info("Bot started. Press Ctrl+C to stop.")
        await stop_signal.wait()  # Wait until the stop signal is received
    except Exception as e:
        logger.error(f"Error occurred: {e}")
    finally:
        logger.info("Stopping the bot...")
        await application.stop()
        await application.shutdown()
        logger.info("Bot stopped gracefully")

if __name__ == "__main__":
    asyncio.run(main())