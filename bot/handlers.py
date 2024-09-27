import io
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import ContextTypes, CallbackQueryHandler
from config import GOOGLE_GENERATIVE_AI_KEY
from services.cv_analyzer import CVAnalyzer
from services.storage import StorageService
from io import BytesIO
from PIL import Image
from telegram.error import BadRequest, RetryAfter, TimedOut
import asyncio
import logging

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

cv_analyzer = CVAnalyzer(GOOGLE_GENERATIVE_AI_KEY)

# Define MAX_MESSAGE_LENGTH constant
MAX_MESSAGE_LENGTH = 4096

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE, storage_service: StorageService) -> None:
    user = update.effective_user
    try:
        saved_user = await storage_service.save_user(user.id, user.username)
        logger.info(f"User saved: {saved_user}")
        await update.message.reply_text(f"سلام {user.first_name}! من ربات تحلیلگر رزومه هستم. لطفاً رزومه خود را به صورت فایل PDF ارسال کنید تا آن را حلیل کنم.")
    except Exception as e:
        logger.error(f"Error saving user: {e}", exc_info=True)
        await update.message.reply_text("متأسفانه در حال حاضر مشکلی پیش آمده است. لطفاً بعداً دوباره تلاش کنید.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("برای تحلیل رزومه، لطفاً آن را به صورت فایل PDF ارسال کنید. من آن را بررسی کرده و نتایج تحلیل را برای شما ارسال خواهم کرد.")

async def check_channel_membership(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    user_id = update.effective_user.id
    try:
        chat_member = await context.bot.get_chat_member(chat_id='@growly_ir', user_id=user_id)
        is_member = chat_member.status in ['member', 'administrator', 'creator']
        logger.info(f"User {user_id} channel membership status: {is_member}")
        return is_member
    except Exception as e:
        logger.error(f"Error checking channel membership: {e}")
        return False  # Assume not a member if there's an error

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE, storage_service: StorageService) -> None:
    logger.info("handle_document function called")
    max_retries = 3
    for attempt in range(max_retries):
        try:
            user = update.effective_user
            logger.info(f"Processing document for user: {user.id}")
            await storage_service.save_user(user.id, user.username)
            
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
            
            # Log the model name from cv_analyzer
            logger.info(f"Model name from cv_analyzer: {cv_analyzer.model.model_name}")
            
            cv_data = {
                "user_id": update.effective_user.id,
                "username": update.effective_user.username,
                "file_id": update.message.document.file_id,
                "analyzed_data": analysis,
                "model": cv_analyzer.model.model_name,
                "rating": None
            }
            
            # Log the cv_data before saving
            logger.info(f"cv_data before saving: {cv_data}")
            
            cv_id = await storage_service.save_cv(cv_data)
            
            # Increment the user's CV count
            await storage_service.increment_user_cv_count(user.id)
            
            if job_positions:
                await storage_service.save_cv_job_positions(cv_id, job_positions)
            
            # Split the analysis into chunks
            chunks = split_message(analysis)
            
            try:
                for chunk in chunks:
                    await update.message.reply_text(chunk, parse_mode=ParseMode.MARKDOWN_V2)
            except BadRequest as e:
                if "can't parse entities" in str(e).lower():
                    logger.warning(f"Markdown parsing failed. Sending message without formatting: {str(e)}")
                    for chunk in chunks:
                        await update.message.reply_text(chunk.replace('*', '').replace('\\', ''))
                else:
                    raise

            # Send rating options
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
            
            await update.message.reply_text(
                "لطفاً کیفیت این تحلیل را ارزیابی کنید:",
                reply_markup=reply_markup
            )
            
            break  # If successful, break out of the retry loop
        except (RetryAfter, TimedOut, asyncio.TimeoutError) as e:
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt  # Exponential backoff
                logger.warning(f"Attempt {attempt + 1} failed. Retrying in {wait_time} seconds...")
                await asyncio.sleep(wait_time)
            else:
                logger.error(f"Failed after {max_retries} attempts: {str(e)}")
                await update.message.reply_text("Sorry, there was an error processing your document. Please try again later.")
                return
        except Exception as e:
            logger.error(f"Unexpected error: {str(e)}")
            await update.message.reply_text("An unexpected error occurred. Please try again later.")
            return

def split_message(text, max_length=MAX_MESSAGE_LENGTH):
    """Split a message into chunks of maximum length."""
    chunks = []
    current_chunk = ""

    for line in text.split('\n'):
        if len(current_chunk) + len(line) + 1 <= max_length:
            current_chunk += line + '\n'
        else:
            chunks.append(current_chunk.strip())
            current_chunk = line + '\n'

    if current_chunk:
        chunks.append(current_chunk.strip())

    return chunks

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE, storage_service: StorageService) -> None:
    await update.message.reply_text("لطفاً رزومه خود را به صورت فای PDF ارسال کنید.")

async def handle_rating(update: Update, context: ContextTypes.DEFAULT_TYPE, storage_service: StorageService) -> None:
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

def register_handlers(application, storage_service: StorageService):
    application.add_handler(CallbackQueryHandler(lambda update, context: handle_rating(update, context, storage_service), pattern=r"^rate_"))
