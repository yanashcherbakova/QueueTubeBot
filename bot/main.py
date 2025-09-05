from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters
from bot.utility import is_youtube_link
from bot.user_class import User
from bot.yt_parse import detect_youtube_type
import os
import logging
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("TELEGRAM_TOKEN")
if not TOKEN:
    raise RuntimeError("TELEGRAM_TOKEN not found")

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

async def start(update, context):
    #get user info
    tg_id = update.message.from_user.id
    username = update.message.from_user.username

    Cur_user = User(tg_id, username)

    try:
        Cur_user.save_to_db()
        Cur_user.get_or_create_default_playlist()
    except Exception as e:
        logger.exception("🔴 Failed to init user")
        await update.message.reply_text("🔴 Internal error. Failed to init user")
        return
    
    context.user_data["user"] = Cur_user
    await update.message.reply_text(f"Hi, @{username}! Send me youtube playlist link to start")
    

async def ingest_link(update, context):
    if not update.message or not update.message.text:
        logger.error("🔴 Not a link")
        await update.message.reply_text("Error: Not a link") 
        return
    
    text=update.message.text.strip()
    if not is_youtube_link(text):
        logger.error("🔴 Not YouTube link")
        await update.message.reply_text("Error: Not YouTube link")
        return
    
    obj_type = detect_youtube_type(text)
    try:
        if obj_type == "playlist":
            ...
        elif obj_type == "video":
            ...
        else:
            logger.error("🔴 Type error: not a video / not a playlist")
            await update.message.reply_text("Type error: not a video / not a playlist")
    except Exception:
        logger.exception("🔴 Failed to ingest link")
        await update.message.reply_text("Internal error while saving link.")
            


if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, ingest_link))

    app.run_polling()