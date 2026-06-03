"""
YouTube Video Uploader Module
==============================
Handles video uploads to YouTube using the YouTube Data API v3 (FREE tier).

Features:
- OAuth 2.0 authentication with token persistence (token.pickle)
- Resumable video uploads with progress tracking
- Custom thumbnail upload support
- Scheduled publishing (privacyStatus='private' + publishAt)
- Exponential backoff retry logic (3 retries)
- Quota-aware error handling

Dependencies:
    pip install google-auth google-auth-oauthlib google-api-python-client

Usage:
    # Test authentication only:
    python youtube_uploader.py

    # Programmatic usage:
    uploader = YouTubeUploader()
    result = uploader.upload_video(
        video_path="output/news_video.mp4",
        title="Today's News",
        description="Daily news update",
        tags=["news", "daily"]
    )
    print(result)  # {'video_id': 'abc123', 'url': 'https://youtu.be/abc123'}
"""

import os
import sys
import time
import logging
import pickle
import json
import random
import traceback

import config

from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Only request upload scope – minimal permissions
SCOPES = ['https://www.googleapis.com/auth/youtube.upload']

# Upload chunk size: 10 MB (must be a multiple of 256 KB)
CHUNK_SIZE = 10 * 1024 * 1024  # 10 MB

# Retry configuration
MAX_RETRIES = 3
INITIAL_BACKOFF_SECONDS = 5

# Retriable HTTP status codes (server-side / transient errors)
RETRIABLE_STATUS_CODES = [500, 502, 503, 504]

# Retriable exceptions
RETRIABLE_EXCEPTIONS = (IOError, ConnectionError, TimeoutError)

logger = logging.getLogger(__name__)


