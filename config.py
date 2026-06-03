"""
config.py - Central Configuration for YouTube News Automation Pipeline
======================================================================

This module contains all configuration constants, API key placeholders,
RSS feed URLs, scheduling slots, video/TTS settings, and path definitions
used across the entire pipeline.

Usage:
    import config
    print(config.GEMINI_API_KEY)
    print(config.RSS_FEEDS["karnataka"])
    slot = config.SCHEDULE_SLOTS[0]
    next_pub = config.get_publish_datetime(slot["slot_number"])
"""

import os
import logging
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

# =============================================================================
# API KEYS & CREDENTIALS
# =============================================================================
# Replace these with your actual API keys before running the pipeline.
# In GitHub Actions, these are injected automatically from GitHub Secrets.
# For local use, set environment variables or create a .env file.
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY", "")
YOUTUBE_CLIENT_SECRETS = os.environ.get("YOUTUBE_CLIENT_SECRETS_PATH", "client_secrets.json")

# =============================================================================
# CHANNEL SETTINGS
# =============================================================================
CHANNEL_NAME = "Your Channel Name"
CHANNEL_LANGUAGE = "kn"  # Kannada (ISO 639-1)

# =============================================================================
# GEMINI MODEL
# =============================================================================
GEMINI_MODEL = "gemini-flash-lite-latest"

# =============================================================================
# TIMEZONE — Indian Standard Time (IST) is UTC+05:30
# =============================================================================
IST_OFFSET = timedelta(hours=5, minutes=30)
IST = timezone(IST_OFFSET)

# =============================================================================
# RSS FEEDS
# =============================================================================
# Categorized RSS feed URLs for news scraping.
# Each category maps to a list of feed URLs.
RSS_FEEDS = {
    "karnataka": [
        "https://www.thehindu.com/news/national/karnataka/feeder/default.rss",   # The Hindu - Karnataka
        "https://www.deccanherald.com/rss/karnataka.rss",                         # Deccan Herald - Karnataka
        "https://www.prajavani.net/rss/karnataka-news.xml",                       # Prajavani - Karnataka
    ],
    "national": [
        "https://feeds.feedburner.com/ndtvnews-top-stories",                      # NDTV - Top Stories
        "https://timesofindia.indiatimes.com/rssfeedstopstories.cms",             # Times of India - Top Stories
        "https://www.thehindu.com/news/national/feeder/default.rss",              # The Hindu - National
    ],
    "international": [
        "https://feeds.reuters.com/reuters/topNews",                              # Reuters - Top News
        "https://feeds.bbci.co.uk/news/world/rss.xml",                           # BBC - World News
        "https://www.aljazeera.com/xml/rss/all.xml",                              # Al Jazeera - All News
    ],
}

# =============================================================================
# SCHEDULE SLOTS
# =============================================================================
# 6 daily video upload slots with Kannada title templates and content focus.
SCHEDULE_SLOTS = [
    {
        "slot_number": 1,
        "name": "morning",
        "publish_time_ist": "08:00",
        "video_title_template": "ಬೆಳಗಿನ ಸುದ್ದಿ ಬುಲೆಟಿನ್ | {date}",
        "content_focus": "Morning roundup — overnight developments, early-morning breaking news, and the day's top stories across Karnataka, national, and international categories.",
    },
    {
        "slot_number": 2,
        "name": "mid_morning",
        "publish_time_ist": "11:00",
        "video_title_template": "ಮಧ್ಯಾಹ್ನ ಅಪ್ಡೇಟ್ | {date}",
        "content_focus": "Breaking developments — mid-morning updates on fast-moving stories, market reactions, government announcements, and emerging news.",
    },
    {
        "slot_number": 3,
        "name": "afternoon",
        "publish_time_ist": "13:30",
        "video_title_template": "ಮಧ್ಯಾಹ್ನ ಸುದ್ದಿ | {date}",
        "content_focus": "Deep dive analysis — detailed coverage of the day's most significant stories with expert context, background information, and implications.",
    },
    {
        "slot_number": 4,
        "name": "evening",
        "publish_time_ist": "17:00",
        "video_title_template": "ಸಂಜೆ ಸುದ್ದಿ | {date}",
        "content_focus": "Evening catch-up — afternoon developments, political updates, sports highlights, and stories for the evening audience.",
    },
    {
        "slot_number": 5,
        "name": "prime_time",
        "publish_time_ist": "20:00",
        "video_title_template": "ಪ್ರೈಮ್ ಟೈಮ್ ಬುಲೆಟಿನ್ | {date}",
        "content_focus": "Prime time flagship — the most comprehensive bulletin of the day with all major stories, exclusive analysis, and viewer engagement segments.",
    },
    {
        "slot_number": 6,
        "name": "night",
        "publish_time_ist": "22:30",
        "video_title_template": "ದಿನದ ಸಾರಾಂಶ | {date}",
        "content_focus": "Night recap — complete summary of the day's events, tomorrow's outlook, and any late-breaking stories.",
    },
]

