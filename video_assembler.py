"""
video_assembler.py - Video Assembly Pipeline using FFmpeg

Assembles final news videos by combining:
    - B-roll footage from Pexels (free stock videos)
    - Audio narration (from voice_generator.py)
    - Title cards with Kannada text
    - Lower-third headline overlays
    - Background music mixing
    - Burned-in subtitles

All video processing uses FFmpeg via subprocess — completely free
and open source. No paid video editing APIs required.

Dependencies:
    - FFmpeg (must be installed and on PATH)
    - requests (pip install requests)
"""

import subprocess
import os
import json
import requests
import logging
import random
import tempfile
import shutil
import glob

try:
    import config
except ImportError:
    config = None

# ─── Logging Setup ───────────────────────────────────────────────────────────
logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

# ─── Default Settings ────────────────────────────────────────────────────────
DEFAULT_VIDEO_SETTINGS = {
    "width": 1920,
    "height": 1080,
    "fps": 30,
    "bitrate": "5M",
    "format": "mp4",
}

DEFAULT_PATHS = {
    "output": "output/",
    "assets": "assets/",
    "temp": "temp/",
    "broll": "temp/broll/",
    "fonts": "assets/fonts/",
}

# Kannada font — try Noto Sans Kannada first, then fallback options
KANNADA_FONTS = [
    "NotoSansKannada-Bold.ttf",
    "NotoSansKannada-Regular.ttf",
    "Noto Sans Kannada",
    "Tunga",
    "Arial",
]