class YouTubeUploader:
    """
    Manages YouTube video uploads via the Data API v3.

    Workflow:
        1. Authenticate (OAuth 2.0) → build youtube service object
        2. Upload video with metadata (title, description, tags, etc.)
        3. Optionally set a custom thumbnail
        4. Optionally schedule the publish time

    Token persistence:
        The OAuth token is cached in ``token.pickle`` so subsequent runs
        do not require re-authentication via the browser.
    """

    def __init__(self):
        """Initialize the uploader by authenticating and building the API service."""
        logger.info("Initializing YouTubeUploader...")
        self.credentials = None
        self.youtube = None
        self._authenticate()
        logger.info("YouTubeUploader ready ✓")

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------

    def _authenticate(self):
        """
        Handle the full OAuth 2.0 flow with token caching.

        Steps:
            1. Check for saved ``token.pickle`` – load if present.
            2. If the token is expired but has a refresh token, refresh it.
            3. If no valid token exists, launch the ``InstalledAppFlow``
               (opens a browser window for the user to authorize).
            4. Save the new/refreshed token to ``token.pickle`` for reuse.

        Raises:
            FileNotFoundError: If ``client_secrets.json`` is missing.
            Exception: If the OAuth flow fails for any reason.
        """
        token_path = os.path.join(os.path.dirname(__file__), "token.pickle")
        client_secrets_path = config.YOUTUBE_CLIENT_SECRETS

        # If client_secrets path is relative, resolve against this file's dir
        if not os.path.isabs(client_secrets_path):
            client_secrets_path = os.path.join(
                os.path.dirname(__file__), client_secrets_path
            )

        # ---- Step 1: Try to load cached token ----
        if os.path.exists(token_path):
            try:
                with open(token_path, "rb") as token_file:
                    self.credentials = pickle.load(token_file)
                logger.info("Loaded cached credentials from token.pickle")
            except Exception as exc:
                logger.warning("Could not load token.pickle: %s", exc)
                self.credentials = None

        # ---- Step 2: Refresh expired token ----
        if self.credentials and self.credentials.expired and self.credentials.refresh_token:
            try:
                logger.info("Token expired – refreshing...")
                self.credentials.refresh(Request())
                logger.info("Token refreshed successfully ✓")
            except Exception as exc:
                logger.warning("Token refresh failed: %s – re-authenticating", exc)
                self.credentials = None

        # ---- Step 3: Run full OAuth flow if needed ----
        if not self.credentials or not self.credentials.valid:
            # Check if running in CI/cloud (GitHub Actions sets CI=true)
            is_ci = os.environ.get("CI", "").lower() == "true" or os.environ.get("GITHUB_ACTIONS", "").lower() == "true"

            if is_ci:
                # In CI/cloud: cannot open browser. Token must be pre-provided.
                raise RuntimeError(
                    "YouTube OAuth token is missing or invalid in CI/cloud environment. "
                    "Please re-generate token.pickle locally and update the "
                    "YOUTUBE_TOKEN_PICKLE GitHub Secret."
                )

            if not os.path.exists(client_secrets_path):
                raise FileNotFoundError(
                    f"client_secrets.json not found at '{client_secrets_path}'. "
                    "Download it from the Google Cloud Console → APIs & Services → Credentials."
                )

            logger.info("Starting OAuth 2.0 authorization flow...")
            logger.info("A browser window will open – please authorize the application.")

            flow = InstalledAppFlow.from_client_secrets_file(
                client_secrets_path, SCOPES
            )
            self.credentials = flow.run_local_server(
                port=8080,
                prompt="consent",
                access_type="offline",  # ensures we get a refresh_token
            )
            logger.info("Authorization successful ✓")

        # ---- Step 4: Save token for future runs ----
        try:
            with open(token_path, "wb") as token_file:
                pickle.dump(self.credentials, token_file)
            logger.info("Credentials saved to %s", token_path)
        except Exception as exc:
            logger.warning("Could not save token.pickle: %s", exc)

        # ---- Build the YouTube API service ----
        self.youtube = build("youtube", "v3", credentials=self.credentials)
        logger.info("YouTube API service built successfully ✓")

    # ------------------------------------------------------------------
    # Video Upload
    # ------------------------------------------------------------------

    def upload_video(
        self,
        video_path: str,
        title: str,
        description: str,
        tags: list,
        category_id: str = "25",
        publish_at: str = None,
    ) -> dict:
        """
        Upload a video to YouTube with metadata.

        Args:
            video_path:   Path to the video file (.mp4).
            title:        Video title (max 100 chars).
            description:  Video description (max 5000 chars).
            tags:         List of keyword tags.
            category_id:  YouTube category ID. Default '25' = News & Politics.
            publish_at:   ISO 8601 datetime string for scheduled publishing.
                          Example: '2026-06-03T08:00:00+05:30'
                          If provided, video is uploaded as *private* and auto-
                          published at the given time.

        Returns:
            dict: ``{'video_id': '...', 'url': 'https://youtu.be/...'}``

        Raises:
            FileNotFoundError: If video_path does not exist.
            HttpError: On non-retriable API errors (e.g. quota exceeded).
        """
        # Validate input
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"Video file not found: {video_path}")

        file_size_mb = os.path.getsize(video_path) / (1024 * 1024)
        logger.info("Uploading video: %s (%.1f MB)", video_path, file_size_mb)
        logger.info("Title: %s", title)

        # ---- Build request body ----
        body = {
            "snippet": {
                "title": title[:100],  # YouTube limit
                "description": description[:5000],  # YouTube limit
                "tags": tags[:500] if tags else [],
                "categoryId": category_id,
            },
            "status": {},
        }

        # Scheduling logic
        if publish_at:
            # Handle datetime objects or strings
            publish_at_str = publish_at.isoformat() if hasattr(publish_at, "isoformat") else str(publish_at)
            body["status"]["privacyStatus"] = "private"
            body["status"]["publishAt"] = publish_at_str
            logger.info("Scheduled to publish at: %s (uploading as private)", publish_at_str)
        else:
            body["status"]["privacyStatus"] = "public"
            logger.info("Publishing immediately as public")

        # ---- Media upload (resumable) ----
        media = MediaFileUpload(
            video_path,
            mimetype="video/mp4",
            resumable=True,
            chunksize=CHUNK_SIZE,
        )

        request = self.youtube.videos().insert(
            part="snippet,status",
            body=body,
            media_body=media,
        )

        # ---- Execute with retry logic ----
        response = self._execute_upload_with_retry(request, video_path)

        video_id = response.get("id", "unknown")
        video_url = f"https://youtu.be/{video_id}"

        logger.info("=" * 60)
        logger.info("🎉 UPLOAD SUCCESSFUL!")
        logger.info("   Video ID : %s", video_id)
        logger.info("   URL      : %s", video_url)
        logger.info("=" * 60)

        return {"video_id": video_id, "url": video_url}

    def _execute_upload_with_retry(self, request, video_path: str) -> dict:
        """
        Execute a resumable upload with exponential backoff retries.

        Args:
            request:    The API insert request object.
            video_path: Path to video (for logging).

        Returns:
            dict: The API response on successful upload.

        Raises:
            HttpError: After all retries are exhausted, or on non-retriable errors.
        """
        response = None
        retry_count = 0
        backoff = INITIAL_BACKOFF_SECONDS

        while response is None:
            try:
                # Upload next chunk
                status, response = request.next_chunk()

                if status:
                    progress_pct = int(status.progress() * 100)
                    logger.info(
                        "Upload progress: %d%% (%.1f MB uploaded)",
                        progress_pct,
                        status.resumable_progress / (1024 * 1024),
                    )

            except HttpError as exc:
                if exc.resp.status in RETRIABLE_STATUS_CODES:
                    retry_count += 1
                    if retry_count > MAX_RETRIES:
                        logger.error("Max retries (%d) exceeded. Giving up.", MAX_RETRIES)
                        raise

                    wait_time = backoff + random.random()
                    logger.warning(
                        "HTTP %d error. Retry %d/%d in %.1f seconds...",
                        exc.resp.status,
                        retry_count,
                        MAX_RETRIES,
                        wait_time,
                    )
                    time.sleep(wait_time)
                    backoff *= 2  # exponential backoff

                elif exc.resp.status == 403:
                    # Likely quota exceeded
                    error_detail = json.loads(exc.content.decode("utf-8"))
                    reason = (
                        error_detail.get("error", {})
                        .get("errors", [{}])[0]
                        .get("reason", "unknown")
                    )
                    if reason == "quotaExceeded":
                        logger.error(
                            "❌ YouTube API quota exceeded! "
                            "Daily quota resets at midnight Pacific Time. "
                            "Wait and retry tomorrow."
                        )
                    else:
                        logger.error("❌ Forbidden (403): %s", reason)
                    raise

                else:
                    # Non-retriable HTTP error
                    logger.error("❌ Non-retriable HTTP error %d: %s", exc.resp.status, exc)
                    raise

            except RETRIABLE_EXCEPTIONS as exc:
                retry_count += 1
                if retry_count > MAX_RETRIES:
                    logger.error("Max retries (%d) exceeded after network error.", MAX_RETRIES)
                    raise

                wait_time = backoff + random.random()
                logger.warning(
                    "Network error (%s). Retry %d/%d in %.1f seconds...",
                    type(exc).__name__,
                    retry_count,
                    MAX_RETRIES,
                    wait_time,
                )
                time.sleep(wait_time)
                backoff *= 2

        return response

    # ------------------------------------------------------------------
    # Thumbnail Upload
    # ------------------------------------------------------------------

    def _upload_thumbnail(self, video_id: str, thumbnail_path: str) -> dict:
        """
        Upload a custom thumbnail for a video.

        Args:
            video_id:       The YouTube video ID.
            thumbnail_path: Path to the thumbnail image (JPEG/PNG, <2 MB recommended).

        Returns:
            dict: API response from thumbnails().set().

        Raises:
            FileNotFoundError: If thumbnail_path does not exist.
            HttpError: On API errors (e.g. account not verified for custom thumbnails).

        Note:
            Custom thumbnails require the YouTube account to be verified
            (phone number verification). If not verified, this will raise
            a 403 error.
        """
        if not os.path.exists(thumbnail_path):
            raise FileNotFoundError(f"Thumbnail not found: {thumbnail_path}")

        logger.info("Uploading thumbnail: %s → video %s", thumbnail_path, video_id)

        # Determine mimetype from extension
        ext = os.path.splitext(thumbnail_path)[1].lower()
        mime_map = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png"}
        mimetype = mime_map.get(ext, "image/jpeg")

        media = MediaFileUpload(thumbnail_path, mimetype=mimetype)

        response = (
            self.youtube.thumbnails()
            .set(videoId=video_id, media_body=media)
            .execute()
        )

        logger.info("Thumbnail uploaded successfully ✓")
        return response

    # ------------------------------------------------------------------
    # Combined Upload (Video + Thumbnail)
    # ------------------------------------------------------------------

    def upload_with_thumbnail(
        self,
        video_path: str,
        thumbnail_path: str,
        title: str,
        description: str,
        tags: list,
        category_id: str = "25",
        publish_at: str = None,
    ) -> dict:
        """
        Upload a video and then set its custom thumbnail.

        This is a convenience method that chains ``upload_video()`` and
        ``_upload_thumbnail()``.

        Args:
            video_path:     Path to the video file.
            thumbnail_path: Path to the thumbnail image.
            title:          Video title.
            description:    Video description.
            tags:           List of tags.
            category_id:    YouTube category ID (default '25' = News).
            publish_at:     Optional ISO 8601 scheduled publish time.

        Returns:
            dict: ``{'video_id': '...', 'url': 'https://youtu.be/...', 'thumbnail': True}``
        """
        # Step 1: Upload the video
        result = self.upload_video(
            video_path=video_path,
            title=title,
            description=description,
            tags=tags,
            category_id=category_id,
            publish_at=publish_at,
        )

        # Step 2: Upload the thumbnail
        try:
            self._upload_thumbnail(result["video_id"], thumbnail_path)
            result["thumbnail"] = True
            logger.info("Video + thumbnail upload complete ✓")
        except HttpError as exc:
            logger.error(
                "⚠️ Video uploaded but thumbnail failed: %s. "
                "Make sure your YouTube account is verified for custom thumbnails.",
                exc,
            )
            result["thumbnail"] = False
        except Exception as exc:
            logger.error("⚠️ Thumbnail upload failed with unexpected error: %s", exc)
            result["thumbnail"] = False

        return result


