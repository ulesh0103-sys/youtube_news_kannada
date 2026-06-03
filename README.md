# 🎬 YouTube News Automation Pipeline

**Fully automated news channel** — from RSS feeds to published YouTube videos, 6 times a day.

> Scrapes news → Writes scripts with AI → Generates voiceover → Creates video → Uploads to YouTube  
> **Cost: ₹0/month** (all free-tier APIs)

---

## 📋 Overview

This pipeline automates an entire YouTube news channel:

1. **Scrapes** trending news from RSS feeds (Karnataka, National, International)
2. **Generates** professional news scripts using Google Gemini AI
3. **Creates** natural voiceover audio
4. **Assembles** videos with stock footage from Pexels + text overlays
5. **Designs** eye-catching thumbnails automatically
6. **Uploads** to YouTube with proper titles, descriptions, tags & scheduling
7. **Runs on schedule** — 6 videos per day, fully unattended

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    SCHEDULER (scheduler.bat)                 │
│              Windows Task Scheduler – 6 daily slots          │
└─────────────┬───────────────────────────────────────────────┘
              │  triggers
              ▼
┌─────────────────────────────────────────────────────────────┐
│                    main.py (Orchestrator)                     │
│         Coordinates all modules, handles errors, logs        │
└──────┬──────┬──────┬──────┬──────┬──────┬───────────────────┘
       │      │      │      │      │      │
       ▼      ▼      ▼      ▼      ▼      ▼
   ┌──────┐┌──────┐┌──────┐┌──────┐┌──────┐┌──────┐
   │Scrape││Script││Voice ││Video ││Thumb ││Upload│
   │ News ││ Gen  ││ Gen  ││Assem ││Maker ││ YT   │
   └──┬───┘└──┬───┘└──┬───┘└──┬───┘└──┬───┘└──┬───┘
      │       │       │       │       │       │
      ▼       ▼       ▼       ▼       ▼       ▼
   RSS Feeds Gemini  gTTS/   FFmpeg  Pillow  YouTube
             AI      Edge            +Pexels Data API
                     TTS                      v3
```

---

## ⚙️ Prerequisites

| Requirement | Version | Notes |
|-------------|---------|-------|
| **Python**  | 3.9+    | [Download](https://www.python.org/downloads/) |
| **FFmpeg**  | Latest  | Required for video assembly |
| **Internet**| Always  | For APIs, RSS feeds, stock footage |
| **Windows** | 10/11   | For Task Scheduler (Linux users: use cron) |

---

## 🚀 Step-by-Step Setup

### Step 1: Download the Project

```bash
# Clone or download the project
cd C:\Users\mahesh\OneDrive\Desktop\ULESH\SCREEN SHOT\ai edtech
# Place the youtube-automation folder here
```

### Step 2: Install Python Dependencies

```bash
cd youtube-automation
pip install -r requirements.txt
```

This installs: `google-generativeai`, `feedparser`, `Pillow`, `gTTS`, `moviepy`, `pexels-api`, `google-api-python-client`, `google-auth-oauthlib`, and more.

### Step 3: Install FFmpeg

FFmpeg is required for video processing.

1. **Download** FFmpeg from: https://ffmpeg.org/download.html
   - Recommended: [gyan.dev builds](https://www.gyan.dev/ffmpeg/builds/) → download `ffmpeg-release-essentials.zip`
2. **Extract** to `C:\ffmpeg\`
3. **Add to PATH**:
   - Press `Win + X` → System → Advanced System Settings → Environment Variables
   - Under "System variables", find `Path` → Edit → New
   - Add: `C:\ffmpeg\bin`
   - Click OK → OK → OK
4. **Verify**: Open a new terminal and run:
   ```bash
   ffmpeg -version
   ```

### Step 4: Get Gemini API Key (FREE)

1. Go to **[Google AI Studio](https://aistudio.google.com/)**
2. Sign in with your Google account
3. Click **"Get API Key"** in the top right
4. Click **"Create API Key"** → select a Google Cloud project (or create one)
5. **Copy** the API key (starts with `AIza...`)
6. **Save** it – you'll add it to `config.py` in Step 7

> 💡 Free tier includes 15 requests/minute, 1 million tokens/day — more than enough!

### Step 5: Get Pexels API Key (FREE)

1. Go to **[Pexels API](https://www.pexels.com/api/)**
2. Click **"Your API Key"** or sign up for a free account
3. Fill in the application form:
   - App name: "YouTube News Automation"
   - Description: "Automated news video creation"
4. **Copy** your API key
5. **Save** it for Step 7

> 💡 Free: 200 requests/hour, 20,000/month — plenty for 6 videos/day.

### Step 6: Set Up YouTube API (FREE)

This is the most involved step – follow carefully:

#### a. Create Google Cloud Project
1. Go to **[Google Cloud Console](https://console.cloud.google.com/)**
2. Click the project dropdown (top bar) → **"New Project"**
3. Name: `youtube-news-automation` → Click **Create**
4. **Select** the new project from the dropdown

#### b. Enable YouTube Data API v3
1. Go to **[API Library](https://console.cloud.google.com/apis/library)**
2. Search for **"YouTube Data API v3"**
3. Click on it → Click **"Enable"**

#### c. Configure OAuth Consent Screen
1. Go to **[OAuth Consent Screen](https://console.cloud.google.com/apis/credentials/consent)**
2. Select **"External"** → Click **Create**
3. Fill in:
   - App name: `YouTube News Automation`
   - User support email: your email
   - Developer email: your email
4. Click **Save and Continue** through all steps
5. Under **"Test users"**, add your Gmail address

#### d. Create OAuth 2.0 Credentials
1. Go to **[Credentials](https://console.cloud.google.com/apis/credentials)**
2. Click **"+ Create Credentials"** → **"OAuth client ID"**
3. Application type: **"Desktop app"**
4. Name: `YouTube Uploader`
5. Click **Create**
6. Click **"Download JSON"** ⬇️
7. **Rename** the downloaded file to `client_secrets.json`
8. **Move** it to the `youtube-automation` folder

#### e. YouTube API Quotas (Important!)
- Free tier: **10,000 units/day**
- Each video upload costs ~1,600 units
- 6 videos/day = ~9,600 units ✅ (fits within free tier)
- Quota resets at **midnight Pacific Time**

### Step 7: Configure API Keys

Edit `config.py` and add your keys:

```python
GEMINI_API_KEY = "AIzaSy..."        # From Step 4
PEXELS_API_KEY = "your-pexels-key"  # From Step 5
YOUTUBE_CLIENT_SECRETS = "client_secrets.json"  # From Step 6
```

### Step 8: Download Kannada Font

For Kannada text overlays in videos and thumbnails:

1. Go to **[Google Fonts – Noto Sans Kannada](https://fonts.google.com/noto/specimen/Noto+Sans+Kannada)**
2. Click **"Download family"**
3. Extract the ZIP
4. Copy `NotoSansKannada-Regular.ttf` to the `assets/fonts/` folder

```
youtube-automation/
└── assets/
    └── fonts/
        └── NotoSansKannada-Regular.ttf
