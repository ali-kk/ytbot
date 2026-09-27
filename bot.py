"""Telegram bot: send a song name (pick from YouTube results) or a YouTube link, get the song back.

Songs are sent as M4A: YouTube's own AAC audio, untouched. No re-encoding means original quality
and ~2x faster than converting to MP3. Telegram plays M4A in its music player like MP3.
"""
import asyncio
import html
import logging
import os
import re
import shelve
import tempfile
from pathlib import Path

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ChatAction
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)
from yt_dlp import YoutubeDL
from yt_dlp.utils import match_filter_func

RESULTS = 6
MAX_DURATION = 20 * 60  # Telegram bots cannot upload past 50 MB
MAX_BYTES = 49 * 1024 * 1024
PROXY = os.environ.get("YT_PROXY")  # e.g. socks5://127.0.0.1:40000 (Cloudflare WARP)
LINK = re.compile(r"(?:youtube\.com/(?:watch\?\S*?v=|shorts/|live/|embed/)|youtu\.be/)([\w-]{11})")
# video id -> Telegram file_id: a song sent once is re-sent instantly, no download or upload.
SENT = {}  # main() swaps in the on-disk cache (it is locked while open, so not at import)

logging.basicConfig(level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)  # its INFO lines contain the bot token
log = logging.getLogger("ytbot")


def extract(opts, url, download):
    """Via proxy (YouTube bot-checks server IPs), retried once as YouTube 403s now and then; direct IP last."""
    routes = [PROXY, PROXY, None] if PROXY else [None, None]
    for attempt, proxy in enumerate(routes, 1):
        try:
            with YoutubeDL({**opts, "proxy": proxy} if proxy else opts) as ydl:
                return ydl.extract_info(url, download=download)
        except Exception as e:
            if attempt == len(routes):
                raise
            log.warning("attempt %d/%d failed: %s", attempt, len(routes), e)


def human(n):
    if not n:
        return "?"
    for unit in ("", "K", "M", "B"):
        if n < 1000:
            return f"{n:.0f}{unit}" if unit == "" else f"{n:.1f}{unit}".replace(".0", "")
        n /= 1000
    return f"{n:.1f}T"


def clock(seconds):
    if not seconds:
        return "?"
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def search(query):
    opts = {"quiet": True, "no_warnings": True, "extract_flat": True, "default_search": "ytsearch"}
    info = extract(opts, f"ytsearch{RESULTS}:{query}", download=False)
    return [e for e in (info.get("entries") or []) if e.get("id")]


def fetch_audio(video_id, folder):
    """Download the song as m4a into folder. Returns (path, or None if skipped, info)."""
    opts = {
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "format": "bestaudio[ext=m4a]/bestaudio/best",
        "outtmpl": f"{folder}/%(id)s.%(ext)s",
        # Skip before downloading: live streams never end, long videos exceed 50 MB.
        "match_filter": match_filter_func(f"!is_live & duration <=? {MAX_DURATION}"),
        "postprocessors": [
            # Already m4a (nearly always): left untouched. Otherwise converted to m4a.
            {"key": "FFmpegExtractAudio", "preferredcodec": "m4a"},
            {"key": "FFmpegMetadata"},
            {"key": "EmbedThumbnail"},
        ],
        "writethumbnail": True,
    }
    info = extract(opts, f"https://www.youtube.com/watch?v={video_id}", download=True)
    return next(Path(folder).glob("*.m4a"), None), info


async def send_audio(msg, video_id):
    await msg.chat.send_action(ChatAction.UPLOAD_VOICE)
    if video_id in SENT:
        try:
            return await msg.reply_audio(SENT[video_id])
        except Exception:
            log.warning("cached file_id rejected, downloading %s again", video_id)

    with tempfile.TemporaryDirectory() as folder:
        try:
            path, info = await asyncio.to_thread(fetch_audio, video_id, folder)
        except Exception:
            log.exception("download failed")
            return await msg.reply_text("فشل التحميل.")
        if not path or path.stat().st_size > MAX_BYTES:
            return await msg.reply_text("الملف كبير جداً أو بث مباشر (الحد 20 دقيقة).")

        with path.open("rb") as fh:
            sent = await msg.reply_audio(
                audio=fh,
                title=info.get("track") or info.get("title"),
                performer=info.get("artist") or info.get("uploader"),
                duration=int(info.get("duration") or 0),
                filename=f"{info.get('title', 'audio')[:60]}.m4a",
            )
    SENT[video_id] = sent.audio.file_id


async def start(update, _):
    await update.message.reply_text(
        "ابعتلي اسم الأغنية أو رابط يوتيوب وأرجعلك الأغنية 🎵\n\nSend me a song name or a YouTube link."
    )


async def on_query(update, _):
    query = update.message.text.strip()
    if not query:
        return
    if link := LINK.search(query):
        return await send_audio(update.message, link[1])

    await update.message.chat.send_action(ChatAction.TYPING)
    try:
        entries = await asyncio.to_thread(search, query)
    except Exception:
        log.exception("search failed")
        return await update.message.reply_text("ما كدرت أبحث، جرب مرة ثانية.")
    if not entries:
        return await update.message.reply_text("ماكو نتائج.")

    lines, buttons = [], []
    for i, e in enumerate(entries, 1):
        title = html.escape(e.get("title") or "?")
        channel = html.escape(e.get("uploader") or e.get("channel") or "?")
        lines.append(
            f"<b>{i}.</b> {title}\n"
            f"    👤 {channel}"
            f"  ·  👁 {human(e.get('view_count'))}"
            f"  ·  ⏱ {clock(e.get('duration'))}"
        )
        buttons.append(InlineKeyboardButton(str(i), callback_data=e["id"]))

    await update.message.reply_text(
        "\n\n".join(lines),
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([buttons[:3], buttons[3:]]),
        disable_web_page_preview=True,
    )


async def on_pick(update, _):
    q = update.callback_query
    await q.answer("جاري التحميل…")
    await send_audio(q.message, q.data)


def main():
    global SENT
    SENT = shelve.open(str(Path(__file__).with_name("sent_cache")))
    # concurrent_updates: serve users in parallel (default is one update at a time).
    app = Application.builder().token(os.environ["BOT_TOKEN"]).concurrent_updates(True).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(on_pick))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_query))
    app.run_polling()


if __name__ == "__main__":
    main()
