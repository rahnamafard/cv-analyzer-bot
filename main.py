import logging
from telegram.ext import Application, CommandHandler, MessageHandler, filters
from telegram.request import HTTPXRequest
import asyncio
import signal
from telegram.error import NetworkError
from flask import Flask, send_file
import os

from config import CV_ANALYZER_BOT_TOKEN
from bot.commands import start, help_command
from bot.handlers import handle_document, handle_text, register_handlers
from bot.middleware import rate_limiter, user_auth

# Set up logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.DEBUG
)

# Create Flask app
flask_app = Flask(__name__)

# Add route for database download
@flask_app.route('/download_db')
def download_db():
    db_path = './cv_analyzer.db'
    if os.path.exists(db_path):
        return send_file(db_path, as_attachment=True)
    else:
        return "Database file not found", 404

def apply_middleware(handler, middlewares):
    async def wrapped(update, context):
        async def next_handler(update, context):
            return await handler(update, context)
        
        for middleware in reversed(middlewares):
            next_handler = lambda u, c, nh=next_handler: middleware(u, c, nh)
        
        return await next_handler(update, context)
    return wrapped

async def setup_application():
    # Create a custom request object with a larger connection pool
    request = HTTPXRequest(connection_pool_size=8, pool_timeout=None)

    # Create the Application and pass it your bot's token and the custom request object
    application = Application.builder().token(CV_ANALYZER_BOT_TOKEN).request(request).build()

    # Add command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))

    # Add message handlers with middleware
    document_handler = apply_middleware(handle_document, [rate_limiter, user_auth])
    text_handler = apply_middleware(handle_text, [rate_limiter, user_auth])

    application.add_handler(MessageHandler(filters.Document.ALL, document_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

    # Register the rating handler
    register_handlers(application)

    return application

async def main():
    application = None
    try:
        application = await setup_application()
        await application.initialize()
        await application.start()
        logging.info("Application started successfully. Press Ctrl+C to stop.")
        await application.updater.start_polling(drop_pending_updates=True)

        # Set up signal handlers
        loop = asyncio.get_running_loop()
        stop = loop.create_future()
        loop.add_signal_handler(signal.SIGINT, stop.set_result, None)
        loop.add_signal_handler(signal.SIGTERM, stop.set_result, None)

        # Start Flask app in a separate thread
        from threading import Thread
        Thread(target=flask_app.run, kwargs={'host': '0.0.0.0', 'port': 10000}).start()

        await stop  # Wait until SIGINT or SIGTERM is received
    except Exception as e:
        logging.error(f"An error occurred: {e}")
    finally:
        if application:
            try:
                if application.updater.running:
                    await application.updater.stop()
                await application.stop()
                await application.shutdown()
            except Exception as e:
                logging.error(f"Error during shutdown: {e}")
        logging.info("Application has been shut down.")

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Bot stopped by user. Shutting down.")
    except Exception as e:
        logging.exception(f"An unexpected error occurred: {e}")