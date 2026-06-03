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
import asyncio
from voice_generator import VoiceGenerator

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
        Assemble the final video from all components, ensuring each section's 
        visuals (B-roll) and subtitle overlays exactly match its audio narration.
        """
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

        # Create a unique temp directory for this assembly
        assembly_temp = os.path.join(self.temp_dir, f"assembly_{os.getpid()}")
        os.makedirs(assembly_temp, exist_ok=True)

        try:
            sections = script_data.get("sections", [])
            title = script_data.get("title", "News Update")
            slot_number = script_data.get("slot_number", 1)
            
            logger.info("Starting section-by-section video assembly for slot %d (%d sections)...", slot_number, len(sections))
            
            # Initialize VoiceGenerator for section-level audio/subtitle generation
            voice_gen = VoiceGenerator(language="kannada")
            
            section_videos = []
            
            for i, section in enumerate(sections):
                name = section.get("name", f"section_{i}")
                narration_text = section.get("narration", "").strip()
                headline = section.get("headline", f"Section {i + 1}").strip()
                keywords = section.get("broll_keywords", [])
                
                logger.info("Processing section %d/%d: name=%s, headline='%s'", i+1, len(sections), name, headline)
                
                if not narration_text:
                    logger.warning("Section %d has no narration text. Skipping.", i)
                    continue
                
                # 1. Generate audio and subtitles for this section
                sec_audio_path = os.path.join(assembly_temp, f"sec_audio_{i}.mp3")
                sec_srt_path = os.path.join(assembly_temp, f"sec_audio_{i}.srt")
                
                logger.info("Generating TTS and SRT for section %d...", i)
                asyncio.run(voice_gen.generate_with_subtitles(narration_text, sec_audio_path, sec_srt_path))
                
                # 2. Get the duration of this section's narration
                sec_duration = self._get_audio_duration(sec_audio_path)
                logger.info("Section %d duration: %.2f seconds", i, sec_duration)
                
                # 3. Search and download B-roll for this section
                sec_broll_dir = os.path.join(assembly_temp, f"broll_sec_{i}")
                os.makedirs(sec_broll_dir, exist_ok=True)
                
                clips = []
                if keywords:
                    clips = self.broll_downloader.get_broll_for_section(
                        keywords, sec_broll_dir, count=2
                    )
                
                # 4. Create visual track for this section matching the duration
                sec_video_base = os.path.join(assembly_temp, f"sec_base_{i}.mp4")
                if clips:
                    concat_sec_path = os.path.join(assembly_temp, f"sec_concat_{i}.mp4")
                    self._concat_videos(clips, concat_sec_path)
                    self._loop_video_to_duration(concat_sec_path, sec_duration, sec_video_base)
                else:
                    logger.warning("No B-roll clips downloaded for section %d. Creating title card.", i)
                    self._create_title_card(headline, sec_duration, sec_video_base, slot_number)
                
                current_sec_video = sec_video_base
                
                # 5. Overlay section headline banner (lower-third)
                if headline:
                    lt_output = os.path.join(assembly_temp, f"sec_lt_{i}.mp4")
                    # Display lower-third starting at 0.5s until 0.5s before the section ends
                    start_time = 0.5
                    duration = max(1.0, sec_duration - 1.0)
                    self._add_lower_third(
                        current_sec_video, headline,
                        start_time, duration, lt_output,
                        slot_number
                    )
                    current_sec_video = lt_output
                
                # 6. Burn subtitles into the section video
                if os.path.exists(sec_srt_path):
                    sub_output = os.path.join(assembly_temp, f"sec_subs_{i}.mp4")
                    self._add_subtitles(current_sec_video, sec_srt_path, sub_output)
                    current_sec_video = sub_output
                
                # 7. Merge the section audio narration with the visual track
                sec_final = os.path.join(assembly_temp, f"sec_final_{i}.mp4")
                cmd = [
                    "ffmpeg", "-y",
                    "-i", current_sec_video,
                    "-i", sec_audio_path,
                    "-c:v", "libx264",
                    "-c:a", "aac",
                    "-b:a", "192k",
                    "-shortest",
                    sec_final,
                ]
                self._run_ffmpeg(cmd, f"merge audio for section {i}")
                
                section_videos.append(sec_final)
            
            if not section_videos:
                raise RuntimeError("No section videos were generated.")
            
            # 8. Concatenate all section videos together
            concat_path = os.path.join(assembly_temp, "final_concat_no_music.mp4")
            self._concat_section_videos(section_videos, concat_path)
            
            current_video = concat_path
            
            # 9. Add background music across the entire concatenated video
            slot_music_map = {
                1: "morning_news.mp3",
                2: "crime_thriller.mp3",
                3: "evening_news.mp3",
                4: "viral_entertainment.mp3",
                5: "social_buzz.mp3",
                6: "devotional_stories.mp3",
            }
            music_filename = slot_music_map.get(slot_number, "background_music.mp3")
            music_path = os.path.join(
                self.paths.get("music", "assets/music/"), music_filename
            )
            
            # Fallback chains
            if not os.path.exists(music_path):
                music_path = os.path.join(
                    self.paths.get("music", "assets/music/"), "background_music.mp3"
                )
            if not os.path.exists(music_path):
                music_path = os.path.join(
                    self.paths.get("assets", "assets/"), "background_music.mp3"
                )
                
            if os.path.exists(music_path):
                music_output = os.path.join(assembly_temp, "final_with_music.mp4")
                self._mix_audio(current_video, music_path, music_output, 0.15)
                current_video = music_output
            else:
                logger.info("No background music found at: %s (skipping)", music_path)
            
            # 10. Copy to the final output path
            if current_video != output_path:
                shutil.copy2(current_video, output_path)
            
            logger.info("✓ Final aligned video assembled: %s", output_path)
            return os.path.abspath(output_path)
            
        finally:
            # Cleanup temp files
            try:
                shutil.rmtree(assembly_temp, ignore_errors=True)
                logger.info("Cleaned up temp directory: %s", assembly_temp)
            except Exception as e:
                logger.warning("Failed to cleanup temp files: %s", str(e))

    def _create_title_card(
        self, text: str, duration: float, output_path: str, slot_number: int = 1
    ) -> str:
        """
        Create a title card video segment with text on a dark gradient background.

        Uses FFmpeg's drawtext filter with Noto Sans Kannada font.

        Args:
            text: Title/headline text (supports Kannada Unicode).
            duration: Duration of the title card in seconds.
            output_path: Path to save the title card video.
            slot_number: Active slot number for custom styling.

        Returns:
            Path to the created title card video.
        """
        # Find a suitable font
        font_file = self._find_font()
        font_opt = f":fontfile='{font_file}'" if font_file else ""

        # Escape special characters for FFmpeg drawtext filter
        escaped_text = self._escape_ffmpeg_text(text)

        # Select background color based on slot
        slot_bg_colors = {
            1: "#400000",       # Dark Red
            2: "#150000",       # Near Black / Dark Crimson
            3: "#502000",       # Dark Orange
            4: "#400030",       # Dark Pink
            5: "#001530",       # Dark Blue
            6: "#503000",       # Saffron Gold / Dark Orange-Brown
        }
        bg_color = slot_bg_colors.get(slot_number, "#0a0a2e")

        # Build FFmpeg command for background color + centered text
        cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi",
            "-i", (
                f"color=c={bg_color}:s={self.width}x{self.height}:d={duration}:r={self.fps},"
                f"format=yuv420p"
            ),
            "-vf", (
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

    def _concat_section_videos(self, video_list: list, output_path: str) -> str:
        """
        Concatenate finished section videos (with audio and subtitles) using FFmpeg concat demuxer.
        """
        if not video_list:
            raise ValueError("Cannot concatenate empty video list.")

        concat_file = output_path + ".concat.txt"
        with open(concat_file, "w", encoding="utf-8") as f:
            for video_path in video_list:
                safe_path = os.path.abspath(video_path).replace("\\", "/").replace("'", "'\\''")
                f.write(f"file '{safe_path}'\n")

        # Concatenate using concat demuxer, preserving audio and video stream
        cmd = [
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", concat_file,
            "-c", "copy",  # Direct stream copy (no re-encoding, extremely fast!)
            output_path,
        ]

        self._run_ffmpeg(cmd, "concatenate section videos")

        try:
            os.remove(concat_file)
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
        slot_number: int = 1,
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
            slot_number: Active slot number for custom styling.

        Returns:
            Path to the output video.
        """
        font_file = self._find_font()
        font_opt = f":fontfile='{font_file}'" if font_file else ""
        escaped_text = self._escape_ffmpeg_text(text)

        end_time = start_time + duration

        # Select colors based on slot number
        # Red: Slot 1, Crimson/Black: Slot 2, Orange: Slot 3, Pink/Cyan: Slot 4, Social blue: Slot 5, Saffron/Gold: Slot 6
        slot_colors = {
            1: {"box": "0xCC1111@0.85", "text": "white"},
            2: {"box": "0x150000@0.9", "text": "0xFFCCCC"},
            3: {"box": "0xFF6600@0.85", "text": "white"},
            4: {"box": "0xE51400@0.85", "text": "white"},
            5: {"box": "0x0088CC@0.85", "text": "white"},
            6: {"box": "0xFF9900@0.85", "text": "0xFFEE55"},
        }
        colors = slot_colors.get(slot_number, {"box": "black@0.7", "text": "white"})
        box_color = colors["box"]
        font_color = colors["text"]

        # Lower-third: semi-transparent custom slot bar + text
        drawbox_filter = (
            f"drawbox=x=0:y=ih-120:w=iw:h=120"
            f":color={box_color}:t=fill"
            f":enable='between(t,{start_time},{end_time})'"
        )
        drawtext_filter = (
            f"drawtext=text='{escaped_text}'"
            f"{font_opt}"
            f":fontsize=36"
            f":fontcolor={font_color}"
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
