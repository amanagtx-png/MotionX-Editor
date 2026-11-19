import os
import asyncio
import tempfile
import shutil
import time

from motor.motor_asyncio import AsyncIOMotorClient
from pyrogram import Client, filters, StopPropagation
from pyrogram.errors import FloodWait
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

API_ID = int(os.environ["API_ID"])
API_HASH = os.environ["API_HASH"]
BOT_TOKEN = os.environ["BOT_TOKEN"]
MONGO_URI = os.environ["MONGO_URI"]
ADMIN_ID = int(os.environ.get("ADMIN_ID", "6658706300"))

db = AsyncIOMotorClient(MONGO_URI)["videoeditor"]
users = db["users"]

FONT = os.environ.get(
    "FONT_PATH", "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Regular.ttf"
)
if not os.path.exists(FONT):
    FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

app = Client("editor_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# Per-user state: {"dir": temp folder, "video": path, "action": chosen edit}
STATE = {}

MENU = InlineKeyboardMarkup(
    [
        [
            InlineKeyboardButton("✂️ Trim", callback_data="trim"),
            InlineKeyboardButton("⏩ Speed", callback_data="speed"),
        ],
        [
            InlineKeyboardButton("📝 Text", callback_data="text"),
            InlineKeyboardButton("🎵 Music", callback_data="music"),
        ],
        [
            InlineKeyboardButton("🔇 Mute", callback_data="mute"),
            InlineKeyboardButton("🎧 Extract audio", callback_data="audio"),
        ],
        [InlineKeyboardButton("🗜 Compress", callback_data="compress")],
    ]
)

PROMPTS = {
    "trim": "Send the start and end time.\nExample: 00:00:05 00:00:20",
    "speed": "Send the speed. Example: 2 (double speed) or 0.5 (half speed). Range: 0.25 to 4",
    "text": "Send the text you want to put on the video.",
    "music": "Now send the audio/music file you want to add to the video.",
}


async def ffmpeg(*args):
    proc = await asyncio.create_subprocess_exec(
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *args,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    _, err = await proc.communicate()
    return proc.returncode == 0, err.decode()[-500:]


def atempo_chain(s):
    parts = []
    while s > 2.0:
        parts.append("atempo=2.0")
        s /= 2.0
    while s < 0.5:
        parts.append("atempo=0.5")
        s /= 0.5
    parts.append(f"atempo={s:.4f}")
    return ",".join(parts)


async def run_edit(client, chat_id, uid, action, param=None, audio_path=None):
    st = STATE.get(uid)
    if not st:
        await client.send_message(chat_id, "Please send a video first.")
        return
    src = st["video"]
    out = os.path.join(st["dir"], "out.mp4")
    wait = await client.send_message(chat_id, "⏳ Processing...")
    enc = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-c:a", "aac"]

    try:
        if action == "trim":
            start, end = param.split()
            args = ["-i", src, "-ss", start, "-to", end, *enc, out]
        elif action == "speed":
            s = float(param)
            if not 0.25 <= s <= 4:
                raise ValueError("Speed must be between 0.25 and 4")
            args = ["-i", src, "-filter_complex",
                    f"[0:v]setpts=PTS/{s}[v];[0:a]{atempo_chain(s)}[a]",
                    "-map", "[v]", "-map", "[a]", *enc, out]
        elif action == "text":
            txt = os.path.join(st["dir"], "t.txt")
            with open(txt, "w", encoding="utf-8") as f:
                f.write(param)
            vf = (f"drawtext=fontfile={FONT}:textfile={txt}:fontcolor=white:"
                  "fontsize=h/15:borderw=3:bordercolor=black:"
                  "x=(w-text_w)/2:y=h-text_h-60")
            args = ["-i", src, "-vf", vf, "-c:v", "libx264", "-preset", "veryfast",
                    "-crf", "23", "-c:a", "copy", out]
        elif action == "music":
            args = ["-i", src, "-i", audio_path, "-map", "0:v", "-map", "1:a",
                    "-shortest", "-c:v", "copy", "-c:a", "aac", out]
        elif action == "mute":
            args = ["-i", src, "-an", "-c:v", "copy", out]
        elif action == "compress":
            args = ["-i", src, "-c:v", "libx264", "-preset", "veryfast",
                    "-crf", "28", "-c:a", "aac", "-b:a", "96k", out]
        elif action == "audio":
            out = os.path.join(st["dir"], "out.mp3")
            args = ["-i", src, "-vn", "-c:a", "libmp3lame", "-q:a", "2", out]
        else:
            return

        ok, err = await ffmpeg(*args)
        if not ok:
            await wait.edit_text(f"❌ Error:\n{err}")
            return

        await wait.edit_text("📤 Uploading...")
        if action == "audio":
            await client.send_audio(chat_id, out)
        else:
            await client.send_video(chat_id, out, caption="✅ Done! You can edit further:",
                                    reply_markup=MENU)
            os.replace(out, src)  # next edit will apply on this new video
        await wait.delete()
        await users.update_one({"_id": uid}, {"$inc": {"edits": 1}})
    except ValueError as e:
        await wait.edit_text(f"❌ Invalid input: {e}")
    except Exception as e:
        await wait.edit_text(f"❌ Something went wrong: {e}")
    finally:
        st["action"] = None


@app.on_message(filters.command(["start", "help"]) & filters.private)
async def start(_, m):
    await m.reply("Hello! 🎬 Send me a video, then pick an edit using the buttons.\nUse /done to clean up.")


@app.on_message(filters.command("done") & filters.private)
async def done(_, m):
    st = STATE.pop(m.from_user.id, None)
    if st:
        shutil.rmtree(st["dir"], ignore_errors=True)
    await m.reply("🧹 Files deleted. You can send a new video now.")


@app.on_message(filters.private & (filters.video | filters.document))
async def got_video(client, m):
    if m.document and not (m.document.mime_type or "").startswith("video"):
        return
    uid = m.from_user.id
    old = STATE.pop(uid, None)
    if old:
        shutil.rmtree(old["dir"], ignore_errors=True)
    d = tempfile.mkdtemp(prefix=f"u{uid}_")
    msg = await m.reply("⬇️ Downloading...")
    path = await m.download(file_name=os.path.join(d, "in.mp4"))
    STATE[uid] = {"dir": d, "video": path, "action": None}
    await msg.edit_text("What do you want to edit?", reply_markup=MENU)


@app.on_callback_query()
async def on_button(client, q):
    uid = q.from_user.id
    st = STATE.get(uid)
    if not st:
        await q.answer("Please send a video first", show_alert=True)
        return
    await q.answer()
    action = q.data
    if action in ("mute", "audio", "compress"):
        await run_edit(client, q.message.chat.id, uid, action)
    else:
        st["action"] = action
        await q.message.reply(PROMPTS[action])


@app.on_message(filters.private & filters.text & ~filters.command(["start", "help", "done", "stats", "broadcast", "ban", "unban"]))
async def on_text(client, m):
    uid = m.from_user.id
    st = STATE.get(uid)
    if not st or st.get("action") not in ("trim", "speed", "text"):
        await m.reply("Please send a video first and pick a button.")
        return
    await run_edit(client, m.chat.id, uid, st["action"], param=m.text.strip())


@app.on_message(filters.private & (filters.audio | filters.voice))
async def on_audio(client, m):
    uid = m.from_user.id
    st = STATE.get(uid)
    if not st or st.get("action") != "music":
        await m.reply("Please send a video first and press the 🎵 Music button.")
        return
    apath = await m.download(file_name=os.path.join(st["dir"], "music.bin"))
    await run_edit(client, m.chat.id, uid, "music", audio_path=apath)


# ---------- Database, ban and admin ----------
async def track(user):
    now = int(time.time())
    await users.update_one(
        {"_id": user.id},
        {"$set": {"name": user.first_name, "username": user.username, "last_seen": now},
         "$setOnInsert": {"joined": now, "banned": False, "edits": 0}},
        upsert=True,
    )


async def is_banned(uid):
    doc = await users.find_one({"_id": uid}, {"banned": 1})
    return bool(doc and doc.get("banned"))


@app.on_message(filters.private, group=-1)
async def gate_msg(_, m):
    if not m.from_user:
        return
    await track(m.from_user)
    if m.from_user.id != ADMIN_ID and await is_banned(m.from_user.id):
        await m.reply("🚫 You are banned from this bot.")
        raise StopPropagation


@app.on_callback_query(group=-1)
async def gate_cb(_, q):
    if q.from_user.id != ADMIN_ID and await is_banned(q.from_user.id):
        await q.answer("🚫 You are banned.", show_alert=True)
        raise StopPropagation


admin = filters.private & filters.user(ADMIN_ID)


@app.on_message(filters.command("stats") & admin)
async def stats(_, m):
    total = await users.count_documents({})
    banned = await users.count_documents({"banned": True})
    day = await users.count_documents({"last_seen": {"$gt": int(time.time()) - 86400}})
    agg = await users.aggregate([{"$group": {"_id": None, "e": {"$sum": "$edits"}}}]).to_list(1)
    edits = agg[0]["e"] if agg else 0
    await m.reply(f"📊 Total users: {total}\n🟢 Last 24 hours: {day}\n🚫 Banned: {banned}\n🎬 Total edits: {edits}")


@app.on_message(filters.command("ban") & admin)
async def ban(_, m):
    if len(m.command) < 2 or not m.command[1].isdigit():
        return await m.reply("Usage: /ban USER_ID")
    await users.update_one({"_id": int(m.command[1])}, {"$set": {"banned": True}}, upsert=True)
    await m.reply("🚫 User banned.")


@app.on_message(filters.command("unban") & admin)
async def unban(_, m):
    if len(m.command) < 2 or not m.command[1].isdigit():
        return await m.reply("Usage: /unban USER_ID")
    await users.update_one({"_id": int(m.command[1])}, {"$set": {"banned": False}})
    await m.reply("✅ User unbanned.")


@app.on_message(filters.command("broadcast") & admin)
async def broadcast(client, m):
    src = m.reply_to_message
    text = m.text.split(None, 1)[1] if len(m.command) > 1 else None
    if not src and not text:
        return await m.reply("Usage: /broadcast message, or reply to a message with /broadcast")
    ok = fail = 0
    status = await m.reply("📣 Sending...")
    async for u in users.find({"banned": {"$ne": True}}, {"_id": 1}):
        try:
            if src:
                await src.copy(u["_id"])
            else:
                await client.send_message(u["_id"], text)
            ok += 1
        except FloodWait as e:
            await asyncio.sleep(e.value)
        except Exception:
            fail += 1
        await asyncio.sleep(0.05)
    await status.edit_text(f"✅ Sent: {ok}\n❌ Failed: {fail}")


if __name__ == "__main__":
    app.run()
