from telegram import BotCommand
from telegram.constants import ParseMode
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters
from bot.db_connection import mark_video_done, resolve_playlist_arg
from bot.utility import is_youtube_link, YOUTUBE_URL_RE
from bot.playlist_service import PlaylistService
from bot.user_class import User
from bot.playlist_class import Playlist
from bot.yt_parse import detect_youtube_type
import html
import os
import logging
from dotenv import load_dotenv
from functools import wraps

load_dotenv()
TOKEN = os.getenv("TELEGRAM_TOKEN")
if not TOKEN:
    raise RuntimeError("TELEGRAM_TOKEN not found")

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)


#Decorator to check User before running handler
def require_user(func):
    @wraps(func)
    async def wrapper(update, context, *args, **kwargs):
        try:
            Cur_user = User.validate_or_reload(context, update, ensure_default=False)
            context.user_data["user"] = Cur_user 
        except Exception:
            logger.exception("🔴 Failed to restore/init user")
            await update.message.reply_text("🔴 Internal error. Please try again.")
            return
        return await func(update, context, *args, **kwargs)
    return wrapper

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
    await update.message.reply_text(f"Hi, @{username}! Send me youtube playlist link to start\nUse /help for command list")
    

@require_user
async def ingest_link(update, context):
    Cur_user = context.user_data["user"]

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
            playlist_id = PlaylistService.add_playlist(Cur_user.user_id, text)
            if playlist_id:
                await update.message.reply_text("Playlist saved")
            else:
                await update.message.reply_text("Hi! This playlist already exists")

        elif obj_type == "video":
            if not Cur_user.default_playlist_id:
                Cur_user.get_or_create_default_playlist()
            title = PlaylistService.add_video(Cur_user.default_playlist_id, text)
            PlaylistService.set_playlist_await(Cur_user.default_playlist_id, Cur_user.user_id)
            if not title:
                title = "video"
            await update.message.reply_text(f"Video: 🎥 {title}\nadded to your custom playlist")
        else:
            logger.error("🔴 Type error: not a video / not a playlist")
            await update.message.reply_text("Type error: not a video / not a playlist")
    except Exception:
        logger.exception("🔴 Failed to ingest link")
        await update.message.reply_text("Internal error while saving link.")
            

@require_user
async def send_videos(update, context):
    Cur_user = context.user_data["user"]

    playlist_id = None

    if context.args:
        try:
            pos = int(context.args[0])
        except ValueError:
            await update.message.reply_text("Playlist number must be an integer")
            return
        playlist_id = resolve_playlist_arg(Cur_user.user_id, pos)

    if not playlist_id:
        playlist_id = Cur_user.get_random_playlist()

    if not playlist_id:
        await update.message.reply_text("No playlists with -- await -- status")
        return
    
    Pl = Playlist(playlist_id, Cur_user.user_id)

    video = Pl.find_next_video()    #{"id": vid_id, "link": link}
    if not video:
        await update.message.reply_text("Try again. No videos with -- await -- status in current playlist")
        return
    
    await update.message.reply_text(video["link"])
    
    if mark_video_done(video['id'], playlist_id, Cur_user.user_id):
        logger.info(f"Video {video['link']} has been marked as done")
    if Pl.set_last_sent():
        logger.info('Playlist info -- last sent -- changed to NOW')

    if Pl.set_playlist_done():
        await update.message.reply_text("Playlist has been marked as done!")
        logger.info(f"Playlist has been marked as done")


@require_user
async def show_playlists(update, context):
    Cur_user = context.user_data["user"]
    try:
        text = Cur_user.render_playlists()
    except Exception:
        logger.exception("🔴 DB error in render_playlists")
        await update.message.reply_text("🔴 Failed to fetch playlists.")
        return
    
    await update.message.reply_text(text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)


async def delete_playlist_cmd(update, context):
    try:
        Cur_user = User.validate_or_reload(context, update)
    except Exception:
        logger.exception("🔴 Failed to restore/init user in ingest_link")
        await update.message.reply_text("🔴 Internal error. Please try again.")
        return
    
    if not context.args:
        await update.message.reply_text("Usage: /delete_playlist <playlist_id>")
        return
    
    try:
        playlist_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Playlist id must be an integer.")
        return
    
    Pl = Playlist(playlist_id, Cur_user.user_id)
    deleted = Pl.delete_playlist()
    if deleted:
        logger.info(f"Playlist {deleted['id']} '{deleted['title']}' deleted")
        await update.message.reply_text(
            f"Deleted:\n{deleted['id']} {deleted['title']}\n🔗 {deleted['youtube_link']}")
    else:
        logger.error('🔴 Failed to delete playlist')


async def restart_playlist(update, context):
    try:
        Cur_user = User.validate_or_reload(context, update)
    except Exception:
        logger.exception("🔴 Failed to restore/init user in ingest_link")
        await update.message.reply_text("🔴 Internal error. Please try again.")
        return
    
    if not context.args:
        await update.message.reply_text("Usage: /restart_playlist <playlist_id>")
        return
    
    try:
        playlist_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Playlist id must be a positive integer.")
        return
    
    Pl = Playlist(playlist_id, Cur_user.user_id)

    try:
        result = Pl.restart()
    except Exception:
        logger.exception("🔴 DB error in restart_pldb")
        await update.message.reply_text("🔴 Internal error while restarting playlist.")
        return
    
    if result:
        await update.message.reply_text(result["msg"])
    else:
        await update.message.reply_text("🔴 Unexpected error. Please try again.")


@require_user
async def statistic(update, context):
    Cur_user = context.user_data["user"]
    
    user_stat = Cur_user.get_user_stat()
    await update.message.reply_text(user_stat)
    logger.info("User stat delivered")


async def help_cmd(update, context):
    help_text = (
        "Here are the available commands:\n\n"
        "/start - Start the bot\n"
        "/show_playlists - Show your playlists\n"
        "/next [playlist position] - Get the next video (random if no number)\n"
        "/delete_playlist <playlist_number> - Delete a playlist by number\n"
        "/restart <playlist_number> - Restart a playlist by its position\n"
        "/stat - Show your statistics\n"
    )
    await update.message.reply_text(help_text)


COMMANDS = [
    BotCommand("start", "Start the bot"),
    BotCommand("show_playlists", "Show your playlists"),
    BotCommand("next", "Get the next video (random or by position in /show_playlists)"),
    BotCommand("delete_playlist", "Delete a playlist by its position"),
    BotCommand("restart", "Restart a playlist by its position"),
    BotCommand("stat", "Show your statistics"),
    BotCommand("help", "Show available commands"),
]


if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("next", send_videos))
    app.add_handler(CommandHandler("show_playlists", show_playlists))
    app.add_handler(CommandHandler("delete_playlist", delete_playlist_cmd))
    app.add_handler(CommandHandler("stat", statistic))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, ingest_link))

    app.run_polling()