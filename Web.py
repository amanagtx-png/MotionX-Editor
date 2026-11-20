import os
import hmac
import json
import time
import uuid
import shutil
import hashlib
import asyncio
import tempfile
from urllib.parse import parse_qsl

from aiohttp import web

BASE = os.path.dirname(os.path.abspath(__file__))
WORK = tempfile.mkdtemp(prefix="web_")
MAX_UPLOAD = 500 * 1024 * 1024  # 500MB limit for web uploads
JOB_TTL = 3600  # delete web files after 1 hour
LIMIT = asyncio.Semaphore(2)  # max 2 ffmpeg jobs at the same time


def verify_init_data(init_data, bot_token):
    """Check that the data really comes from Telegram. Returns the user dict or None."""
    try:
        data = dict(parse_qsl(init_data, keep_blank_values=True))
        got_hash = data.pop("hash")
        check = "\n".join(f"{k}={v}" for k, v in sorted(data.items()))
        secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
        mine = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(mine, got_hash):
            return None
        if time.time() - int(data["auth_date"]) > 86400:
            return None
        return json.loads(data["user"])
    except Exception:
        return None


RATIOS = {"orig": None, "9:16": 9 / 16, "1:1": 1, "16:9": 16 / 9, "4:5": 4 / 5, "2:3": 2 / 3}
FILTERS = {
    "none": None,
    "vivid": "eq=saturation=1.5:contrast=1.1",
    "warm": "colorbalance=rs=.12:gs=.02:bs=-.12",
    "cool": "colorbalance=rs=-.1:bs=.15",
    "bw": "hue=s=0",
    "sepia": "colorchannelmixer=.393:.769:.189:0:.349:.686:.168:0:.272:.534:.131",
    "anime": "eq=saturation=1.35:contrast=1.15:brightness=0.03",
}


async def probe(path):
    """Returns (width, height, has_audio, duration) of a media file."""
    p = await asyncio.create_subprocess_exec(
        "ffprobe", "-v", "error", "-show_entries", "stream=codec_type,width,height:format=duration",
        "-of", "json", path, stdout=asyncio.subprocess.PIPE)
    out, _ = await p.communicate()
    d = json.loads(out)
    v = next(x for x in d["streams"] if x["codec_type"] == "video")
    return v["width"], v["height"], any(x["codec_type"] == "audio" for x in d["streams"]), float(d["format"]["duration"])


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


