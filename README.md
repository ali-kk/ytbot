# ytbot

A Telegram bot that sends songs from YouTube as audio files (M4A, the original YouTube audio, no quality loss):

- Send it a **song name**: it shows the top YouTube results (title, channel, views, length), you tap a number, it sends the song.
- Send it a **YouTube link** (youtube.com, youtu.be, Shorts, YouTube Music): it sends the song right away.

---

## For the human

**The only thing you need to provide is a Telegram bot token.** No API keys, no accounts, no domain,
no payment. (The WARP proxy used to get around YouTube blocks is free and needs no sign-up.)

1. Get a Linux server (Ubuntu 22.04/24.04 or Debian 12, 1 GB RAM is enough) you can SSH into with `sudo`.
2. Create your own bot: open Telegram, talk to [@BotFather](https://t.me/BotFather), send `/newbot`, follow the steps. It gives you a **token** that looks like `123456789:AAH...`. Keep it secret.
3. Give this README to your AI coding agent (with SSH access to the server) and say:

   > Follow the "For the AI agent" section of https://github.com/ali-kk/ytbot to deploy this bot on my server. Ask me for the bot token when you need it.

---

## For the AI agent

You are deploying this bot on a Linux server. Follow the steps **in order**. Run every command
exactly as written. After each step, do the **Check**. If a check fails, stop and fix it
(see [Troubleshooting](#troubleshooting)) before going on. Do not skip steps.

### Rules (read before you start)

- **The bot token is a secret.** Never print it, never paste it in chat, never commit it to git. It only goes in `/opt/ytbot/.env`.
- **The bot needs NO open ports, NO domain, NO nginx, NO HTTPS, NO firewall changes.** It only makes outgoing connections. Do not set any of that up.
- **Only one copy of the bot may run per token.** If the same token runs anywhere else (another server, a laptop), both copies break with a `Conflict` error.
- **Cloudflare WARP must stay in `proxy` mode.** Never run `warp-cli mode warp`: it reroutes all the server's traffic and can cut your SSH connection.
- **Do not run extra test downloads.** Only run the tests the steps ask for. Dozens of YouTube downloads in a few minutes get the server's IP (and the WARP IP) flagged by YouTube for hours.
- Everything goes in `/opt/ytbot` and runs as a system user named `ytbot`. Do not change these paths: `ytbot.service` expects them.

### What each file is

| File | What it is |
|---|---|
| `bot.py` | The whole bot. |
| `test_bot.py` | Quick self-check (link detection etc.). Prints `ok`. |
| `requirements.txt` | Python packages: `python-telegram-bot`, `yt-dlp` (downloads from YouTube), `deno` (yt-dlp needs it to solve YouTube's JavaScript checks). |
| `.env.example` | Template for `.env` (the bot token + proxy address). |
| `ytbot.service` | systemd service: starts the bot at boot, restarts it if it crashes, updates `yt-dlp` and restarts once a day. |

### Step 1: Check the server

```bash
cat /etc/os-release | head -2
sudo -n true && echo "sudo ok"
```

**Check:** it says Ubuntu or Debian, and prints `sudo ok`. (Other distros work too, but you must translate the `apt-get` commands.)

### Step 2: Install system packages

```bash
sudo apt-get update
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y git python3 python3-venv ffmpeg curl gpg lsb-release
```

**Check:**

```bash
python3 --version && ffmpeg -version | head -1 && git --version
```

Python must be **3.9 or newer**. All three commands must print a version.

### Step 3: Download the bot and create its user

```bash
sudo git clone https://github.com/ali-kk/ytbot.git /opt/ytbot
sudo useradd --system --home-dir /opt/ytbot --shell /usr/sbin/nologin ytbot
sudo chown -R ytbot:ytbot /opt/ytbot
```

If `useradd` says the user already exists, that is fine; continue.

**Check:** `ls -a /opt/ytbot` shows `bot.py`, `test_bot.py`, `requirements.txt`, `.env.example`, `ytbot.service`, `README.md`.

### Step 4: Install Python packages

```bash
cd /opt/ytbot
sudo -H -u ytbot python3 -m venv /opt/ytbot/venv
sudo -H -u ytbot /opt/ytbot/venv/bin/pip install -q --upgrade pip
sudo -H -u ytbot /opt/ytbot/venv/bin/pip install -q -r /opt/ytbot/requirements.txt
```

**Check:**

```bash
sudo -H -u ytbot /opt/ytbot/venv/bin/python /opt/ytbot/test_bot.py
sudo -H -u ytbot /opt/ytbot/venv/bin/deno --version | head -1
```

It prints `ok` and a deno version. If `deno` is missing, see Troubleshooting.

### Step 5: Put the bot token in `.env`

Ask the human for their bot token (from @BotFather). Then run the commands below, replacing
`PASTE_TOKEN_HERE` with the token. Keep the single quotes.

```bash
sudo -H -u ytbot cp /opt/ytbot/.env.example /opt/ytbot/.env
sudo chmod 600 /opt/ytbot/.env
sudo -H -u ytbot sed -i 's|^BOT_TOKEN=.*|BOT_TOKEN=PASTE_TOKEN_HERE|' /opt/ytbot/.env
```

**Check:** the token works (this reads it from the file, so it is not printed):

```bash
sudo bash -c 'set -a; . /opt/ytbot/.env; curl -s "https://api.telegram.org/bot$BOT_TOKEN/getMe"' | grep -o '"username":"[^"]*"'
```

It prints `"username":"<the bot's name>"`. Tell the human the bot's username so they can confirm it's the right bot.
If it prints nothing, the token is wrong: ask the human again and repeat the `sed` line.

### Step 6: Test whether YouTube blocks this server

YouTube often blocks server/datacenter IPs with the message `Sign in to confirm you're not a bot`. Test it:

```bash
cd /tmp && sudo -H -u ytbot env PATH=/opt/ytbot/venv/bin:/usr/bin:/bin \
  yt-dlp -f bestaudio -o "/tmp/yttest.%(ext)s" "https://www.youtube.com/watch?v=dQw4w9WgXcQ" 2>&1 | tail -3
sudo rm -f /tmp/yttest.*
```

- If it ends with `[download] 100% ...`: YouTube does not block this server **today**. Still do Step 7. Blocks often start later.
- If it says `Sign in to confirm you're not a bot`: this server is blocked. Step 7 fixes it.

### Step 7: Set up the Cloudflare WARP proxy (free, bypasses YouTube blocks)

WARP gives the bot a Cloudflare IP address for YouTube traffic only. The bot tries the proxy
first and falls back to the direct connection if the proxy fails.

**Do the commands in this exact order. `mode proxy` MUST come before `connect`.**

```bash
curl -fsSL https://pkg.cloudflareclient.com/pubkey.gpg | sudo gpg --yes --dearmor -o /usr/share/keyrings/cloudflare-warp-archive-keyring.gpg
echo "deb [signed-by=/usr/share/keyrings/cloudflare-warp-archive-keyring.gpg] https://pkg.cloudflareclient.com/ $(lsb_release -cs) main" | sudo tee /etc/apt/sources.list.d/cloudflare-client.list
sudo apt-get update
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y cloudflare-warp

warp-cli --accept-tos registration new
warp-cli --accept-tos mode proxy
warp-cli --accept-tos proxy port 40000
warp-cli --accept-tos connect
sleep 5
warp-cli --accept-tos status
```

**Check:** `status` says `Connected`. Then:

```bash
curl -s https://cloudflare.com/cdn-cgi/trace | grep warp
curl -s -x socks5h://127.0.0.1:40000 https://cloudflare.com/cdn-cgi/trace | grep warp
```

- The **first** line must be `warp=off` (the server's normal traffic is untouched).
- The **second** line must be `warp=on` (the proxy works).

If the first line says `warp=on`, WARP took over all traffic: immediately run
`warp-cli --accept-tos mode proxy` and check again.

Now test YouTube through the proxy:

```bash
cd /tmp && sudo -H -u ytbot env PATH=/opt/ytbot/venv/bin:/usr/bin:/bin \
  yt-dlp --proxy socks5://127.0.0.1:40000 -f bestaudio -o "/tmp/yttest.%(ext)s" "https://www.youtube.com/watch?v=dQw4w9WgXcQ" 2>&1 | tail -3
sudo rm -f /tmp/yttest.*
```

**Check:** it ends with `[download] 100% ...`.

**If WARP cannot be installed** (unsupported OS/CPU) and Step 6 downloaded fine, you can skip WARP:
run `sudo -H -u ytbot sed -i 's#^YT_PROXY=.*#YT_PROXY=direct#' /opt/ytbot/.env`. Tell the human
that the bot may stop working if YouTube blocks the server later (see [Handling lots of users](#handling-lots-of-users-avoiding-youtube-blocks)).

### Step 8: Start the bot as a service

```bash
sudo cp /opt/ytbot/ytbot.service /etc/systemd/system/ytbot.service
sudo systemctl daemon-reload
sudo systemctl enable --now ytbot
sleep 30
systemctl is-active ytbot
sudo journalctl -u ytbot -n 20 --no-pager
```

**Check:** `is-active` prints `active`, and the log contains `Application started`.
The first start takes up to a minute because it updates `yt-dlp` first. If it prints `activating`,
wait 30 seconds and run the last two commands again.

### Step 9: Test with the human

Ask the human to open their bot in Telegram, press **Start**, and send a song name (for example `fairuz kifak inta`).

- They should get a list of 6 results with number buttons.
- Tapping a number should send back the song (an `.m4a` file that plays in Telegram's music player) within about 5–15 seconds.
- Then ask them to send a YouTube link (for example `https://youtu.be/dQw4w9WgXcQ`). The song should come back directly, with no list.
- Tapping the same song again should send it almost instantly (it is cached).

While they test, watch the log:

```bash
sudo journalctl -u ytbot -f
```

Press `Ctrl+C` to stop watching. A line like `route 1/2 failed, trying next` is only a warning and
is fine as long as the song arrives.

**Done.** The bot now starts by itself after reboots and restarts itself if it crashes.

---

## Everyday commands

| Task | Command |
|---|---|
| Is it running? | `systemctl is-active ytbot` |
| See logs | `sudo journalctl -u ytbot -n 50 --no-pager` |
| Restart | `sudo systemctl restart ytbot` |
| Stop | `sudo systemctl stop ytbot` |
| Update the bot code | `sudo -H -u ytbot git -C /opt/ytbot pull && sudo systemctl restart ytbot` |
| Change the token | `sudo -H -u ytbot sed -i 's#^BOT_TOKEN=.*#BOT_TOKEN=NEW_TOKEN#' /opt/ytbot/.env && sudo systemctl restart ytbot` |
| Is WARP up? | `warp-cli --accept-tos status` |

## Troubleshooting

| You see | Meaning | Fix |
|---|---|---|
| `Conflict: terminated by other getUpdates request` | The same token runs somewhere else. | Stop the other copy (another server, a laptop). Only one may run. |
| `Unauthorized` or `InvalidToken` | Wrong token in `.env`. | Redo Step 5. If the token leaked, send `/revoke` to @BotFather and use the new one. |
| `Sign in to confirm you're not a bot` (songs fail, search still works) | YouTube blocks the IPs the bot uses. | Make sure Step 7 passed. If it started right after many downloads in a short time, stop testing and wait a few hours: it usually clears by itself. For a lasting fix, add residential proxies: see [Handling lots of users](#handling-lots-of-users-avoiding-youtube-blocks). |
| `No supported JavaScript runtime` / `n challenge solving failed` | `deno` is missing from the bot's PATH. | `sudo -H -u ytbot /opt/ytbot/venv/bin/pip install deno`, then check `/opt/ytbot/venv/bin/deno` exists and restart. |
| `ffprobe/ffmpeg not found` | ffmpeg not installed. | `sudo apt-get install -y ffmpeg`, then restart. |
| Bot replies `الملف كبير جداً أو بث مباشر` | The video is longer than 20 minutes, bigger than 50 MB, or a live stream. Telegram bots cannot send files over 50 MB. | Normal. Pick a shorter video. |
| Bot shows a search list for a link instead of sending the song | The link is not a single video (a playlist or channel link). | Normal. Only single-video links are downloaded directly. |
| Downloads suddenly fail for every song | YouTube changed something and `yt-dlp` is outdated. | `sudo systemctl restart ytbot` (it updates `yt-dlp` on every start). |
| `status=203/EXEC` or `217/USER` in `systemctl status ytbot` | Wrong paths or the `ytbot` user is missing. | Redo Steps 3–4. The service needs exactly `/opt/ytbot` and user `ytbot`. |
| `warp-cli: command not found` | WARP not installed. | Redo Step 7, or skip it as described there. |

## Handling lots of users (avoiding YouTube blocks)

YouTube limits how much one IP address can download. When an IP is over the limit, the log shows
`Sign in to confirm you're not a bot`: songs fail, but search usually still works. A block lasts hours.

- YouTube's limit is about **300 songs per hour per IP**. Server (datacenter) IPs and Cloudflare WARP get
  blocked much sooner than that, especially by bursts (many downloads within a few minutes).
- The bot already protects itself:
  - A song sent once is re-sent from Telegram's cache: no YouTube request at all.
  - At most 3 downloads run at the same time (`DOWNLOADS` in `bot.py`), so a rush of users does not become a burst.
  - Requests rotate over all routes in `YT_PROXY`. A route that gets blocked moves to the back and is only
    used when the others fail; once it works again it rejoins the rotation.
  - `yt-dlp` is updated every day.
- **Small bot (you, friends, one group):** the default `YT_PROXY=socks5://127.0.0.1:40000,direct` is usually enough.
- **Many users:** add **rotating residential proxies**. They are paid (usually a few USD per GB; one song is
  about 4 MB, so roughly 250 songs per GB). Datacenter proxies and free proxy lists do not work: YouTube
  already blocks them, and free proxies can be unsafe.

How to add residential proxies (for the AI agent):

1. The human buys a **rotating residential proxy** plan that supports **sticky sessions** and gives you the
   proxy host, port, username and password.
2. In the provider's docs, find the sticky-session format. Usually a session id goes inside the username,
   for example `myuser-session-abc123`. Replace the id with the literal text `{session}`. The bot puts a new
   random id there for every song, so every song gets a fresh IP, while all requests for one song share the
   same IP (YouTube requires that).
3. Put the proxy first in `YT_PROXY`, keeping WARP and direct as fallbacks. Replace `USER`, `PASS`, `HOST`,
   `PORT`, and keep `{session}` exactly as written:

   ```bash
   sudo -H -u ytbot sed -i 's#^YT_PROXY=.*#YT_PROXY=http://USER-session-{session}:PASS@HOST:PORT,socks5://127.0.0.1:40000,direct#' /opt/ytbot/.env
   sudo systemctl restart ytbot
   ```

   If the username or password contains `@`, `#`, `,` or `&`, write them URL-encoded: `%40`, `%23`, `%2C`, `%26`.
   Several proxies (even from different providers) can be listed, separated by commas; the bot spreads
   songs across all of them.
4. Ask the human to send one song. In `sudo journalctl -u ytbot -n 20 --no-pager` there must be no
   `route 1/3 failed` line. The proxy password is never written to the log.

## Customizing (optional)

All settings are at the top of `bot.py`:

- `RESULTS = 6`: how many search results to show.
- `MAX_DURATION = 20 * 60`: longest allowed video, in seconds.
- To send **MP3** instead of M4A (some old car stereos need MP3): in `fetch_audio` change `"preferredcodec": "m4a"` to `"preferredcodec": "mp3", "preferredquality": "192"`, change both `m4a` endings (`"*.m4a"` and `.m4a"`) to `mp3`, then restart. This is about 2–3x slower (the audio must be re-encoded) and slightly lower quality.

The bot's replies are in Iraqi Arabic. To change them, edit the Arabic text strings in the functions
`start`, `on_query` and `send_audio` in `bot.py`, then restart the bot.

## How it works (short)

- Search: `yt-dlp` searches YouTube (`ytsearch6:<text>`) without downloading.
- Link: if the message contains a YouTube video link, the bot skips the search and sends the song.
- Download: `yt-dlp` downloads YouTube's AAC audio (`.m4a`) into a temporary folder. It is **not re-encoded**, so it is exactly YouTube's quality and fast: `ffmpeg` only adds the title, artist and cover art. The bot uploads it, and the temporary folder is deleted. A 4-minute song takes about 3 seconds on a small 2-CPU server. (In the rare case a video has no m4a audio, it is converted to m4a.)
- Live streams and videos over 20 minutes are refused **before** downloading.
- Cache: after a song is sent once, Telegram gives the bot an ID for that file. The bot saves it in `/opt/ytbot/sent_cache*` and next time re-sends the same file by ID, with no download or upload, in under a second. Deleting `sent_cache*` is safe; songs just get downloaded again.
- Many users are served at the same time; one slow download does not block others.
- Every YouTube request goes through one of the routes in `YT_PROXY` (rotating); if it fails, the next route is tried. See [Handling lots of users](#handling-lots-of-users-avoiding-youtube-blocks).