class BRollDownloader:
    """
    Downloads free stock B-roll video clips from Pexels API.

    Pexels provides a generous free API with high-quality stock footage
    perfect for news video backgrounds.

    Usage:
        >>> downloader = BRollDownloader(api_key="your_pexels_key")
        >>> urls = downloader.search_videos("rain storm india", count=3)
        >>> downloader.download_video(urls[0], "temp/broll/clip1.mp4")
    """

    PEXELS_VIDEO_SEARCH_URL = "https://api.pexels.com/videos/search"

    def __init__(self, api_key: str):
        """
        Initialize with Pexels API key.

        Args:
            api_key: Your Pexels API key (get free at pexels.com/api).
        """
        if not api_key:
            logger.warning("Pexels API key not provided. B-roll download will fail.")
        self.api_key = api_key
        self.session = requests.Session()
        self.session.headers.update({"Authorization": self.api_key})

    def search_videos(self, query: str, count: int = 3) -> list:
        """
        Search Pexels for stock videos matching a query.

        Args:
            query: Search keywords (e.g., "rain india city").
            count: Number of videos to retrieve (max ~15 per page).

        Returns:
            List of dicts with keys: 'url', 'width', 'height', 'duration'.
            Returns empty list on failure.
        """
        if not self.api_key:
            logger.error("Cannot search videos: no Pexels API key.")
            return []

        try:
            params = {
                "query": query,
                "per_page": count,
                "size": "medium",
                "orientation": "landscape",
            }

            logger.info("Searching Pexels for: '%s' (count=%d)", query, count)
            response = self.session.get(
                self.PEXELS_VIDEO_SEARCH_URL, params=params, timeout=15
            )
            response.raise_for_status()

            data = response.json()
            videos = data.get("videos", [])

            results = []
            for video in videos:
                # Extract the best HD video file
                video_files = video.get("video_files", [])
                hd_file = self._get_best_video_file(video_files)

                if hd_file:
                    results.append({
                        "url": hd_file["link"],
                        "width": hd_file.get("width", 1920),
                        "height": hd_file.get("height", 1080),
                        "duration": video.get("duration", 10),
                    })

            logger.info("Found %d B-roll clips for '%s'", len(results), query)
            return results

        except requests.exceptions.RequestException as e:
            logger.error("Pexels API request failed: %s", str(e))
            return []
        except (json.JSONDecodeError, KeyError) as e:
            logger.error("Failed to parse Pexels response: %s", str(e))
            return []

    @staticmethod
    def _get_best_video_file(video_files: list) -> dict:
        """
        Select the best quality video file, preferring HD (1920x1080).

        Args:
            video_files: List of video file dicts from Pexels API.

        Returns:
            Best matching video file dict, or None.
        """
        if not video_files:
            return None

        # Sort by width descending, prefer files close to 1920
        suitable = [
            f for f in video_files
            if f.get("width", 0) >= 1280 and f.get("file_type") == "video/mp4"
        ]

        if suitable:
            # Pick the one closest to 1920 width
            suitable.sort(key=lambda f: abs(f.get("width", 0) - 1920))
            return suitable[0]

        # Fallback: just pick the largest MP4
        mp4_files = [f for f in video_files if f.get("file_type") == "video/mp4"]
        if mp4_files:
            mp4_files.sort(key=lambda f: f.get("width", 0), reverse=True)
            return mp4_files[0]

        # Last resort: any file
        return video_files[0] if video_files else None

    def download_video(self, url: str, save_path: str) -> str:
        """
        Download a video file from URL.

        Args:
            url: Direct URL to the video file.
            save_path: Local path to save the downloaded video.

        Returns:
            Absolute path to the saved file.

        Raises:
            IOError: If download fails.
        """
        os.makedirs(os.path.dirname(save_path) or ".", exist_ok=True)

        logger.info("Downloading B-roll: %s", url[:80])
        try:
            response = self.session.get(url, stream=True, timeout=60)
            response.raise_for_status()

            with open(save_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)

            file_size_mb = os.path.getsize(save_path) / (1024 * 1024)
            logger.info("Downloaded: %s (%.1f MB)", save_path, file_size_mb)
            return os.path.abspath(save_path)

        except Exception as e:
            logger.error("Download failed for %s: %s", url[:60], str(e))
            raise IOError(f"Failed to download video: {e}") from e

    def get_broll_for_section(
        self, keywords: list, output_dir: str, count: int = 2
    ) -> list:
        """
        Download B-roll clips for a list of keywords.

        Searches for each keyword and downloads matching clips.

        Args:
            keywords: List of search terms (e.g., ["rain", "flooding"]).
            output_dir: Directory to save downloaded clips.
            count: Number of clips to download per keyword.

        Returns:
            List of absolute file paths to downloaded clips.
        """
        os.makedirs(output_dir, exist_ok=True)
        downloaded = []

        for i, keyword in enumerate(keywords):
            videos = self.search_videos(keyword, count=count)

            for j, video in enumerate(videos):
                filename = f"broll_{i}_{j}_{keyword.replace(' ', '_')[:20]}.mp4"
                save_path = os.path.join(output_dir, filename)

                try:
                    path = self.download_video(video["url"], save_path)
                    downloaded.append(path)
                except IOError:
                    logger.warning("Skipping failed download for keyword: %s", keyword)
                    continue

        logger.info(
            "Downloaded %d B-roll clips for %d keywords",
            len(downloaded),
            len(keywords),
        )
        return downloaded


