# Video Editor Telegram Bot (V01.0)

Features: trim, speed, text, music, mute, extract audio, compress. Works with videos up to 2GB.

## Updates channel
Join our Telegram channel for updates and news: https://t.me/AniTimesNetwork

## Environment variables
| Name | Where to get it |
|---|---|
| `BOT_TOKEN` | @BotFather |
| `API_ID` | https://my.telegram.org -> API development tools |
| `API_HASH` | same page |
| `MONGO_URI` | MongoDB Atlas -> Connect -> Drivers (free cluster is enough) |
| `WEB_URL` | Public https link of your app, e.g. https://yourapp.up.railway.app (see Web editor below) |
| `ADMIN_ID` | your Telegram user ID (default: 6658706300) |

## Deploy on Railway
1. Upload this folder to your GitHub repository.
2. Railway -> New Project -> Deploy from GitHub repo.
3. Add the variables above in the Variables tab.
4. Railway builds from the Dockerfile and starts the bot automatically.

## Deploy on a VPS
```
git clone <your-repo-link> && cd <folder>
docker build -t editorbot .
docker run -d --restart always -e BOT_TOKEN=... -e API_ID=... -e API_HASH=... -e MONGO_URI=... editorbot
```

## How it works
Send a video, pick a button, give input if needed, and get the edited video back. Each edit stacks on top of the previous one. Use `/done` to delete your files.

## Staff commands (admin and moderators)
- `/stats` : user and edit counts
- `/broadcast message` : message everyone (or reply to a message with /broadcast)
- `/ban ID` and `/unban ID`

## Admin-only commands
- `/addmod ID` : make someone a moderator
- `/removemod ID` : remove a moderator
- `/mods` : list all moderators
- `/commands` : shows the command list (staff only)

Moderators can use /stats, /broadcast, /ban and /unban. Moderators cannot ban the admin or other moderators, and cannot add or remove moderators.

## Web editor (Telegram Mini App)
MEGA EDITOR (Stage 1) is a Telegram Mini App by AniTimes Network. Features: video preview, timeline with thumbnails and drag trim handles, aspect ratios (Original, 9:16, 1:1, 16:9, 4:5, 2:3) with blur, black bars or crop, rotate, mirror, flip, zoom, blur, speed, 6 filters, text, music with volume and fades, resolution (480p to 4K), frame rate, undo, send to Telegram and download.

Not built yet (coming in later stages): split and multi-clip timeline, multiple tracks, stickers, overlays, subtitles, masks, mosaic, cutout. AI features (background removal, AI avatars, text-to-speech, AI upscaling) will need external APIs or a GPU service.

Setup on Railway:
1. Open your service -> Settings -> Networking -> Generate Domain.
2. Copy the https link and add it as the `WEB_URL` variable. Redeploy.
3. Send /start or /editor to the bot and tap the Open web editor button.

Notes: web uploads are limited to 500 MB, and web files are deleted after 1 hour.
