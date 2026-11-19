# Video Editor Telegram Bot (Version 1.0 | Genesis Release)

Features: trim, speed, text, music, mute, extract audio, compress. Works with videos up to 2GB.

## Environment variables
| Name | Where to get it |
|---|---|
| `BOT_TOKEN` | @BotFather |
| `API_ID` | https://my.telegram.org -> API development tools |
| `API_HASH` | same page |
| `MONGO_URI` | MongoDB Atlas -> Connect -> Drivers (free cluster is enough) |
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

## Admin commands (ADMIN_ID only)
- `/stats` : user and edit counts
- `/broadcast message` : message everyone (or reply to a message with /broadcast)
- `/ban ID` and `/unban ID`