```

### Step 9: Test YouTube Authentication

Run this to verify your OAuth setup (no video uploaded):

```bash
python youtube_uploader.py
```

- A browser window will open → sign in and authorize
- You should see: `✅ Authentication successful!`
- A `token.pickle` file is created (no re-auth needed next time)

### Step 10: Test the Full Pipeline

```bash
# Dry run (creates video but doesn't upload)
python main.py --slot 1 --test
```

Check the `output/` folder for the generated video and thumbnail.

### Step 11: Set Up Daily Scheduler

```bash
# Right-click scheduler.bat → "Run as Administrator"
scheduler.bat
```

This creates 6 Windows Scheduled Tasks that run automatically every day.

> ⚠️ **Important**: Edit `scheduler.bat` first to update `PYTHON_PATH` if your Python is installed elsewhere. Run `where python` to find the path.

---

## 📖 Usage

### Command Line Options

```bash
# Run a specific slot (1-6)
python main.py --slot 1

# Run with dry-run (no upload)
python main.py --slot 1 --test

# Run all 6 slots
python main.py --all

# Dry-run all slots
python main.py --all --test

# Just scrape news (no video)
python main.py --scrape-only

# Scrape + generate script only
python main.py --script-only 2
```

### Daily Schedule

| Slot | Pipeline Trigger | Video Publishes | Content Focus |
|------|-----------------|-----------------|---------------|
| 1    | 5:30 AM         | 8:00 AM         | Morning news  |
| 2    | 8:30 AM         | 11:00 AM        | Mid-morning   |
| 3    | 11:00 AM        | 1:30 PM         | Afternoon     |
| 4    | 2:30 PM         | 5:00 PM         | Evening       |
| 5    | 5:30 PM         | 8:00 PM         | Prime-time    |
| 6    | 8:00 PM         | 10:30 PM        | Night wrap-up |

---

## 🔧 Troubleshooting

### "client_secrets.json not found"
- Download from Google Cloud Console → Credentials → OAuth 2.0 Client
- Must be named exactly `client_secrets.json`
- Must be in the `youtube-automation/` root folder

### "Token refresh failed"
- Delete `token.pickle` and re-run `python youtube_uploader.py`
- Re-authorize in the browser when prompted

### "FFmpeg not found"
- Ensure FFmpeg is in your system PATH
- Test: open CMD and type `ffmpeg -version`
- If not found, re-do Step 3 and open a **new** terminal

### "Quota exceeded" (YouTube API)
- Free limit: 10,000 units/day
- Each upload ≈ 1,600 units; 6 videos = ~9,600
- Quota resets at midnight Pacific Time
- Wait until tomorrow and retry

### "No articles scraped"
- Check your internet connection
- RSS feed URLs in `config.py` may have changed — verify them in a browser
- Some feeds may be temporarily down; the pipeline will retry next slot

### Video has no audio / black screen
- Ensure `ffmpeg` is working: `ffmpeg -version`
- Check `logs/pipeline_YYYY-MM-DD.log` for detailed error messages
- Try: `python main.py --slot 1 --test` to debug without uploading

### Scheduled tasks not running
- Open Task Scheduler (`taskschd.msc`) and check task status
- Ensure your PC is on and not in sleep mode at trigger times
- Check "History" tab in Task Scheduler for errors
- Verify the Python path in `scheduler.bat` is correct

---

## 💰 Cost Breakdown

| Service | Free Tier | Our Usage | Cost |
|---------|-----------|-----------|------|
| **Gemini AI** | 15 req/min, 1M tokens/day | ~12 req/day | ₹0 |
| **Pexels** | 200 req/hour | ~60 req/day | ₹0 |
| **YouTube API** | 10,000 units/day | ~9,600 units/day | ₹0 |
| **gTTS** | Unlimited | 6 audio/day | ₹0 |
| **Total** | — | — | **₹0/month** |

---

## 📁 Project Structure

```
youtube-automation/
│
├── config.py              # 🔧 API keys, RSS feeds, schedule, settings
├── news_scraper.py        # 📰 Scrapes news from RSS feeds
├── script_generator.py    # 📝 Generates scripts using Gemini AI
├── voice_generator.py     # 🎙️ Creates voiceover audio (gTTS)
├── video_assembler.py     # 🎬 Assembles video with FFmpeg
├── thumbnail_maker.py     # 🖼️ Creates thumbnails with Pillow
├── youtube_uploader.py    # 📤 Uploads to YouTube (OAuth 2.0)
├── main.py                # 🚀 Master orchestrator (CLI)
├── scheduler.bat          # ⏰ Windows Task Scheduler setup
│
├── requirements.txt       # 📦 Python dependencies
├── client_secrets.json    # 🔑 YouTube OAuth credentials (you create)
├── token.pickle           # 🔑 Cached auth token (auto-created)
├── README.md              # 📖 This file
│
├── assets/                # 📂 Static assets
│   └── fonts/             #    Kannada & other fonts
│       └── NotoSansKannada-Regular.ttf
│
├── output/                # 📂 Generated videos & thumbnails
│   └── news_2026-06-02_slot1_morning.mp4
│
├── temp/                  # 📂 Temporary files (auto-cleaned)
│
└── logs/                  # 📂 Pipeline logs
    └── pipeline_2026-06-02.log
