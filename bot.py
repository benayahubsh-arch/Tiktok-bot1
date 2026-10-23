import asyncio
import logging
import os
import re
import tempfile
import uuid
from pathlib import Path
from urllib.parse import urlparse

import yt_dlp
from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters

load_dotenv()
TOKEN = os.getenv("BOT_TOKEN", "").strip()
MAX_UPLOAD_BYTES = 49 * 1024 * 1024
ALLOWED_HOSTS = {"tiktok.com", "www.tiktok.com", "m.tiktok.com", "vm.tiktok.com", "vt.tiktok.com"}
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)


def valid_tiktok_url(value: str) -> bool:
    try:
        parsed = urlparse(value.strip())
        host = (parsed.hostname or "").lower()
        return parsed.scheme in {"http", "https"} and host in ALLOWED_HOSTS and parsed.path != "/"
    except ValueError:
        return False


def download_media(url: str, audio_only: bool = False) -> tuple[Path, str]:
    folder = Path(tempfile.mkdtemp(prefix="tiktok_bot_"))
    opts = {
        "outtmpl": str(folder / "%(id)s.%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "retries": 2,
        "socket_timeout": 25,
        "max_filesize": MAX_UPLOAD_BYTES,
    }
    if audio_only:
        opts.update({"format": "bestaudio/best", "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}]})
    else:
        opts.update({"format": "best[ext=mp4]/best", "merge_output_format": "mp4"})
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        title = str(info.get("title") or "TikTok")[:100]
    files = [p for p in folder.iterdir() if p.is_file()]
    if not files:
        raise RuntimeError("לא נמצא קובץ להעלאה")
    result = max(files, key=lambda p: p.stat().st_size)
    if result.stat().st_size > MAX_UPLOAD_BYTES:
        raise RuntimeError("הקובץ גדול מדי לשליחה דרך הבוט. נסה סרטון קצר יותר.")
    return result, title


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "שלחו לי קישור ציבורי של TikTok ואחזיר את הסרטון.\n"
        "אחרי הסרטון יופיע כפתור 🎵 MUSIC להורדת האודיו."
    )


async def handle_link(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.message.text or ""
    match = re.search(r"https?://\S+", text)
    url = match.group(0).rstrip(".,!?)\"]}") if match else ""
    if not valid_tiktok_url(url):
        await update.message.reply_text("שלחו קישור TikTok תקין, למשל https://www.tiktok.com/@user/video/123")
        return
    status = await update.message.reply_text("⏳ מוריד את הסרטון…")
    try:
        path, title = await asyncio.to_thread(download_media, url, False)
        media_key = uuid.uuid4().hex[:12]
        context.bot_data.setdefault("links", {})[media_key] = url
        with path.open("rb") as video:
            await update.message.reply_video(
                video=video,
                caption=title,
                supports_streaming=True,
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🎵 MUSIC", callback_data=f"music:{media_key}")]]),
            )
        await status.delete()
    except Exception as exc:
        logging.warning("TikTok download failed (%s)", type(exc).__name__)
        await status.edit_text("לא הצלחתי להוריד את הסרטון. בדקו שהקישור ציבורי ונסו שוב בעוד כמה דקות.")


async def music_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer("מכין את האודיו…")
    media_key = query.data.removeprefix("music:")
    url = context.bot_data.get("links", {}).get(media_key, "")
    if not valid_tiktok_url(url):
        await query.message.reply_text("הקישור אינו תקין. שלחו את הקישור שוב.")
        return
    status = await query.message.reply_text("⏳ מוריד אודיו…")
    try:
        path, title = await asyncio.to_thread(download_media, url, True)
        with path.open("rb") as audio:
            await query.message.reply_audio(audio=audio, title=title[:64], filename=f"{path.stem}.mp3")
        await status.delete()
    except Exception as exc:
        logging.warning("TikTok audio failed (%s)", type(exc).__name__)
        await status.edit_text("לא הצלחתי להפיק אודיו מהקישור הזה. נסו שוב מאוחר יותר.")


def main() -> None:
    if not TOKEN:
        raise SystemExit("חסר BOT_TOKEN. העתיקו את הטוקן לקובץ .env")
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(music_button, pattern=r"^music:"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_link))
    logging.info("TikTok bot is running")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
