import io
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import ContextTypes, CallbackQueryHandler
from config import GOOGLE_GENERATIVE_AI_KEY
from services.cv_analyzer import CVAnalyzer
from services.storage import StorageService
from io import BytesIO
from PIL import Image
from telegram.error import BadRequest
import logging

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

cv_analyzer = CVAnalyzer(GOOGLE_GENERATIVE_AI_KEY)
storage_service = StorageService()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    await storage_service.save_user(user.id, user.username)
    await update.message.reply_text(f"سلام {user.first_name}! من ربات تحلیلگر رزومه هستم. لطفاً رزومه خود را به صورت فایل PDF ارسال کنید تا آن را تحلیل کنم.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("برای تحلیل رزومه، لطفاً آن را به صورت فایل PDF ارسال کنید. من آن را بررسی کرده و نتایج تحلیل را برای شما ارسال خواهم کرد.")

async def check_channel_membership(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    user_id = update.effective_user.id
    chat_member = await context.bot.get_chat_member(chat_id='@growly_ir', user_id=user_id)
    return chat_member.status in ['member', 'administrator', 'creator']

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        if not await check_channel_membership(update, context):
            keyboard = [[InlineKeyboardButton("عضویت در کانال", url="https://t.me/growly_ir")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(
                "برای استفاده از این ربات، لطفاً ابتدا در کانال گرولی عضو شوید:",
                reply_markup=reply_markup
            )
            return

        processing_message = await update.message.reply_text("در حال پردازش رزومه شما. لطفاً چند لحظه صبر کنید...")

        file = await update.message.document.get_file()
        file_content = await file.download_as_bytearray()
        mime_type = update.message.document.mime_type
        
        if mime_type == 'application/pdf':
            resume_file = BytesIO(file_content)
        elif mime_type.startswith('image/'):
            image = Image.open(BytesIO(file_content))
            pdf_buffer = BytesIO()
            image.save(pdf_buffer, 'PDF')
            resume_file = BytesIO(pdf_buffer.getvalue())
        else:
            raise ValueError("Unsupported file type. Please upload a PDF or image file.")
        
        analysis, job_positions = cv_analyzer.analyze_cv(resume_file)
        
        cv_data = {
            "user_id": update.effective_user.id,
            "username": update.effective_user.username,
            "file_id": update.message.document.file_id,
            "analyzed_data": analysis,
            "model": cv_analyzer.model.model_name,
            "rating": None
        }
        cv_id = await storage_service.save_cv(cv_data)
        
        if job_positions:
            await storage_service.save_cv_job_positions(cv_id, job_positions)
        
        rating_options = [
            ("⭐️⭐️⭐️⭐️⭐️ عالی", 5),
            ("⭐️⭐️⭐️⭐️ خوب", 4),
            ("⭐️⭐️⭐️ متوسط", 3),
            ("⭐️⭐️ بد", 2),
            ("⭐️ افتضاح", 1)
        ]
        
        keyboard = [
            [InlineKeyboardButton(text, callback_data=f"rate_{cv_id}_{rating}")]
            for text, rating in rating_options
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        try:
            await update.message.reply_text(analysis, parse_mode=ParseMode.MARKDOWN_V2)
            await update.message.reply_text(
                "لطفاً کیفیت این تحلیل را ارزیابی کنید:",
                reply_markup=reply_markup
            )
        except BadRequest as e:
            if "can't parse entities" in str(e).lower():
                logger.warning(f"Markdown parsing failed. Sending message without formatting: {str(e)}")
                await update.message.reply_text(analysis.replace('*', '').replace('\\', ''))
            else:
                raise
        
    except Exception as e:
        logger.error(f"Error in handle_document: {str(e)}")
        error_message = f"متأسفانه خطایی در هنگام تحلیل رزومه شما رخ داد:\n\n{str(e)}\n\nلطفاً بعداً دوباره تلاش کنید یا در صورت تداوم مشکل با پشتیبانی تماس بگیرید."
        await update.message.reply_text(error_message)

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("لطفاً رزومه خود را به صورت فای PDF ارسال کنید.")

async def handle_rating(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    cv_id, rating = query.data.split("_")[1:]
    cv_id = int(cv_id)
    rating = int(rating)

    await storage_service.update_cv_rating(cv_id, rating)

    rating_text = {
        5: "عالی",
        4: "خوب",
        3: "متوسط",
        2: "بد",
        1: "افتضاح"
    }.get(rating, "نامشخص")

    await query.edit_message_reply_markup(reply_markup=None)
    await query.message.reply_text(f"ممنون از ارزیابی شما! شما به این تحلیل {rating} ستاره ({rating_text}) دادید.")

def register_handlers(application):
    application.add_handler(CallbackQueryHandler(handle_rating, pattern=r"^rate_"))