class VideoAssembler:
    """
    Assembles final news videos using FFmpeg.

    Combines B-roll footage, audio narration, title cards, subtitles,
    and background music into a polished YouTube-ready video.

    Usage:
        >>> assembler = VideoAssembler()
        >>> final_path = assembler.assemble_video(
        ...     audio_path="output/narration.mp3",
        ...     script_data={"title": "...", "sections": [...]},
        ...     output_path="output/final_video.mp4"
        ... )
    """

    def __init__(self):
        """Initialize VideoAssembler with paths and settings from config."""
        # Load settings
        if config and hasattr(config, "VIDEO_SETTINGS"):
            self.video_settings = config.VIDEO_SETTINGS
        else:
            self.video_settings = DEFAULT_VIDEO_SETTINGS

        if config and hasattr(config, "PATHS"):
            self.paths = config.PATHS
        else:
            self.paths = DEFAULT_PATHS

        self.width = self.video_settings.get("width", 1920)
        self.height = self.video_settings.get("height", 1080)
        self.fps = self.video_settings.get("fps", 30)
        self.bitrate = self.video_settings.get("bitrate", "5M")

        # Pexels API key for B-roll
        pexels_key = ""
        if config and hasattr(config, "PEXELS_API_KEY"):
            pexels_key = config.PEXELS_API_KEY
        self.broll_downloader = BRollDownloader(api_key=pexels_key)

        # Channel name for watermark
        self.channel_name = ""
        if config and hasattr(config, "CHANNEL_NAME"):
            self.channel_name = config.CHANNEL_NAME

        # Temp directory for intermediate files
        self.temp_dir = self.paths.get("temp", "temp/")
        os.makedirs(self.temp_dir, exist_ok=True)

        # Check FFmpeg availability
        self._check_ffmpeg()

        logger.info(
            "VideoAssembler initialized: %dx%d @ %dfps",
            self.width, self.height, self.fps,
        )

    def _check_ffmpeg(self):
        """
        Verify that FFmpeg and ffprobe are installed and accessible.

        Raises:
            EnvironmentError: If FFmpeg is not found on PATH.
        """
        for tool in ("ffmpeg", "ffprobe"):
            try:
                result = subprocess.run(
                    [tool, "-version"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                version_line = result.stdout.split("\n")[0] if result.stdout else "unknown"
                logger.info("%s found: %s", tool, version_line.strip())
            except FileNotFoundError:
                error_msg = (
                    f"{tool} not found! Please install FFmpeg:\n"
                    f"  Windows: winget install FFmpeg\n"
                    f"  Mac:     brew install ffmpeg\n"
                    f"  Linux:   sudo apt install ffmpeg\n"
                    f"  Or download from: https://ffmpeg.org/download.html"
                )
                logger.error(error_msg)
                raise EnvironmentError(error_msg)
            except subprocess.TimeoutExpired:
                logger.warning("%s check timed out, proceeding anyway.", tool)

    def assemble(
        self,
        audio_path: str,
        script_data: dict,
        output_path: str,
        subtitle_path: str = None,
    ) -> str:
        """Alias for assemble_video to ensure compatibility with master orchestrator."""
        return self.assemble_video(
            audio_path=audio_path,
            script_data=script_data,
            output_path=output_path,
            subtitle_path=subtitle_path,
        )

    def assemble_video(
        self,
        audio_path: str,
        script_data: dict,
        output_path: str,
        subtitle_path: str = None,
    ) -> str:
        """
        Assemble the final video from all components.

        This is the main orchestration method that combines all elements
        into a finished, YouTube-ready video.

        Args:
            audio_path: Path to the narration audio (MP3).
            script_data: Dict with keys:
                - 'title': str, video title
                - 'sections': list of dicts, each with:
                    - 'headline': str
                    - 'broll_keywords': list of str
                    - 'duration': float (seconds, optional)
            output_path: Path for the final output MP4.
            subtitle_path: Optional path to SRT subtitle file.

        Returns:
            Absolute path to the final assembled video.

        Raises:
            FileNotFoundError: If audio file doesn't exist.
            RuntimeError: If FFmpeg processing fails.
        """
        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

        # Create a unique temp directory for this assembly
        assembly_temp = os.path.join(self.temp_dir, f"assembly_{os.getpid()}")
        os.makedirs(assembly_temp, exist_ok=True)

        try:
            # ── Step 1: Get audio duration ────────────────────────────────
            total_duration = self._get_audio_duration(audio_path)
            logger.info("Audio duration: %.1f seconds", total_duration)

            sections = script_data.get("sections", [])
            title = script_data.get("title", "News Update")

            # ── Step 2: Download B-roll clips ─────────────────────────────
            all_broll = []
            broll_dir = os.path.join(assembly_temp, "broll")
            os.makedirs(broll_dir, exist_ok=True)

            for i, section in enumerate(sections):
                keywords = section.get("broll_keywords", [])
                if keywords:
                    clips = self.broll_downloader.get_broll_for_section(
                        keywords, broll_dir, count=2
                    )
                    all_broll.extend(clips)

            # ── Step 3: Create visual track ───────────────────────────────
            if all_broll:
                # Concatenate B-roll and loop to match audio duration
                concat_path = os.path.join(assembly_temp, "broll_concat.mp4")
                self._concat_videos(all_broll, concat_path)

                video_base = os.path.join(assembly_temp, "video_base.mp4")
                self._loop_video_to_duration(concat_path, total_duration, video_base)
            else:
                # No B-roll: create solid color background with title text
                logger.warning("No B-roll available. Creating solid background.")
                video_base = os.path.join(assembly_temp, "video_base.mp4")
                self._create_title_card(title, total_duration, video_base)

            # ── Step 4: Create section title cards ────────────────────────
            title_cards = []
            for i, section in enumerate(sections):
                headline = section.get("headline", f"Section {i + 1}")
                card_duration = min(4.0, total_duration / max(len(sections), 1))
                card_path = os.path.join(assembly_temp, f"title_card_{i}.mp4")
                self._create_title_card(headline, card_duration, card_path)
                title_cards.append(card_path)

            # ── Step 5: Overlay audio narration ───────────────────────────
            video_with_audio = os.path.join(assembly_temp, "with_audio.mp4")
            cmd = [
                "ffmpeg", "-y",
                "-i", video_base,
                "-i", audio_path,
                "-c:v", "libx264",
                "-c:a", "aac",
                "-b:a", "192k",
                "-shortest",
                "-movflags", "+faststart",
                video_with_audio,
            ]
            self._run_ffmpeg(cmd, "overlay audio")
            current_video = video_with_audio

            # ── Step 6: Add lower-third overlays for headlines ────────────
            if sections:
                time_per_section = total_duration / len(sections)
                for i, section in enumerate(sections):
                    headline = section.get("headline", "")
                    if headline:
                        lt_output = os.path.join(
                            assembly_temp, f"lower_third_{i}.mp4"
                        )
                        start_time = i * time_per_section + 1.0  # 1s delay
                        duration = min(5.0, time_per_section - 2.0)
                        if duration > 1.0:
                            self._add_lower_third(
                                current_video, headline,
                                start_time, duration, lt_output
                            )
                            current_video = lt_output

            # ── Step 7: Add background music (if available) ───────────────
            music_path = os.path.join(
                self.paths.get("assets", "assets/"), "background_music.mp3"
            )
            if os.path.exists(music_path):
                music_output = os.path.join(assembly_temp, "with_music.mp4")
                self._mix_audio(current_video, music_path, music_output, 0.15)
                current_video = music_output
            else:
                logger.info("No background music found at: %s (skipping)", music_path)

            # ── Step 8: Add subtitles (if provided) ───────────────────────
            if subtitle_path and os.path.exists(subtitle_path):
                sub_output = os.path.join(assembly_temp, "with_subs.mp4")
                self._add_subtitles(current_video, subtitle_path, sub_output)
                current_video = sub_output

            # ── Step 9: Final output copy ─────────────────────────────────
            if current_video != output_path:
                shutil.copy2(current_video, output_path)

            logger.info("✓ Final video assembled: %s", output_path)
            return os.path.abspath(output_path)

        finally:
            # ── Cleanup temp files ────────────────────────────────────────
            try:
                shutil.rmtree(assembly_temp, ignore_errors=True)
                logger.info("Cleaned up temp directory: %s", assembly_temp)
            except Exception as e:
                logger.warning("Failed to cleanup temp files: %s", str(e))

    def _create_title_card(
        self, text: str, duration: float, output_path: str
    ) -> str:
        """
        Create a title card video segment with text on a dark gradient background.

        Uses FFmpeg's drawtext filter with Noto Sans Kannada font.

        Args:
            text: Title/headline text (supports Kannada Unicode).
            duration: Duration of the title card in seconds.
            output_path: Path to save the title card video.

        Returns:
            Path to the created title card video.
        """
        # Find a suitable font
        font_file = self._find_font()
        font_opt = f":fontfile='{font_file}'" if font_file else ""

        # Escape special characters for FFmpeg drawtext filter
        escaped_text = self._escape_ffmpeg_text(text)

        # Build FFmpeg command for gradient background + centered text
        # Using color source + drawtext filter
        cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi",
            "-i", (
                f"color=c=#0a0a2e:s={self.width}x{self.height}:d={duration}:r={self.fps},"
                f"format=yuv420p"
            ),
            "-vf", (
                # Dark gradient overlay using geq filter
                f"geq=r='clip(p(X,Y)*0.7 + X*0.02, 0, 255)'"
                f":g='clip(p(X,Y)*0.5, 0, 255)'"
                f":b='clip(p(X,Y)*0.9 - X*0.01, 0, 255)',"
                # Main title text
                f"drawtext=text='{escaped_text}'"
                f"{font_opt}"
                f":fontsize=56"
                f":fontcolor=white"
                f":shadowcolor=black"
                f":shadowx=3:shadowy=3"
                f":x=(w-text_w)/2"
                f":y=(h-text_h)/2"
                f":line_spacing=10"
            ),
            "-c:v", "libx264",
            "-preset", "fast",
            "-t", str(duration),
            "-pix_fmt", "yuv420p",
            output_path,
        ]

        self._run_ffmpeg(cmd, f"title card: {text[:30]}")
        return output_path

    def _get_audio_duration(self, audio_path: str) -> float:
        """
        Get the duration of an audio file in seconds using ffprobe.

        Args:
            audio_path: Path to the audio file.

        Returns:
            Duration in seconds.

        Raises:
            RuntimeError: If ffprobe fails to read the file.
        """
        cmd = [
            "ffprobe",
            "-v", "quiet",
            "-show_entries", "format=duration",
            "-of", "json",
            audio_path,
        ]

        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=15
            )
            data = json.loads(result.stdout)
            duration = float(data["format"]["duration"])
            logger.info("Audio duration: %.2fs (%s)", duration, audio_path)
            return duration
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.error("Failed to get audio duration: %s", str(e))
            raise RuntimeError(f"Cannot determine audio duration: {e}") from e
        except subprocess.TimeoutExpired:
            raise RuntimeError("ffprobe timed out reading audio file.")

    def _loop_video_to_duration(
        self, video_path: str, target_duration: float, output_path: str
    ) -> str:
        """
        Loop or trim a video to match a target duration.

        If the video is shorter than target, it loops; if longer, it trims.

        Args:
            video_path: Source video to loop/trim.
            target_duration: Desired duration in seconds.
            output_path: Path for the output video.

        Returns:
            Path to the output video.
        """
        cmd = [
            "ffmpeg", "-y",
            "-stream_loop", "-1",          # Infinite loop
            "-i", video_path,
            "-t", str(target_duration),    # Trim to target duration
            "-vf", f"scale={self.width}:{self.height}:force_original_aspect_ratio=decrease,"
                   f"pad={self.width}:{self.height}:(ow-iw)/2:(oh-ih)/2:black",
            "-c:v", "libx264",
            "-preset", "fast",
            "-an",                         # Remove audio from B-roll
            "-pix_fmt", "yuv420p",
            output_path,
        ]

        self._run_ffmpeg(cmd, f"loop video to {target_duration:.1f}s")
        return output_path

    def _concat_videos(self, video_list: list, output_path: str) -> str:
        """
        Concatenate multiple video files using FFmpeg concat demuxer.

        Args:
            video_list: List of video file paths to concatenate.
            output_path: Path for the concatenated output.

        Returns:
            Path to the concatenated video.

        Raises:
            ValueError: If video_list is empty.
        """
        if not video_list:
            raise ValueError("Cannot concatenate empty video list.")

        # Create concat list file
        concat_file = output_path + ".concat.txt"
        with open(concat_file, "w", encoding="utf-8") as f:
            for video_path in video_list:
                # Escape single quotes and backslashes for FFmpeg concat format
                safe_path = os.path.abspath(video_path).replace("\\", "/").replace("'", "'\\''")
                f.write(f"file '{safe_path}'\n")

        # First, normalize all videos to same resolution/fps
        normalized = []
        norm_dir = os.path.dirname(output_path)
        for i, vpath in enumerate(video_list):
            norm_path = os.path.join(norm_dir, f"norm_{i}.mp4")
            norm_cmd = [
                "ffmpeg", "-y",
                "-i", vpath,
                "-vf", (
                    f"scale={self.width}:{self.height}"
                    f":force_original_aspect_ratio=decrease,"
                    f"pad={self.width}:{self.height}:(ow-iw)/2:(oh-ih)/2:black,"
                    f"fps={self.fps},setsar=1"
                ),
                "-c:v", "libx264",
                "-preset", "fast",
                "-an",
                "-pix_fmt", "yuv420p",
                "-t", "15",  # Cap each clip to 15 seconds
                norm_path,
            ]
            try:
                self._run_ffmpeg(norm_cmd, f"normalize clip {i}")
                normalized.append(norm_path)
            except RuntimeError:
                logger.warning("Skipping clip that failed normalization: %s", vpath)

        if not normalized:
            raise RuntimeError("All video clips failed normalization.")

        # Rewrite concat file with normalized clips
        with open(concat_file, "w", encoding="utf-8") as f:
            for npath in normalized:
                safe_path = os.path.abspath(npath).replace("\\", "/").replace("'", "'\\''")
                f.write(f"file '{safe_path}'\n")

        # Concatenate using concat demuxer
        cmd = [
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", concat_file,
            "-c:v", "libx264",
            "-preset", "fast",
            "-pix_fmt", "yuv420p",
            output_path,
        ]

        self._run_ffmpeg(cmd, "concatenate videos")

        # Cleanup concat file and normalized clips
        try:
            os.remove(concat_file)
            for npath in normalized:
                if os.path.exists(npath):
                    os.remove(npath)
        except OSError:
            pass

        return output_path

    def _add_lower_third(
        self,
        video_path: str,
        text: str,
        start_time: float,
        duration: float,
        output_path: str,
    ) -> str:
        """
        Add a lower-third text overlay banner to the video.

        Creates a semi-transparent bar at the bottom of the frame with
        the headline text, visible for the specified duration.

        Args:
            video_path: Input video path.
            text: Headline text to display.
            start_time: When to show the overlay (seconds).
            duration: How long to show the overlay (seconds).
            output_path: Output video path.

        Returns:
            Path to the output video.
        """
        font_file = self._find_font()
        font_opt = f":fontfile='{font_file}'" if font_file else ""
        escaped_text = self._escape_ffmpeg_text(text)

        end_time = start_time + duration

        # Lower-third: semi-transparent black bar + white text
        drawbox_filter = (
            f"drawbox=x=0:y=ih-120:w=iw:h=120"
            f":color=black@0.7:t=fill"
            f":enable='between(t,{start_time},{end_time})'"
        )
        drawtext_filter = (
            f"drawtext=text='{escaped_text}'"
            f"{font_opt}"
            f":fontsize=36"
            f":fontcolor=white"
            f":x=40"
            f":y=h-90"
            f":shadowcolor=black:shadowx=2:shadowy=2"
            f":enable='between(t,{start_time},{end_time})'"
        )

        cmd = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-vf", f"{drawbox_filter},{drawtext_filter}",
            "-c:v", "libx264",
            "-preset", "fast",
            "-c:a", "copy",
            "-pix_fmt", "yuv420p",
            output_path,
        ]

        self._run_ffmpeg(cmd, f"lower-third: {text[:30]}")
        return output_path

    def _mix_audio(
        self,
        video_path: str,
        music_path: str,
        output_path: str,
        music_volume: float = 0.15,
    ) -> str:
        """
        Mix background music into the video at reduced volume.

        Args:
            video_path: Input video with narration audio.
            music_path: Path to background music file.
            output_path: Output video path.
            music_volume: Volume multiplier for music (0.0 to 1.0).

        Returns:
            Path to the output video.
        """
        cmd = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-i", music_path,
            "-filter_complex", (
                f"[1:a]volume={music_volume},aloop=loop=-1:size=2e+09[music];"
                f"[0:a][music]amix=inputs=2:duration=shortest:dropout_transition=3[aout]"
            ),
            "-map", "0:v",
            "-map", "[aout]",
            "-c:v", "copy",
            "-c:a", "aac",
            "-b:a", "192k",
            "-shortest",
            output_path,
        ]

        self._run_ffmpeg(cmd, "mix background music")
        return output_path

    def _add_subtitles(
        self, video_path: str, srt_path: str, output_path: str
    ) -> str:
        """
        Burn subtitles into the video from an SRT file.

        Args:
            video_path: Input video path.
            srt_path: Path to SRT subtitle file.
            output_path: Output video path.

        Returns:
            Path to the output video.
        """
        # Escape path for FFmpeg subtitles filter (needs forward slashes and escaping)
        safe_srt = srt_path.replace("\\", "/").replace(":", "\\:")

        font_file = self._find_font()
        # Build subtitle style string
        style = "FontSize=22,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,Outline=2"
        if font_file:
            font_name = os.path.splitext(os.path.basename(font_file))[0]
            style += f",FontName={font_name}"

        cmd = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-vf", f"subtitles='{safe_srt}':force_style='{style}'",
            "-c:v", "libx264",
            "-preset", "fast",
            "-c:a", "copy",
            "-pix_fmt", "yuv420p",
            output_path,
        ]

        self._run_ffmpeg(cmd, "burn subtitles")
        return output_path

    # ─── Private Helpers ──────────────────────────────────────────────────────

    def _find_font(self) -> str:
        """
        Find a suitable Kannada-capable font on the system.

        Searches common font directories for Noto Sans Kannada or fallbacks.

        Returns:
            Absolute path to a font file, or empty string if none found.
        """
        # Common font search paths
        font_dirs = [
            self.paths.get("fonts", "assets/fonts/"),
            "C:/Windows/Fonts/",
            "/usr/share/fonts/",
            "/usr/share/fonts/truetype/noto/",
            "/usr/share/fonts/truetype/",
            os.path.expanduser("~/.local/share/fonts/"),
        ]

        for font_dir in font_dirs:
            if not os.path.isdir(font_dir):
                continue
            for font_name in KANNADA_FONTS:
                font_path = os.path.join(font_dir, font_name)
                if os.path.isfile(font_path):
                    logger.info("Found font: %s", font_path)
                    return font_path

        # Search recursively in Windows fonts
        if os.path.isdir("C:/Windows/Fonts/"):
            for font_name in KANNADA_FONTS:
                matches = glob.glob(
                    f"C:/Windows/Fonts/**/{font_name}", recursive=True
                )
                if matches:
                    logger.info("Found font: %s", matches[0])
                    return matches[0]

        logger.warning(
            "No Kannada font found. Text may not render correctly. "
            "Install Noto Sans Kannada: https://fonts.google.com/noto"
        )
        return ""

    @staticmethod
    def _escape_ffmpeg_text(text: str) -> str:
        """
        Escape special characters for FFmpeg drawtext filter.

        FFmpeg's drawtext filter requires certain characters to be escaped.

        Args:
            text: Raw text string.

        Returns:
            Escaped text safe for FFmpeg drawtext filter.
        """
        # Characters that need escaping in FFmpeg drawtext
        text = text.replace("\\", "\\\\")
        text = text.replace("'", "'\\\\\\''")
        text = text.replace("%", "%%")
        text = text.replace(":", "\\:")
        text = text.replace(";", "\\;")
        return text

    @staticmethod
    def _run_ffmpeg(cmd: list, description: str = ""):
        """
        Execute an FFmpeg command with error checking.

        Args:
            cmd: Command list to execute.
            description: Human-readable description for logging.

        Raises:
            RuntimeError: If the command exits with non-zero status.
        """
        logger.info("FFmpeg [%s]: %s", description, " ".join(cmd[:6]) + " ...")

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=600,  # 10 minute timeout
            )

            if result.returncode != 0:
                error_output = result.stderr[-500:] if result.stderr else "No error output"
                logger.error(
                    "FFmpeg [%s] failed (code %d):\n%s",
                    description, result.returncode, error_output,
                )
                raise RuntimeError(
                    f"FFmpeg '{description}' failed with code {result.returncode}: "
                    f"{error_output[:200]}"
                )

            logger.info("FFmpeg [%s] completed successfully.", description)

        except subprocess.TimeoutExpired:
            logger.error("FFmpeg [%s] timed out after 600 seconds.", description)
            raise RuntimeError(f"FFmpeg '{description}' timed out.")
        except FileNotFoundError:
            raise EnvironmentError("FFmpeg not found on PATH. Please install FFmpeg.")