async def start_web(bot, bot_token, users, ffmpeg, font):
    """Starts the web server. Uses the same bot, database and ffmpeg helper as bot.py."""

    async def auth(request):
        init = request.headers.get("X-Init-Data") or request.query.get("auth", "")
        user = verify_init_data(init, bot_token)
        if not user:
            raise web.HTTPUnauthorized(text="Open this page from the Telegram bot.")
        doc = await users.find_one({"_id": user["id"]}, {"banned": 1})
        if doc and doc.get("banned"):
            raise web.HTTPForbidden(text="You are banned.")
        return user

    def job_path(uid, job):
        if not job.isalnum():
            raise web.HTTPBadRequest(text="Bad id")
        return os.path.join(WORK, str(uid), job, "in.mp4")

    async def index(request):
        return web.FileResponse(os.path.join(BASE, "static", "index.html"))

    async def upload(request):
        user = await auth(request)
        uid = user["id"]
        shutil.rmtree(os.path.join(WORK, str(uid)), ignore_errors=True)  # one project per user
        job = uuid.uuid4().hex[:12]
        path = job_path(uid, job)
        os.makedirs(os.path.dirname(path))
        reader = await request.multipart()
        field = await reader.next()
        if field is None or field.name != "video":
            raise web.HTTPBadRequest(text="No video received.")
        size = 0
        with open(path, "wb") as f:
            while True:
                chunk = await field.read_chunk(1 << 20)
                if not chunk:
                    break
                size += len(chunk)
                if size > MAX_UPLOAD:
                    f.close()
                    shutil.rmtree(os.path.dirname(path), ignore_errors=True)
                    raise web.HTTPRequestEntityTooLarge(MAX_UPLOAD, size)
                f.write(chunk)
        return web.json_response({"id": job})

    async def media(request):
        user = await auth(request)
        path = job_path(user["id"], request.match_info["job"])
        if not os.path.exists(path):
            raise web.HTTPNotFound(text="File not found.")
        return web.FileResponse(path)  # supports seeking in the video player

    async def save_file(request, field_name, path, limit):
        reader = await request.multipart()
        field = await reader.next()
        if field is None or field.name != field_name:
            raise web.HTTPBadRequest(text="No file received.")
        size = 0
        with open(path, "wb") as f:
            while True:
                chunk = await field.read_chunk(1 << 20)
                if not chunk:
                    break
                size += len(chunk)
                if size > limit:
                    raise web.HTTPRequestEntityTooLarge(limit, size)
                f.write(chunk)

    async def music(request):
        user = await auth(request)
        path = job_path(user["id"], request.match_info["job"])
        if not os.path.exists(path):
            raise web.HTTPNotFound(text="Upload a video first.")
        await save_file(request, "audio", os.path.join(os.path.dirname(path), "music.bin"), 50 * 1024 * 1024)
        return web.json_response({"ok": True})

    async def thumbs(request):
        user = await auth(request)
        path = job_path(user["id"], request.match_info["job"])
        if not os.path.exists(path):
            raise web.HTTPNotFound(text="File not found.")
        img = os.path.join(os.path.dirname(path), "thumbs.jpg")
        n = 12
        _, _, _, dur = await probe(path)
        async with LIMIT:
            ok, err = await ffmpeg("-i", path, "-vf", f"fps={n}/{max(dur, 0.1):.3f},scale=-2:64,tile={n}x1",
                                   "-frames:v", "1", "-q:v", "5", img)
        if not ok:
            raise web.HTTPInternalServerError(text=err)
        return web.FileResponse(img, headers={"Cache-Control": "no-store"})

    async def undo(request):
        user = await auth(request)
        body = await request.json()
        src = job_path(user["id"], str(body.get("id", "")))
        prev = os.path.join(os.path.dirname(src), "prev.mp4")
        if not os.path.exists(prev):
            raise web.HTTPBadRequest(text="Nothing to undo.")
        os.replace(prev, src)
        return web.json_response({"ok": True})

    async def edit(request):
        user = await auth(request)
        uid = user["id"]
        b = await request.json()
        src = job_path(uid, str(b.get("id", "")))
        if not os.path.exists(src):
            raise web.HTTPNotFound(text="Upload a video first.")
        folder = os.path.dirname(src)
        out = os.path.join(folder, "out.mp4")
        mfile = os.path.join(folder, "music.bin")

        def num(k, lo, hi, d):
            try:
                return min(hi, max(lo, float(b.get(k, d))))
            except (TypeError, ValueError):
                raise web.HTTPBadRequest(text=f"Bad value: {k}")

        def pick(k, allowed, d):
            v = b.get(k, d)
            if v not in allowed:
                raise web.HTTPBadRequest(text=f"Bad value: {k}")
            return v

        start, end, speed = num("start", 0, 1e6, 0), num("end", 0, 1e6, 0), num("speed", 0.25, 4, 1)
        zoom, blur = num("zoom", 1, 3, 1), int(num("blur", 0, 20, 0))
        vol, mvol = num("vol", 0, 2, 1), num("mvol", 0, 2, 1)
        fin, fout = num("fade_in", 0, 5, 0), num("fade_out", 0, 5, 0)
        ratio, fit = pick("ratio", RATIOS, "orig"), pick("fit", ("fit", "fill", "blur"), "blur")
        rot, res, fps = pick("rot", (0, 90, 180, 270), 0), pick("res", (0, 480, 720, 1080, 2160), 0), pick("fps", (0, 24, 30, 60), 0)
        flt = pick("filter", FILTERS, "none")
        text = str(b.get("text") or "").strip()[:200]
        mute, use_music = bool(b.get("mute")), bool(b.get("music"))
        if end and end <= start:
            raise web.HTTPBadRequest(text="End time must be after start time.")
        if use_music and not os.path.exists(mfile):
            raise web.HTTPBadRequest(text="Add a music file first.")

        sw, sh, has_a, dur = await probe(src)
        outdur = ((end or dur) - start) / speed

        # output size from ratio + resolution
        if rot in (90, 270):
            sw, sh = sh, sw
        ar = RATIOS[ratio] or sw / sh
        short = res or min(sw, sh)
        W, H = (round(short * ar), short) if ar >= 1 else (short, round(short / ar))
        W, H = W - W % 2, H - H % 2

        # video graph: prepare -> aspect -> finish
        pre = []
        if speed != 1:
            pre.append(f"setpts=PTS/{speed}")
        pre += {0: [], 90: ["transpose=1"], 180: ["hflip", "vflip"], 270: ["transpose=2"]}[rot]
        if b.get("mirror"):
            pre.append("hflip")
        if b.get("flip"):
            pre.append("vflip")
        if zoom > 1:
            pre.append(f"crop=iw/{zoom}:ih/{zoom}")
        if FILTERS[flt]:
            pre.append(FILTERS[flt])
        if blur:
            pre.append(f"boxblur={blur}:1")
        g = ["[0:v]" + ",".join(["null"] + pre) + "[p]"]
        cover = f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}"
        if ratio == "orig" or fit == "fill":
            g.append(f"[p]{cover}[q]")
        elif fit == "fit":
            g.append(f"[p]scale={W}:{H}:force_original_aspect_ratio=decrease,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:black[q]")
        else:
            g.append(f"[p]split[a][b];[a]{cover},boxblur=20:2[bg];"
                     f"[b]scale={W}:{H}:force_original_aspect_ratio=decrease[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2[q]")
        post = ["setsar=1", "format=yuv420p"]
        if text:
            txt = os.path.join(folder, "t.txt")
            with open(txt, "w", encoding="utf-8") as f:
                f.write(text)
            post.insert(0, f"drawtext=fontfile={font}:textfile={txt}:fontcolor=white:fontsize=h/15:"
                           "borderw=3:bordercolor=black:x=(w-text_w)/2:y=h-text_h-60")
        g.append("[q]" + ",".join(post) + "[v]")

        # audio graph: original audio + optional music, with fades
        labels = []
        if has_a and not mute:
            chain = ([atempo_chain(speed)] if speed != 1 else []) + [f"volume={vol}"]
            g.append(f"[0:a]{','.join(chain)}[a0]")
            labels.append("[a0]")
        if use_music:
            g.append(f"[1:a]volume={mvol}[a1]")
            labels.append("[a1]")
        if labels:
            fades = ([f"afade=t=in:d={fin}"] if fin else []) + \
                    ([f"afade=t=out:st={max(0, outdur - fout):.2f}:d={fout}"] if fout else [])
            head = labels[0] if len(labels) == 1 else "".join(labels) + "amix=inputs=2:duration=first:normalize=0,"
            g.append(f"{head}{','.join(fades) or 'anull'}[af]")

        args = (["-ss", str(start)] if start else []) + (["-to", str(end)] if end else []) + ["-i", src]
        if use_music:
            args += ["-stream_loop", "-1", "-i", mfile]
        args += ["-filter_complex", ";".join(g), "-map", "[v]"]
        args += ["-map", "[af]", "-c:a", "aac"] if labels else ["-an"]
        if fps:
            args += ["-r", str(fps)]
        if use_music:
            args += ["-t", f"{outdur:.2f}"]
        args += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-movflags", "+faststart", out]

        async with LIMIT:
            ok, err = await ffmpeg(*args)
        if not ok:
            raise web.HTTPInternalServerError(text=f"Editing failed: {err}")

        shutil.copy2(src, os.path.join(folder, "prev.mp4"))  # one-level undo
        os.replace(out, src)
        await users.update_one({"_id": uid}, {"$inc": {"edits": 1}})
        return web.json_response({"ok": True})

    async def send(request):
        user = await auth(request)
        body = await request.json()
        path = job_path(user["id"], str(body.get("id", "")))
        if not os.path.exists(path):
            raise web.HTTPNotFound(text="Upload a video first.")
        await bot.send_video(user["id"], path, caption="Edited with the web editor.")
        return web.json_response({"ok": True})

    async def cleaner():
        while True:
            await asyncio.sleep(600)
            now = time.time()
            for uid in os.listdir(WORK):
                p = os.path.join(WORK, uid)
                if now - os.path.getmtime(p) > JOB_TTL:
                    shutil.rmtree(p, ignore_errors=True)

    app = web.Application(client_max_size=MAX_UPLOAD + (1 << 20))
    app.add_routes([
        web.get("/", index),
        web.post("/api/upload", upload),
        web.get("/api/media/{job}", media),
        web.post("/api/edit", edit),
        web.post("/api/undo", undo),
        web.post("/api/music/{job}", music),
        web.get("/api/thumbs/{job}", thumbs),
        web.post("/api/send", send),
    ])
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", int(os.environ.get("PORT", "8080"))).start()
    asyncio.create_task(cleaner())
