from telegram import BotCommand
from telegram.constants import ParseMode
from telegram.ext import ApplicationBuilder,  ApplicationHandlerStop, CommandHandler, MessageHandler, filters
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


@require_user
async def cancel_any(update, context):
    msg = None
    if context.user_data.pop(AWAITING_DELETE_KEY, None):
        msg = "Deletion cancelled."
    if context.user_data.pop(AWAITING_RESTART_KEY, None):
        msg = "Restart cancelled."
    await update.message.reply_text(msg or "Nothing to cancel.")
    raise ApplicationHandlerStop  

AWAITING_DELETE_KEY = "awaiting_delete"


@require_user
async def starting_deletion(update, context):
    Cur_user = context.user_data["user"]

    try:
        text = Cur_user.render_playlists()
    except Exception:
        logger.exception("🔴 DB error in render_playlists")
        await update.message.reply_text("🔴 Failed to fetch playlists.")
        return
    
    context.user_data[AWAITING_DELETE_KEY] = True
    intruction_msg = "🗑️ To delete playlist send the number\n✋🏻 To cancel command send /cancel\n"

    await update.message.reply_text(intruction_msg + text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)


@require_user
async def get_deletion_info(update, context):

    if not context.user_data.get(AWAITING_DELETE_KEY):
        return

    Cur_user = context.user_data["user"]
    user_answer = (update.message.text or "").strip()

    if user_answer.lower() == "/cancel":
        context.user_data.pop(AWAITING_DELETE_KEY, None)
        await update.message.reply_text("Deletion cancelled.")
        raise ApplicationHandlerStop
    
    try:
        playlist_position = int(user_answer)
    except ValueError:
        await update.message.reply_text("Please send a NUMBER of the playlist or /cancel.")
        return

    await delete_playlist_cmd(update, context, playlist_position)
    context.user_data.pop(AWAITING_DELETE_KEY, None)
    raise ApplicationHandlerStop


@require_user
async def delete_playlist_cmd(update, context, playlist_position = None):
    Cur_user = context.user_data["user"]
    
    try:
        playlist_id = resolve_playlist_arg(Cur_user.user_id, playlist_position)
    except Exception:
        logger.exception("🔴 resolve_playlist_arg failed")
        await update.message.reply_text("🔴 Internal error. Try again later.")
        return

    if not playlist_id:
        await update.message.reply_text("No playlist found by that number.")
        return

    try:
        Pl = Playlist(playlist_id, Cur_user.user_id)
        deleted = Pl.delete_playlist()
    except Exception:
        logger.exception("🔴 Failed to delete playlist")
        await update.message.reply_text("🔴 Failed to delete the playlist.")
        return

    if deleted:
        logger.info(f"Playlist {deleted['id']} '{deleted['title']}' deleted")
        await update.message.reply_text(
            f'Deleted:\n{deleted["id"]} {html.escape(deleted["title"])}\n'
            f'🔗 <a href="{html.escape(deleted["youtube_link"], quote=True)}">link</a>',
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True
            )
    else:
        await update.message.reply_text("Nothing to delete (already removed?).")

AWAITING_RESTART_KEY = "awaiting_restart"


@require_user
async def starting_restart(update, context):
    Cur_user = context.user_data["user"]

    context.user_data.pop(AWAITING_DELETE_KEY, None)
    context.user_data[AWAITING_RESTART_KEY] = True

    try:
        text = Cur_user.render_playlists()
    except Exception:
        logger.exception("🔴 DB error in render_playlists")
        await update.message.reply_text("🔴 Failed to fetch playlists.")
        return
    
    intruction_msg = "🔄 To restart playlist send the number\n✋🏻 To cancel command send /cancel\n"
    await update.message.reply_text(intruction_msg + text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)


@require_user
async def get_restarting_info(update, context):

    if not context.user_data.get(AWAITING_RESTART_KEY):
        return

    Cur_user = context.user_data["user"]
    user_answer = (update.message.text or "").strip()
    logger.info("restart_flow answer: %r", user_answer)

    if user_answer.lower() == "/cancel":
        context.user_data.pop(AWAITING_RESTART_KEY, None)
        await update.message.reply_text("Restart cancelled.")
        raise ApplicationHandlerStop
    
    try:
        playlist_position = int(user_answer)
    except ValueError:
        await update.message.reply_text("Please send a NUMBER of the playlist or /cancel.")
        return
    
    await restart_playlist(update, context, playlist_position)
    context.user_data.pop(AWAITING_RESTART_KEY, None)
    raise ApplicationHandlerStop


@require_user
async def restart_playlist(update, context, playlist_position = None):
    Cur_user = context.user_data["user"]
    logger.info("restart_playlist CALLED, pos=%r", playlist_position)

    try:
        playlist_id = resolve_playlist_arg(Cur_user.user_id, playlist_position)
        logger.info("resolved position %s -> playlist_id %r", playlist_position, playlist_id)
    except Exception:
        logger.exception("🔴 resolve_playlist_arg failed")
        await update.message.reply_text("🔴 Internal error. Try again later.")
        return

    if not playlist_id:
        await update.message.reply_text("No playlist found by that number.")
        return
    
    try:
        Pl = Playlist(playlist_id, Cur_user.user_id)
        restarted = Pl.restart()
    except Exception:
        logger.exception("🔴 DB error in restart_playlist")
        await update.message.reply_text("🔴 Internal error while restarting playlist.")
        return

    if restarted:
        await update.message.reply_text(restarted["msg"])
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

async def _post_init(app):
    await app.bot.set_my_commands(COMMANDS)


awaiting_restart_filter = (
    filters.TEXT
    & ~filters.COMMAND
    & filters.Create(lambda update, context: bool(context.user_data.get(AWAITING_RESTART_KEY)))
)

awaiting_delete_filter = (
    filters.TEXT
    & ~filters.COMMAND
    & filters.Create(lambda update, context: bool(context.user_data.get(AWAITING_DELETE_KEY)))
)

if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).post_init(_post_init).build()

    app.add_handler(MessageHandler(filters.Regex(YOUTUBE_URL_RE), ingest_link), group=0)

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("next", send_videos))
    app.add_handler(CommandHandler("show_playlists", show_playlists))
    app.add_handler(CommandHandler("cancel", cancel_any))
    app.add_handler(CommandHandler("delete_playlist", starting_deletion))
    app.add_handler(CommandHandler("restart", starting_restart))
    app.add_handler(CommandHandler("stat", statistic))
    app.add_handler(CommandHandler("help", help_cmd))

    app.add_handler(MessageHandler(awaiting_restart_filter, get_restarting_info), group=1)
    app.add_handler(MessageHandler(awaiting_delete_filter,  get_deletion_info),   group=1)
    
    app.run_polling()