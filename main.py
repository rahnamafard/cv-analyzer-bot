import asyncio
import logging
import os
from aiohttp import web
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from bot.handlers import start, help_command, handle_document, handle_text, register_handlers
from services.storage import StorageService
from config import CV_ANALYZER_BOT_TOKEN, DB_URL

# Set the root logger to DEBUG level
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", 
    level=logging.DEBUG
)

# Set your application's logger to DEBUG
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

async def handle_webhook(request):
    logger.info("Webhook called")
    try:
        update = await request.json()
        logger.info(f"Received update: {update}")
        await application.process_update(Update.de_json(update, application.bot))
        return web.Response()
    except Exception as e:
        logger.error(f"Error in webhook handler: {e}", exc_info=True)
        return web.Response(status=500)

async def health_check(request):
    return web.Response(text="Bot is running")

async def main() -> None:
    global application  # We'll need to access this in handle_webhook

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

    try:
        await application.initialize()
        await application.start()
        
        # Bind to PORT if defined, otherwise default to 5000.
        port = int(os.environ.get('PORT', 5000))
        
        # Set up the webhook
        webhook_path = f"/webhook/{CV_ANALYZER_BOT_TOKEN}"
        webhook_url = f"{os.environ.get('RENDER_EXTERNAL_URL')}{webhook_path}"
        await application.bot.set_webhook(webhook_url)
        
        # Set up the web application
        app = web.Application()
        app.router.add_post(f"/{webhook_path}", handle_webhook)
        app.router.add_get("/health", health_check)
        
        # Start the web application
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, '0.0.0.0', port)
        await site.start()
        
        logger.info(f"Server started on port {port}")
        
        # Keep the application running
        while True:
            await asyncio.sleep(3600)  # Sleep for an hour (or any other duration)
    except Exception as e:
        logger.error(f"Error occurred: {e}")
    finally:
        logger.info("Stopping the bot...")
        await application.stop()
        await application.shutdown()
        logger.info("Bot stopped gracefully")

if __name__ == "__main__":
    asyncio.run(main())