# ─── Main: Test / Demo ───────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("  Video Assembler - FFmpeg Pipeline Demo")
    print("=" * 60)

    # ── Test 1: Check FFmpeg ──────────────────────────────────────────────
    print("\n[Test 1] Checking FFmpeg installation...")
    try:
        assembler = VideoAssembler()
        print("  ✓ FFmpeg is available")
    except EnvironmentError as e:
        print(f"  ✗ FFmpeg not found: {e}")
        exit(1)

    # ── Test 2: Create a title card ───────────────────────────────────────
    print("\n[Test 2] Creating sample title card...")
    os.makedirs("output", exist_ok=True)
    try:
        assembler._create_title_card(
            text="ಇಂದಿನ ಪ್ರಮುಖ ಸುದ್ದಿ",
            duration=5.0,
            output_path="output/test_title_card.mp4",
        )
        print("  ✓ Title card created: output/test_title_card.mp4")
    except Exception as e:
        print(f"  ✗ Error: {e}")

    # ── Test 3: Test B-roll search (requires API key) ─────────────────────
    print("\n[Test 3] Testing Pexels B-roll search...")
    pexels_key = ""
    if config and hasattr(config, "PEXELS_API_KEY"):
        pexels_key = config.PEXELS_API_KEY

    if pexels_key:
        downloader = BRollDownloader(api_key=pexels_key)
        results = downloader.search_videos("india city", count=2)
        print(f"  ✓ Found {len(results)} B-roll clips")
        for r in results:
            print(f"    - {r['url'][:60]}... ({r['duration']}s)")
    else:
        print("  ⊘ Skipped (no Pexels API key configured)")

    # ── Test 4: Full assembly demo (requires audio file) ──────────────────
    print("\n[Test 4] Full assembly test...")
    test_audio = "output/test_voice.mp3"
    if os.path.exists(test_audio):
        try:
            script_data = {
                "title": "ಕರ್ನಾಟಕ ಸುದ್ದಿ",
                "sections": [
                    {
                        "headline": "ಬೆಂಗಳೂರಿನಲ್ಲಿ ಮಳೆ",
                        "broll_keywords": ["rain", "bangalore"],
                        "duration": 10,
                    },
                    {
                        "headline": "ರಾಜಕೀಯ ಬೆಳವಣಿಗೆ",
                        "broll_keywords": ["politics", "government"],
                        "duration": 10,
                    },
                ],
            }
            result = assembler.assemble_video(
                audio_path=test_audio,
                script_data=script_data,
                output_path="output/test_final_video.mp4",
            )
            print(f"  ✓ Video assembled: {result}")
        except Exception as e:
            print(f"  ✗ Error: {e}")
    else:
        print(f"  ⊘ Skipped (run voice_generator.py first to create {test_audio})")

    print("\n" + "=" * 60)
    print("  Demo complete!")
    print("=" * 60)
