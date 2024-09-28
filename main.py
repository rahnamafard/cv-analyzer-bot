import asyncio
import logging
import signal
import os
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from bot.handlers import start, help_command, handle_document, handle_text, register_handlers
from services.storage import StorageService
from config import CV_ANALYZER_BOT_TOKEN, DB_URL
from aiohttp import web

# Set the root logger to DEBUG level
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", 
    level=logging.DEBUG
)

# Set your application's logger to DEBUG
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

async def handle_webhook(request):
    update = await request.json()
    await application.process_update(Update.de_json(update, application.bot))
    return web.Response()

async def main() -> None:
    global application
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
        
        port = int(os.environ.get('PORT', 5000))
        
        # Use a more specific webhook path
        webhook_path = f"webhook/{CV_ANALYZER_BOT_TOKEN}"
        webhook_url = f"{os.environ.get('RENDER_EXTERNAL_URL')}/{webhook_path}"
        await application.bot.set_webhook(webhook_url)
        
        # Set up the web application
        app = web.Application()
        app.router.add_post(f"/{webhook_path}", handle_webhook)
        
        # Start the webhook
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, '0.0.0.0', port)
        await site.start()
        
        logger.info(f"Server started on port {port}")
        await asyncio.Event().wait()  # Run forever
    except Exception as e:
        logger.error(f"Error occurred: {e}")
    finally:
        logger.info("Stopping the bot...")
        await application.stop()
        await application.shutdown()
        logger.info("Bot stopped gracefully")

if __name__ == "__main__":
    asyncio.run(main())