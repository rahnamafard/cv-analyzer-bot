from telegram import Update
from telegram.ext import ContextTypes

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("به ربات تحلیل‌گر رزومه خوش آمدید! برای شروع، فایل PDF رزومه خود را آپلود کنید.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = """
    دستورات ربات تحلیل‌گر رزومه:
    /start - شروع کار با ربات
    /help - نمایش این پیام راهنما
    
    برای تحلیل رزومه خود، کافیست یک فایل PDF آپلود کنید.
    """
    await update.message.reply_text(help_text)
