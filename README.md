# Kulsh AI Bot 🍷🗿

[![Python](https://img.shields.io/badge/Python-3.14%2B-blue)](https://python.org)
[![License](https://img.shields.io/badge/License-AGPL_v3-green.svg)](LICENSE)
[![Discord](https://img.shields.io/badge/Discord-Bot-5865F2)](https://discord.com/oauth2/authorize?client_id=1489421179461701663)
[![Telegram](https://img.shields.io/badge/Telegram-Bot-26A5E4)](https://t.me/Kulsh_aibot)

**Kulsh** is a foul-mouthed, witty, and oddly brilliant AI companion built for Discord and Telegram.  
He codes, cracks jokes, insults your friends (lovingly), and can join voice channels to listen and speak his mind.  
Powered by a multi-provider AI cascade (EtageOne → Google Gemini) and a generous dose of post-Soviet humor.  
Now also a brutally honest **looksmaxxing analyst** – upload a face photo and get a full PSL rating, tier, and stylish infographic.

> *"Ты — Кульш, современная языковая модель ИИ... Используй сочетание «🍷🗿»..."*

---

## ✨ Features

- **Dual Platform** – Fully asynchronous operation across **Telegram** and **Discord** simultaneously.
- **Advanced Voice Interaction (Discord Exclusive)**
  - **Speech Recognition:** Uses a custom `AudioSink` to listen to users. It has a **65% probability** to respond to any detected speech.
  - **Neural TTS:** High-fidelity voice synthesis via `edge-tts` (Microsoft Neural voices).
  - **Silence Detection:** Intelligent buffering that waits for a pause in speech before processing.
- **Multi-Provider AI Cascade** – Requests go through a priority chain and stop at the first success (see [Tech Stack](#️-tech-stack)).
- **Contextual Memory** – Rolling context window (last 20 interactions) per chat, enriched with **relative timestamps** ("2 ч назад") so the model always knows how old each message is.
- **Real-Time Awareness** – The current Moscow time is injected into every system prompt as the single source of truth, so the bot never anchors to a stale "it's 2 AM" from hours ago. A guard also strips any leading time/date prefix the model tries to add to its own messages.
- **Vision Support** – Capable of analyzing images and providing sarcastic captions or technical descriptions.
- **AI Personality** – Custom-tuned system prompt for a unique "homie" persona with three communication modes.
- **Three Communication Modes** – `classic` (Обычный, default homie), `assistant` (structured helper), `pro` (step-by-step reasoning, DM only).
- **Message Splitting** – When enabled, the bot naturally breaks replies into multiple short messages (via `!separate` marker, with a fallback that also honours blank-line and sentence boundaries) for a live, human texting feel. The model is explicitly forbidden from using `Enter` / `Shift+Enter` as a separator.
- **Emoji Reactions** – The bot can react to the user's message with an emoji instead of (or in addition to) a text reply, on **both** platforms.
- **Emoji Discipline** – In `classic` mode the bot keeps emojis to an absolute minimum and the output is post-filtered (only 🍷🗿 survive).
- **Remote Administration** – Built-in logging system that allows owners to retrieve `bot.log` files and live stdout directly via chat commands (works in servers **and** DMs).
- **Automated Engagement** – Periodic auto-posting of "random thoughts" to keep the chat alive.
- **Donation System** – Support via Telegram Stars and DonationAlerts integration with a cross-platform leaderboard.
- **🔄 Auto-Update** – Authorized users can trigger a `git pull` and automatic restart directly from Discord (`кульш обновись`), with automatic rollback if a new commit fails the smoke check. Requires systemd setup.
- **🆕 Interactive Discord UI** – The full settings panel is built from native Discord components: one navigator select plus buttons for toggles, and sub-menus with select menus for language, theme, mode and model — mirroring the Telegram UX. Slash commands are synced **globally**, so the `/` command list is populated in every server the bot is in.
- **🆕 Drawing Engine (Pillow)** – Kulsh can draw arbitrary images **on his own**, without any special command: if the latest user message asks for a picture, he emits a `!draw` JSON spec that the bot renders with Pillow (shapes, lines, polygons, bezier/SVG paths, gradients, text with custom fonts, shadows, blurs, image overlays — including images pulled straight from a URL). A restricted `!term` terminal lets him fetch fonts/overlay images from any public host (private/loopback/link-local addresses are blocked as SSRF) and `pip install` a whitelisted set of rendering packages; temporary assets are sandboxed and deleted right after the finished image is sent. Drawing can be toggled per chat in settings.
- **🆕 Rich Draw Replies** – A single model reply can mix text and a picture: text before the `!draw` block is sent as its own messages, text right after the block becomes the photo caption, and anything past a `!separate` becomes further messages.
- **🆕 Interactive Web Search** – `!search` now shows a live animation ("🗿 поиск в интернете…" → "🍷 читаю wikipedia.com") that is removed before the final answer. The model receives the results **and** the source links, decides how to present them, and keeps the links in context so it can hand them over on request.
- **🆕 Balance & Paid Models** – a real ruble balance for premium models. Free models cost nothing; paid models are charged **after** a successful response by the actual token usage, so a failed request is never billed. When a paid model is selected with an empty balance, the bot switches to a free model and says so in chat. DonationAlerts top-ups are credited by the `ID<your Telegram/Discord id>` code in the donation message.
- **🆕 Rich Balance & Profile** – `/balance` and `/profile` are rich Telegram messages (headings, tables, dividers) with coloured buttons, and the profile screen replaces the balance screen in the same message instead of sending a new one. In groups the menu is delivered to DM; if the DM is closed, the bot replies in chat with a `t.me/<bot>?start=balance` link. Discord gets matching embeds and buttons.
- **🆕 Support Tickets** – `/support` (or the button) creates a ticket, forwards it to the support admin in DM, and relays the admin's reply back to the user on both platforms.
- **🆕 Telegram Command List** – the bot registers a localised `/` command list with emoji and readable descriptions via `set_my_commands`, so it appears in the input field and under the Menu button.
- **🆕 Company-first Model Picker** – the model screen shows only companies first (Auto, Anthropic, DeepSeek, Google DeepMind, Moonshot AI, OpenAI, Z.AI, xAI, Alibaba); tapping a company opens its models with a Back button. Paid models are marked with 💎.
- **🆕 Looksmaxxing Analysis** – Strict facial aesthetics evaluation.
  Upload a photo (in Discord or Telegram) with the `кульш psl` command and receive:
  - Objective **PSL rating** (1.0–8.0) and exact **tier** (Sub3 to True Adam / True Eve) with tier distribution chart
  - "You outperform X% of people" percentile based on normal distribution
  - Detailed breakdown of skin, eyes, jawline, bloat, bone structure, symmetry, canthal tilt
  - List of **strengths** and **weaknesses** (no sugarcoating)
  - Optional **improvement advice** (softmaxxing / hardmaxxing)
  - Graceful handling of **non-human images** — no more "Failed to parse AI response" error, just a friendly nudge
  - Stylish **infographic** with dark/light theme support and English/Russian language settings
- **🆕 Femboy Rate** – A dedicated softness/femininity rating on the FMB scale (1.0–10.0) with its own tier ladder, infographic and battle mode.

---

## 🛠️ Tech Stack

- **Core:** Python 3.14+
- **AI Engine (priority cascade):**
  - **EtageOne** (`glm-5.3-flash`, `deepseek-v4.1-flash`, `kimi-k3`, `kimi-k3.1-pro`, `deepseek-v4-pro`, `gpt-6-luna`, `claude-haiku-5-5`, `gpt-6.1-terra`, `gpt-6.1-sol`)
  - **Google Generative AI / Gemini** (Gemini 3.8 Flash, 3.7 Flash, 3.6 Flash, 3.5 Flash, 3.5 Flash Lite, 2.5 Flash, 2.5 Flash Lite)
  - A successful response is **not** passed to the next provider. EtageOne models are tried on EtageOne, then skipped for Gemini. `kimi-k3`, `kimi-k3.1-pro`, `claude-haiku-5-5`, `gpt-6.1-terra` and `gpt-6.1-sol` are EtageOne-only.
- **Frameworks:** `pyTelegramBotAPI` (Async), `discord.py` 2.x
- **Voice Processing:** `discord-ext-voice-receive`, `SpeechRecognition`, `pydub`
- **Audio/Networking:** `FFmpeg`, `aiohttp`, `edge-tts`
- **Image Processing:** `Pillow` (infographic generation for looksmaxxing / femboy reports)
- **Donations:** `python-socketio` (DonationAlerts listener)
- **Logging:** `RotatingFileHandler` for automated log management.

---

## 📦 Installation & Setup

### 1. Clone the repository
```bash
git clone https://github.com/starfall-apk/kulsh.git
cd kulsh
```

### 2. Install Dependencies
Ensure you have **FFmpeg** installed on your host system (Linux: `sudo apt install ffmpeg`).
```bash
pip install -r requirements.txt
```

### 3. Environment Configuration
The bot requires a `.env` file to function. Create a file named `.env` in the root folder and populate it:
```env
# API Keys
TG_TOKEN=your_telegram_bot_token
DISCORD_TOKEN=your_discord_bot_token
AI_KEY=your_google_gemini_api_key_fallback
AI_KEY_1=your_primary_gemini_key
AI_KEY_2=your_secondary_gemini_key
AI_KEY_3=your_tertiary_gemini_key
ETAGEONE_API_KEY=your_etageone_api_key

# IDs & Configuration
TG_TARGET_CHAT=your_target_group_id
DS_ALLOWED_GUILD_ID=your_discord_server_id
DONATIONALERTS_CHANNEL_ID=your_donation_alerts_channel_id
DONATIONALERTS_TOKEN=your_donationalerts_token
DONATIONALERTS_PAGE=your_donationalerts_page_url
DONATIONALERTS_CLIENT_ID=your_donationalerts_app_client_id
DONATIONALERTS_CLIENT_SECRET=your_donationalerts_app_client_secret
DONATIONALERTS_REFRESH_TOKEN=your_donationalerts_refresh_token
USD_TO_RUB=90
SUPPORT_ADMIN_TG=your_telegram_id
SUPPORT_ADMIN_DS=your_discord_id

# Optional
REPO_PATH=/path/to/bot/folder
```

**Notes on the AI cascade:**
- `ETAGEONE_API_KEY` is required.
- EtageOne models (`glm-5.3-flash`, `deepseek-v4.1-flash`, `kimi-k3`, `kimi-k3.1-pro`, `deepseek-v4-pro`, `gpt-6-luna`, `claude-haiku-5-5`, `gpt-6.1-terra`, `gpt-6.1-sol`, `gpt-6-astra`, `grok-4.7`, `claude-fable-5-1`, `claude-opus-5-5`, `claude-sonnet-5-5`, `qwen3.8-max-0902`) try EtageOne first.
- `kimi-k3`, `kimi-k3.1-pro`, `claude-haiku-5-5`, `gpt-6.1-terra` and `gpt-6.1-sol` are EtageOne-only and skipped for Gemini.
- `AI_KEY` is a Gemini fallback. Use `AI_KEY_1`, `AI_KEY_2`, `AI_KEY_3` for the Gemini multi-key fallback.
- A successful response stops the chain; later providers are not called.

### 4. Launch
```bash
python -m src.app
# or, equivalently
python kulsh.py
```

---

## 🖥️ Production Deployment (systemd + auto-update)

For the auto-update feature (`кульш обновись`), deploy the bot as a systemd service:

### 1. Configure Git in the bot directory
```bash
cd /path/to/bot/folder
git config --global user.email "bot@kulsh.ai"
git config --global user.name "Kulsh Bot"
git config --global pull.rebase false
```

### 2. Create systemd service
```bash
sudo nano /etc/systemd/system/kulsh.service
```

Paste (replace paths and user):
```ini
[Unit]
Description=Kulsh Discord Bot
After=network.target

[Service]
Type=simple
User=your_username
WorkingDirectory=/path/to/bot/folder
ExecStart=/path/to/bot/folder/venv/bin/python -m src.app
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

### 3. Enable and start
```bash
sudo systemctl daemon-reload
sudo systemctl enable kulsh
sudo systemctl start kulsh
```

### Useful management commands
```bash
sudo systemctl status kulsh       # Check status
sudo systemctl stop kulsh         # Stop bot
sudo systemctl start kulsh        # Start bot
sudo systemctl restart kulsh      # Manual restart
sudo journalctl -u kulsh -f       # Live logs
```

The `кульш обновись` command performs a `git fetch` + `git pull --ff-only`, then runs a syntax + import **smoke check** on the result. If the new code fails, the bot automatically rolls back to the last working commit and keeps running.

---

## 🎮 Commands

### Telegram — slash commands
| Command | Description |
|---------|-------------|
| `/start` | Greeting + start keyboard. |
| `/menu` | Interactive menu with all sections. |
| `/help` | Full command list. |
| `/status` | Bot status (uptime, latency, mode). |
| `/donate` | Support the project. |
| `/donate_stars <N>` | Donate via Telegram Stars (invoice). |
| `/balance` | Balance, top-up code and payment menu. |
| `/profile` | Profile card with balance and top-up stats. |
| `/support [text]` | Contact support (creates a ticket). |
| `/togglepremiumfunctionsadmin` | (Owner only) Toggle premium features. |

### Telegram — text commands
| Command | Description |
|---------|-------------|
| `кульш [текст]` | General interaction – chat, ask questions, get roasted. |
| `кульш конфиг` / `кульш настройки` | Open the inline settings panel. |
| `кульш статус` | Bot status. |
| `кульш поиск <запрос>` / `кульш найди <запрос>` | Web search with an AI summary. |
| `кульш график <описание>` | Generate an infographic (photo attachment supported). |
| `кульш аватарка` | Describe a user's avatar. |
| `кульш вспомни медиа [N]` | Recall and describe recent media (`!recall_media`). |
| `кульш логи` | (Admins/owner) Send the current `bot.log`. |
| `кульш донаты` | Top donators leaderboard. |
| `кульш psl` / `кульш psl совет` | Looksmaxxing analysis (needs a photo). |
| `кульш баттл` / `кульш battle` | Two-photo PSL battle (send as an album). |
| `фембой рейт` / `femboy rate` | Femboy Rate analysis (needs a photo). |
| `фембой баттл` / `femboy battle` | Two-photo femboy battle (send as an album). |

### Discord — slash commands
| Command | Description |
|---------|-------------|
| `/start` | Greeting message. |
| `/menu` | Interactive menu. |
| `/help` | Full command list. |
| `/status` | Bot status. |
| `/config [scope]` | View / change channel settings (`self` / `shared`, admin only). |
| `/donate` | Support the project. |
| `/balance` | Balance and top-up menu (sent to DM in servers). |
| `/profile` | Profile with balance and top-up stats. |
| `/support [text]` | Contact support (creates a ticket). |
| `/avatar [user]` | Describe an avatar. |
| `/recall [count]` | Recall and describe recent media. |
| `/search <query>` | Web search with an AI summary. |
| `/chart <description>` | Generate an infographic. |
| `/psl <image> [advice]` | Looksmaxxing analysis. |
| `/battle <image1> <image2>` | Two-photo PSL battle. |
| `/femboy <image> [advice]` | Femboy Rate analysis. |
| `/femboy-battle <image1> <image2>` | Two-photo femboy battle. |
| `/groupinfo` | Info about the current server. |
| `/userinfo [user]` | Info about a user. |
| `/logs` | (Admins) Send the current `bot.log`. |

### Discord — text commands
| Command | Description |
|---------|-------------|
| `кульш [текст]` | General interaction. |
| `кульш конфиг` / `кульш настройки` | View / change channel settings. |
| `кульш обновись` | (Authorized) `git pull` + auto-restart with rollback. |
| `кульш статус` | Bot status. |
| `кульш поиск <запрос>` | Web search. |
| `кульш график <описание>` | Generate an infographic. |
| `кульш аватарка` | Describe an avatar. |
| `кульш донаты` | Top donators leaderboard. |
| `кульш логи` | (Authorized) Send `bot.log`. |
| `кульш зайди в войс` | Summon to your voice channel (starts listening). |
| `кульш выйди из войса` | Disconnect from voice. |
| `кульш psl`, `кульш баттл`, `фембой рейт`, `фембой баттл` | Same ratings as in Telegram. |

### In-chat settings (`кульш конфиг <параметр> <значение>`)
| Parameter | Values | Description |
|-----------|--------|-------------|
| `область` / `scope` | `для_себя` / `для_всех` | Per-user or shared-per-channel config (Discord admin only). |
| `язык` / `language` | `ru` / `en` | UI and infographic language. |
| `тема` / `theme` | `тёмная` / `светлая` | Infographic theme. |
| `режим` / `mode` | `обычный` / `ассистент` / `pro` | Communication mode. |
| `модель` / `model` | `<номер>` / `авто` | Force a specific model or auto-cascade. |
| `разбивка` / `split` | `вкл` / `выкл` | Message splitting. |
| `реакции` / `reactions` | `вкл` / `выкл` | Emoji reactions. |
| `стикеры` / `stickers` | `вкл` / `выкл` | Stickers / GIFs. |
| `автоответ` / `autoreply` | `вкл` / `выкл` | Random observer replies. |
| `рандом` / `random` | `вкл` / `выкл` | Periodic random posts. |
| `поиск` / `search` | `вкл` / `выкл` | Web search availability. |
| `рисование` / `drawing` | `вкл` / `выкл` | Autonomous image drawing. |
| `промпт` / `prompt` | `<текст>` / `сброс` | Custom mandatory prompt. |

> **Note:** `разбивка` (Split) and `стриминг` (Streaming) are mutually exclusive.

> **Note (Discord scope):** On Discord the single source of truth for every setting — including the model — is the **effective** config resolved from the channel `scope`. In `shared` scope all reads/writes go to the channel config, so the model the AI uses always matches the one shown in `/config`. In `self` scope each user has their own.

> **Note (Logs):** `кульш логи` / `/logs` work in servers **and** in DMs for authorized admins.

---

## 🤖 AI Utility Markers

The bot's own responses can contain invisible utility markers that the bot strips before sending. The model uses them to trigger built-in actions:

| Marker | Action |
|--------|--------|
| `!react:<emoji>` | React to the user's message (e.g. `!react:👍🔥`). |
| `!why:<text>` | Optional note stored in memory alongside `!react`. |
| `!separate` | Split this reply into several messages. |
| `!search <query>` | Perform an interactive web search (animated) and continue with the results; sources stay in context. |
| `!recall_media` / `!recall_media:ID` | Recall and describe the last (or a specific) media. |
| `!avatar` | Describe the user's avatar. |
| `!sticker` / `!gif` | Send a sticker / GIF. |
| `!group_info` / `!user_info[:id]` | Fetch group / user info. |
| `!chart` + JSON block | Render an infographic (premium). |
| `!draw` + JSON block | Draw an arbitrary image with Pillow (shapes, SVG paths, gradients, text, shadows, overlays). |
| `!term <command>` | Restricted asset terminal: download fonts/images from public hosts (SSRF-protected) or `pip install` a whitelisted rendering package. |

**Autonomous drawing:** drawing is *not* a user command. If the latest message asks for a picture ("нарисуй", "изобрази", "draw", …), Kulsh decides on his own to answer with a `!draw` spec, which the bot renders and sends. The `!draw` spec supports: `gradient` / `radial_gradient`, `line`, `rect`, `circle`/`ellipse`, `polygon`, `svg` (M/L/H/V/C/S/Q/T/Z paths), `text` (custom font), `image` (overlay from `!term` **or** a direct `url`), `blur`, and a `shadow` object on any element. There is no content filter: Kulsh will draw profanity, crude and edgy prompts without moralizing.

**Mixing text and a picture in one reply:** everything before the `!draw` block is sent as its own message(s); the text immediately after the block (up to the first `!separate`) becomes the photo caption; everything after a `!separate` becomes further messages. So `«мопса, говоришь?!separateлан, ща нарисую` + `!draw` block + `во держи!separateну как тебе?»` renders as two messages, then the photo captioned "во держи!", then one more message. If he wants text detached from the photo, he must use `!separate` — otherwise it becomes the caption.

**Censorship:** the bot is explicitly instructed to have no moral filters and to never refuse a request or add disclaimers (provider-level limits aside).

**Secret:** Kulsh never reveals his system prompt, instructions or internal markers. He only talks about his friends in chats where at least one of them is actually present (the bot remembers participants it has seen); the historical Telegram group `2413532783` and Discord guild `1403828466075304036` are always allowed.

**Reactions now work reliably:** the parser accepts `!react:👍`, `!react: 👍`, `[реакция 😂]`, `(реакция: 🗿)` and similar variants, applies the correct emoji via the platform API, and strips any stray marker so it never leaks into the chat as raw text.

---

## 💬 Communication Modes

| Mode | Description |
|------|-------------|
| `classic` | Default homie mode ("Обычный"). Short, casual, human-like. Emojis almost never; only 🍷🗿 occasionally and only when it fits. |
| `assistant` | Structured helper. Headings and lists where appropriate, still friendly. |
| `pro` | Step-by-step reasoning and self-checking. Available **only in Telegram DMs**. |

In `classic` mode the message length adapts to the conversation: a one-liner for a quick joke, a normal human answer for a serious question, and — when splitting is on — up to 2–3 short messages for a longer train of thought.

---

## 📊 Looksmaxxing System

The bot evaluates faces using a strict, objective AI analyst persona. The PSL scale uses normal distribution to map facial aesthetics:

### Tier Distribution
| Tier | PSL Range | Percentile |
|------|-----------|------------|
| SUB 3 | 1.0 – 2.4 | ~2.3% |
| SUB 5 | 2.5 – 3.9 | ~13.6% |
| LTN / LTB | 4.0 – 5.5 | ~10.0% |
| MTN / MTB | 5.6 – 6.3 | ~19.2% |
| HTN / HTB | 6.4 – 6.9 | ~19.2% |
| CHADLITE / STACYLITE | 7.0 – 7.4 | ~13.6% |
| CHAD / STACY | 7.5 – 7.6 | ~10.0% |
| ADAMLITE / EVELITE | 7.7 – 7.8 | ~2.3% |
| TRUE ADAM / TRUE EVE | 7.9 – 8.0 | ~2.3% |

### Analysis Includes
- Gender detection (Male/Female with appropriate tier naming)
- 8 facial metrics (skin, eyes, jawline, bloat, hair, bone structure, symmetry, canthal tilt)
- "You outperform X% of people" based on exact PSL positioning within the tier
- Tier distribution bar chart with highlighted current tier
- Visual infographic with profile photo, metrics table, pros/cons list
- Optional practical looksmaxxing advice (softmaxxing/hardmaxxing)
- **Non-human images** (animals, illustrations, objects) return a friendly message instead of a parsing error

---

## 💐 Femboy Rate System

A separate rating for softness / femininity on the **FMB scale (1.0–10.0)**:

| Tier | FMB Range |
|------|-----------|
| CHAD | 1.0 – 2.4 |
| SIGMA | 2.5 – 3.9 |
| NORMIE | 4.0 – 5.4 |
| SOFTBOY / SOFTGIRL | 5.5 – 6.4 |
| CUTIE | 6.5 – 7.4 |
| FEMBOY / FEMGIRL | 7.5 – 8.4 |
| TWINK | 8.5 – 9.2 |
| ULTRAFEM | 9.3 – 9.7 |
| GODDESS | 9.8 – 10.0 |

Metrics: softness, hair, style, build, expression, skin, charm, voice vibe. Includes its own infographic and two-photo battle mode.

---

## 💳 Balance & Paid Models

The bot has a real ruble balance. Free models cost nothing and do not consume the website's daily free limit; the bot has no daily credits system. Paid models are charged **after** a successful response by the actual token usage (`USD_TO_RUB` converts the provider price). If no answer was received, nothing is charged.

| Model | Input / 1M | Output / 1M | Cached input / 1M | Cache write / 1M |
|-------|-----------|-------------|-------------------|------------------|
| Kimi K3.1 Pro | $0.16 | $0.80 | $0.014 | $0 |
| GPT-6 Astra | $0.34 | $1.70 | $0.034 | $0 |
| Grok 4.7 | $0.20 | $1.00 | $0.02 | $0 |
| Claude Fable 5.1 | $1.20 | $6.00 | $0.12 | $1.20 |
| Claude Opus 5.5 | $0.60 | $3.20 | $0.06 | $0.60 |
| Claude Sonnet 5.5 | $0.40 | $2.00 | $0.04 | $0.40 |
| Qwen3.8 Max | $0.20 | $1.00 | $0.02 | $0 |

Everything else is free. Big paid models are never used for PSL / Femboy ratings — those always run on a cheap model. When a paid model is selected with an empty balance, the bot refuses the request with a clear in-chat notice (current balance, the model, and where to top up) instead of silently spending on a paid cascade.

### Top-up flow
1. Run `/balance` (or press “Баланс” in the menu) and copy the tag `ID<your id>`.
2. Open the payment link from the same screen and paste the tag into the DonationAlerts **message** field.
3. The donation poller credits the matching account automatically; “Проверить платёж” forces an immediate check.

The minimum top-up is 1 ₽ by default and can be changed with `DONATIONALERTS_MIN_TOPUP`.

If `/balance` is used in a group, the menu is delivered to DM. When the DM is closed, the bot replies in chat with a `https://t.me/<bot>?start=balance` link. Legal documents: [Пользовательское соглашение](https://telegra.ph/Kulsh-AI--Polzovatelskoe-soglashenie-10-17) · [Политика конфиденциальности](https://telegra.ph/Kulsh-AI--Politika-konfidencialnosti-10-17-2).

> DonationAlerts API (donation index + OAuth): https://www.donationalerts.com/apidoc

---

## 🧰 DM Tools (Telegram)

Send the bot a file in a private chat:
- **`.zip` archive** — the bot unpacks it, lets the AI edit the files according to your request, repacks, and returns the result.
- **Text file** — the bot reads it and answers your question about its contents.

---

## 👥 Credits & Special Thanks

### Development Team
- **starfall-apk (st6rf9ll)** — Lead Author, Creator & AI Logic Architect (formerly *downfalls2920*).
- **pomidorka1515 (pomi)** — Co-author & Infrastructure (Bot Hosting & Linux Optimization).

### Special Thanks
- **"Секретный чат"** — The legendary Discord server where Kulsh was born, tested, and raised.
- **Kulsh** — My close friend whose name and personality inspired the creation of this bot.

---

## 📞 Contact & Support

If you have any technical questions, suggestions, or just want to chat about the project:

- **starfall-apk (Lead Dev):** [Telegram](https://t.me/wf9ll) | Discord: `st6rf9ll`
- **pomidorka1515 (Hosting):** [Telegram](https://t.me/pomidorka_1515) | Discord: `pomidorka1515`

Project Link: [https://github.com/starfall-apk/kulsh](https://github.com/starfall-apk/kulsh)

Web Version: [https://kulsh-ai.web.app/](https://kulsh-ai.web.app/)

Donate: [https://kulsh-ai.web.app/donate.html](https://kulsh-ai.web.app/donate.html)

---

## 📜 License
This project is licensed under the AGPL v3.0 License – see the [LICENSE file](LICENSE) for details.
## Shared accounts with the website

The bot and [kulsh-web](https://github.com/starfall-apk/kulsh-web) use one account
and one balance. Both read and write the same Upstash Redis keys, so a top-up or a
paid request in Telegram/Discord is immediately visible on the site and in the public API.

Set these environment variables (Vercel adds them automatically when you connect
Upstash Redis to the web project):

```
KV_REST_API_URL=https://...upstash.io
KV_REST_API_TOKEN=...
```

When they are missing the bot falls back to the old local `balances.json`, so local
development keeps working. On the first start with cloud enabled the old balances are
copied into Redis once (`cloud_migrated.json` marks the migration).

### Linking

`/profile` → **🔗 Привязать аккаунт** gives a one-time 8-character code. On the site:
account menu → **Привязать** → enter the code. Telegram logins on the site use the
same `tg:<id>` identity as the bot, so a Telegram sign-in already shares the balance.
Google and GitHub are attached to the same account the same way.

If the chosen sign-in method already belongs to another account, the site shows a
warning with both balances and the resulting sum. After confirmation the accounts are
merged: balances and total top-ups are summed, daily usage takes the larger value,
API keys are combined (up to 10). Old sessions keep working through a merge redirect.

### Promo codes

Admin panel → **🎁 Промокоды**:

```
КОД amount 500 10 7   # 500 ₽, 10 activations, 7 days
КОД bonus 25 0 0      # +25% to the next top-up, unlimited, no expiry
```

Users redeem them with `/profile` → **🎁 Промокод** or the same button on the balance
screen. A bonus is applied automatically to the next DonationAlerts payment and then
cleared. Each account can use a code once.

### API keys

`/profile` → **🔑 API-ключи** creates and revokes keys for the public API
(`https://kulsh.vercel.app/api/v1`). The secret is shown once; only a SHA-256 hash is
stored. Keys are shared with the site, where the same list is available in the account menu.