```

---

## 🔄 How It Works (Technical Flow)

```
1. SCHEDULER triggers main.py --slot N
                │
2. NEWS SCRAPER │ Fetches RSS feeds → parses articles
                │ → Returns: {karnataka: [...], national: [...], ...}
                │
3. SCRIPT GEN   │ Sends articles to Gemini AI
                │ → Returns: {title, script, description, tags, scenes}
                │
4. VOICE GEN    │ Converts script text to audio (gTTS)
                │ → Returns: temp/voiceover.mp3
                │
5. VIDEO ASSEM  │ Downloads Pexels stock footage per scene
                │ + Adds text overlays (headline, Kannada)
                │ + Merges with voiceover audio
                │ → Returns: output/news_YYYY-MM-DD_slotN.mp4
                │
6. THUMB MAKER  │ Creates thumbnail with headline + background
                │ → Returns: output/news_YYYY-MM-DD_slotN.jpg
                │
7. YT UPLOADER  │ Authenticates (OAuth 2.0)
                │ + Uploads video (resumable, chunked)
                │ + Sets thumbnail
                │ + Schedules publish time
                │ → Returns: {video_id, url}
                │
8. CLEANUP      │ Removes temp files, logs summary
```

---

## 📜 License

MIT License – free to use, modify, and distribute.

---

## 🙏 Credits

- **Google Gemini AI** – Script generation
- **Pexels** – Free stock footage
- **YouTube Data API v3** – Video uploads
- **FFmpeg** – Video processing
- **gTTS** – Text-to-speech

---

*Built with ❤️ for automated news content creation*