# ---------------------------------------------------------------------------
# Main – Test Authentication
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # Configure logging for standalone testing
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    print("=" * 60)
    print("  YouTube Uploader – Authentication Test")
    print("=" * 60)
    print()
    print("This will test your OAuth 2.0 setup without uploading anything.")
    print("Make sure 'client_secrets.json' is in the project folder.")
    print()

    try:
        uploader = YouTubeUploader()
        print()
        print("✅ Authentication successful!")
        print("   Your token has been saved to 'token.pickle'.")
        print("   Future runs will not require browser authorization.")
        print()

        # Quick API test – get channel info
        try:
            channels = uploader.youtube.channels().list(
                part="snippet", mine=True
            ).execute()
            if channels.get("items"):
                channel_name = channels["items"][0]["snippet"]["title"]
                print(f"   Connected channel: {channel_name}")
            else:
                print("   (Could not retrieve channel info – upload scope only)")
        except Exception:
            print("   (Channel info not available with upload-only scope – this is OK)")

    except FileNotFoundError as exc:
        print(f"\n❌ {exc}")
        print("\nTo fix this:")
        print("  1. Go to https://console.cloud.google.com/")
        print("  2. Create a project and enable YouTube Data API v3")
        print("  3. Create OAuth 2.0 credentials (Desktop App)")
        print("  4. Download the JSON and save as 'client_secrets.json'")

    except Exception as exc:
        print(f"\n❌ Authentication failed: {exc}")
        traceback.print_exc()

    print()
    print("=" * 60)