# =============================================================================
# VIDEO SETTINGS
# =============================================================================
VIDEO_SETTINGS = {
    "width": 1920,
    "height": 1080,
    "fps": 30,
    "target_duration_minutes": 10,
    "background_music_volume": 0.15,
}

# =============================================================================
# TTS (Text-to-Speech) SETTINGS
# =============================================================================
TTS_SETTINGS = {
    "voice_kannada": "kn-IN-GaganNeural",     # Microsoft Edge TTS Kannada voice
    "voice_english": "en-IN-PrabhatNeural",    # Microsoft Edge TTS English (India) voice
    "rate": "+0%",                              # Speech rate adjustment
    "volume": "+0%",                            # Volume adjustment
}

# =============================================================================
# FILE PATHS
# =============================================================================
PATHS = {
    "output": "output/",
    "assets": "assets/",
    "fonts": "assets/fonts/",
    "music": "assets/music/",
    "temp": "temp/",
    "thumbnails": "output/thumbnails/",
}


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def get_publish_datetime(slot_number: int) -> datetime:
    """
    Calculate the next publish datetime in UTC for a given slot number.

    The function determines when the next occurrence of the slot's publish
    time will be. If today's slot time has already passed (in IST), the
    publish is scheduled for the same time tomorrow.

    Args:
        slot_number: The slot number (1-6) as defined in SCHEDULE_SLOTS.

    Returns:
        A timezone-aware datetime object in UTC representing the next
        publish time for the given slot.

    Raises:
        ValueError: If slot_number is not between 1 and 6 (inclusive).

    Example:
        >>> from config import get_publish_datetime
        >>> utc_time = get_publish_datetime(1)  # Next 08:00 AM IST in UTC
        >>> print(utc_time.isoformat())
        2026-06-03T02:30:00+00:00
    """
    # Validate slot number
    slot = None
    for s in SCHEDULE_SLOTS:
        if s["slot_number"] == slot_number:
            slot = s
            break

    if slot is None:
        raise ValueError(
            f"Invalid slot_number={slot_number}. Must be between 1 and 6."
        )

    # Parse the publish time (HH:MM) from the slot configuration
    time_parts = slot["publish_time_ist"].split(":")
    publish_hour = int(time_parts[0])
    publish_minute = int(time_parts[1])

    # Get the current time in IST
    now_ist = datetime.now(IST)

    # Build today's publish time in IST
    publish_ist = now_ist.replace(
        hour=publish_hour,
        minute=publish_minute,
        second=0,
        microsecond=0,
    )

    # If the slot time has already passed today, schedule for tomorrow
    if publish_ist <= now_ist:
        publish_ist += timedelta(days=1)
        logger.debug(
            "Slot %d time %s IST already passed today; scheduling for tomorrow.",
            slot_number,
            slot["publish_time_ist"],
        )

    # Convert IST to UTC
    publish_utc = publish_ist.astimezone(timezone.utc)

    logger.info(
        "Slot %d (%s) next publish: %s IST → %s UTC",
        slot_number,
        slot["name"],
        publish_ist.strftime("%Y-%m-%d %H:%M %Z"),
        publish_utc.strftime("%Y-%m-%d %H:%M %Z"),
    )

    return publish_utc


# =============================================================================
# MODULE SELF-TEST
# =============================================================================
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG, format="%(levelname)s | %(message)s")

    print("=" * 60)
    print("YouTube News Automation — Configuration Summary")
    print("=" * 60)

    print(f"\nChannel Name : {CHANNEL_NAME}")
    print(f"Language     : {CHANNEL_LANGUAGE}")
    print(f"Gemini Model : {GEMINI_MODEL}")

    print(f"\nRSS Feed Categories: {list(RSS_FEEDS.keys())}")
    for cat, feeds in RSS_FEEDS.items():
        print(f"  {cat}: {len(feeds)} feeds")

    print(f"\nSchedule Slots ({len(SCHEDULE_SLOTS)}):")
    for slot in SCHEDULE_SLOTS:
        utc_time = get_publish_datetime(slot["slot_number"])
        print(
            f"  Slot {slot['slot_number']}: {slot['publish_time_ist']} IST "
            f"({slot['name']}) → {utc_time.strftime('%H:%M UTC')}"
        )

    print(f"\nVideo Settings: {VIDEO_SETTINGS}")
    print(f"TTS Settings : {TTS_SETTINGS}")
    print(f"Paths        : {PATHS}")
