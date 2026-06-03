"""
News Pipeline – Master Orchestrator
=====================================
Runs the complete YouTube news automation pipeline:
    Scrape → Script → Voice → Video → Thumbnail → Upload

Usage:
    python main.py --slot 1          # Run slot 1 (morning)
    python main.py --all             # Run all 6 slots sequentially
    python main.py --slot 1 --test   # Dry run (no upload)
    python main.py --scrape-only     # Just scrape & print news
    python main.py --script-only 1   # Scrape + generate script for slot 1

Exit Codes:
    0 = Success
    1 = Pipeline error
    2 = Invalid arguments
"""

import sys
import os
import logging
import argparse
import datetime
import time
import traceback
import shutil

# ---------------------------------------------------------------------------
# Ensure project root is on sys.path
# ---------------------------------------------------------------------------
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from config import SCHEDULE_SLOTS, PATHS, get_publish_datetime
from news_scraper import NewsScraper
from script_generator import ScriptGenerator
from voice_generator import VoiceGenerator
from video_assembler import VideoAssembler
from thumbnail_maker import ThumbnailMaker
from youtube_uploader import YouTubeUploader

# ---------------------------------------------------------------------------
# Logging Setup
# ---------------------------------------------------------------------------

def setup_logging(log_dir: str = "logs") -> logging.Logger:
    """
    Configure logging to both console and a daily log file.

    Args:
        log_dir: Directory for log files (created if missing).

    Returns:
        Root logger instance.
    """
    os.makedirs(log_dir, exist_ok=True)

    today = datetime.date.today().isoformat()
    log_file = os.path.join(log_dir, f"pipeline_{today}.log")

    # Formatter
    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(fmt)

    # File handler
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(fmt)

    # Root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)

    # Avoid duplicate handlers on re-import
    if not root_logger.handlers:
        root_logger.addHandler(console_handler)
        root_logger.addHandler(file_handler)

    return root_logger


logger = logging.getLogger(__name__)


# ===========================================================================
# News Pipeline
# ===========================================================================

class NewsPipeline:
    """
    Orchestrates the full news-to-YouTube pipeline for a given schedule slot.

    Attributes:
        slot_number (int): Which of the 6 daily slots to run (1-6).
        slot (dict): Slot configuration from config.SCHEDULE_SLOTS.
        dry_run (bool): If True, skip the YouTube upload step.
    """

    def __init__(self, slot_number: int, dry_run: bool = False):
        """
        Initialize the pipeline for a specific slot.

        Args:
            slot_number: Slot index (1-6).
            dry_run:     If True, everything runs except the upload.
        """
        if slot_number < 1 or slot_number > len(SCHEDULE_SLOTS):
            raise ValueError(
                f"Invalid slot number {slot_number}. Must be 1-{len(SCHEDULE_SLOTS)}."
            )

        self.slot_number = slot_number
        self.slot = SCHEDULE_SLOTS[slot_number - 1]  # 0-indexed internally
        self.dry_run = dry_run

        # Pipeline modules (initialized lazily where possible)
        self.scraper = None
        self.script_gen = None
        self.voice_gen = None
        self.video_assembler = None
        self.thumbnail_maker = None
        self.uploader = None

        # Track files for cleanup
        self._temp_files = []

        # Ensure output directories exist
        self._create_directories()

        logger.info(
            "Pipeline initialized: Slot %d (%s) | Dry run: %s",
            slot_number,
            self.slot.get("name", "unknown"),
            dry_run,
        )

    # ------------------------------------------------------------------
    # Directory management
    # ------------------------------------------------------------------

    def _create_directories(self):
        """Ensure all required output and temp directories exist."""
        dirs = [
            PATHS.get("output", "output"),
            PATHS.get("temp", "temp"),
            PATHS.get("assets", "assets"),
            "logs",
        ]
        for d in dirs:
            abs_dir = os.path.join(PROJECT_ROOT, d) if not os.path.isabs(d) else d
            os.makedirs(abs_dir, exist_ok=True)
            logger.debug("Directory ensured: %s", abs_dir)

    # ------------------------------------------------------------------
    # Output filename
    # ------------------------------------------------------------------

    def _get_output_filename(self, extension: str = "mp4") -> str:
        """
        Generate a formatted output filename.

        Format: news_YYYY-MM-DD_slotN_<name>.<ext>
        Example: news_2026-06-02_slot1_morning.mp4

        Args:
            extension: File extension (without dot).

        Returns:
            Full path to the output file.
        """
        today = datetime.date.today().isoformat()
        slot_name = self.slot.get("name", "unknown").lower().replace(" ", "_")
        filename = f"news_{today}_slot{self.slot_number}_{slot_name}.{extension}"

        output_dir = os.path.join(
            PROJECT_ROOT, PATHS.get("output", "output")
        )
        return os.path.join(output_dir, filename)

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def _cleanup(self):
        """Remove temporary files created during this pipeline run."""
        logger.info("Cleaning up %d temporary files...", len(self._temp_files))

        for fpath in self._temp_files:
            try:
                if os.path.isfile(fpath):
                    os.remove(fpath)
                    logger.debug("Removed temp file: %s", fpath)
                elif os.path.isdir(fpath):
                    shutil.rmtree(fpath, ignore_errors=True)
                    logger.debug("Removed temp dir: %s", fpath)
            except Exception as exc:
                logger.warning("Could not remove %s: %s", fpath, exc)

        # Also clean up the temp directory itself (if empty)
        temp_dir = os.path.join(PROJECT_ROOT, PATHS.get("temp", "temp"))
        try:
            if os.path.isdir(temp_dir) and not os.listdir(temp_dir):
                os.rmdir(temp_dir)
                logger.debug("Removed empty temp directory")
        except Exception:
            pass

        logger.info("Cleanup complete ✓")

    # ------------------------------------------------------------------
    # Main Pipeline Execution
    # ------------------------------------------------------------------

    def run(self) -> dict:
        """
        Execute the complete news pipeline.

        Steps:
            1. Scrape news articles
            2. Generate video script with Gemini AI
            3. Generate voiceover audio
            4. Assemble final video
            5. Create thumbnail
            6. Upload to YouTube
            7. Clean up temporary files

        Returns:
            dict: Pipeline result with keys like 'video_url', 'success', etc.

        Note:
            Each step is independently wrapped in try/except. If a critical
            step fails (scrape, script, voice, video), later steps are
            skipped but cleanup always runs.
        """
        start_time = time.time()
        today = datetime.date.today().isoformat()
        result = {
            "success": False,
            "slot": self.slot_number,
            "slot_name": self.slot.get("name", "unknown"),
            "date": today,
            "video_url": None,
            "error": None,
        }

        logger.info("=" * 70)
        logger.info(
            "🚀 PIPELINE START | Date: %s | Slot: %d (%s)",
            today,
            self.slot_number,
            self.slot.get("name", "unknown"),
        )
        logger.info("=" * 70)

        # Track intermediate outputs
        articles = None
        script_data = None
        audio_path = None
        video_path = None
        thumbnail_path = None

        # ================================================================
        # STEP 1: Scrape News
        # ================================================================
        try:
            logger.info("-" * 50)
            logger.info("📰 STEP 1/7: Scraping news articles...")
            logger.info("-" * 50)

            self.scraper = NewsScraper()
            articles = self.scraper.scrape_all()

            # Log article counts per category
            if isinstance(articles, dict):
                for category, items in articles.items():
                    count = len(items) if isinstance(items, list) else 0
                    logger.info("   %s: %d articles", category, count)
                total = sum(
                    len(v) for v in articles.values() if isinstance(v, list)
                )
            else:
                total = len(articles) if articles else 0

            logger.info("   Total articles scraped: %d ✓", total)

            if total == 0:
                raise RuntimeError("No articles scraped – cannot continue")

        except Exception as exc:
            logger.error("❌ STEP 1 FAILED (Scraping): %s", exc)
            logger.debug(traceback.format_exc())
            result["error"] = f"Scraping failed: {exc}"
            self._cleanup()
            elapsed = time.time() - start_time
            logger.info("Pipeline aborted after %.1f seconds", elapsed)
            return result

        # ================================================================
        # STEP 2: Generate Script
        # ================================================================
        try:
            logger.info("-" * 50)
            logger.info("📝 STEP 2/7: Generating video script...")
            logger.info("-" * 50)

            self.script_gen = ScriptGenerator()
            script_data = self.script_gen.generate(articles, self.slot)

            title = script_data.get("title", "Untitled")
            script_text = script_data.get("full_narration", "")
            word_count = len(script_text.split())

            logger.info("   Title     : %s", title)
            logger.info("   Word count: %d words", word_count)
            logger.info("   Script generated ✓")

        except Exception as exc:
            logger.error("❌ STEP 2 FAILED (Script generation): %s", exc)
            logger.debug(traceback.format_exc())
            result["error"] = f"Script generation failed: {exc}"
            self._cleanup()
            elapsed = time.time() - start_time
            logger.info("Pipeline aborted after %.1f seconds", elapsed)
            return result

        # ================================================================
        # STEP 3: Generate Voiceover
        # ================================================================
        try:
            logger.info("-" * 50)
            logger.info("🎙️ STEP 3/7: Generating voiceover...")
            logger.info("-" * 50)

            self.voice_gen = VoiceGenerator()
            audio_path = self.voice_gen.generate(script_data)
            self._temp_files.append(audio_path)

            # Get audio duration if possible
            try:
                import subprocess
                probe_cmd = [
                    "ffprobe", "-v", "quiet", "-show_entries",
                    "format=duration", "-of", "csv=p=0", audio_path
                ]
                duration = float(
                    subprocess.check_output(probe_cmd).decode().strip()
                )
                logger.info("   Audio file   : %s", audio_path)
                logger.info("   Duration     : %.1f seconds (%.1f min)", duration, duration / 60)
            except Exception:
                logger.info("   Audio file: %s ✓", audio_path)

        except Exception as exc:
            logger.error("❌ STEP 3 FAILED (Voiceover): %s", exc)
            logger.debug(traceback.format_exc())
            result["error"] = f"Voiceover generation failed: {exc}"
            self._cleanup()
            elapsed = time.time() - start_time
            logger.info("Pipeline aborted after %.1f seconds", elapsed)
            return result

        # ================================================================
        # STEP 4: Assemble Video
        # ================================================================
        try:
            logger.info("-" * 50)
            logger.info("🎬 STEP 4/7: Assembling video...")
            logger.info("-" * 50)

            self.video_assembler = VideoAssembler()
            output_video = self._get_output_filename("mp4")
            video_path = self.video_assembler.assemble(
                script_data=script_data,
                audio_path=audio_path,
                output_path=output_video,
            )

            file_size_mb = os.path.getsize(video_path) / (1024 * 1024)
            logger.info("   Video file : %s", video_path)
            logger.info("   File size  : %.1f MB", file_size_mb)

            # Get video duration
            try:
                import subprocess
                probe_cmd = [
                    "ffprobe", "-v", "quiet", "-show_entries",
                    "format=duration", "-of", "csv=p=0", video_path
                ]
                duration = float(
                    subprocess.check_output(probe_cmd).decode().strip()
                )
                logger.info("   Duration   : %.1f seconds (%.1f min)", duration, duration / 60)
            except Exception:
                pass

            logger.info("   Video assembled ✓")

        except Exception as exc:
            logger.error("❌ STEP 4 FAILED (Video assembly): %s", exc)
            logger.debug(traceback.format_exc())
            result["error"] = f"Video assembly failed: {exc}"
            self._cleanup()
            elapsed = time.time() - start_time
            logger.info("Pipeline aborted after %.1f seconds", elapsed)
            return result

        # ================================================================
        # STEP 5: Create Thumbnail
        # ================================================================
        try:
            logger.info("-" * 50)
            logger.info("🖼️ STEP 5/7: Creating thumbnail...")
            logger.info("-" * 50)

            self.thumbnail_maker = ThumbnailMaker()
            thumbnail_output = self._get_output_filename("jpg")
            thumbnail_path = self.thumbnail_maker.create(
                script_data=script_data,
                output_path=thumbnail_output,
            )

            logger.info("   Thumbnail: %s ✓", thumbnail_path)

        except Exception as exc:
            logger.warning("⚠️ STEP 5 FAILED (Thumbnail): %s – continuing without thumbnail", exc)
            logger.debug(traceback.format_exc())
            thumbnail_path = None

        # ================================================================
        # STEP 6: Upload to YouTube
        # ================================================================
        if self.dry_run:
            logger.info("-" * 50)
            logger.info("🧪 STEP 6/7: SKIPPED (dry run mode)")
            logger.info("   Video ready at: %s", video_path)
            logger.info("-" * 50)
            result["success"] = True
            result["video_path"] = video_path
        else:
            try:
                logger.info("-" * 50)
                logger.info("📤 STEP 6/7: Uploading to YouTube...")
                logger.info("-" * 50)

                self.uploader = YouTubeUploader()

                # Get scheduled publish time
                publish_at = get_publish_datetime(self.slot_number)

                # Prepare metadata from script_data
                title = script_data.get("title", f"News Update – {today}")
                description = script_data.get("description", script_data.get("script", "")[:500])
                tags = script_data.get("tags", ["news", "daily", "update"])

                # Upload with or without thumbnail
                if thumbnail_path and os.path.exists(thumbnail_path):
                    upload_result = self.uploader.upload_with_thumbnail(
                        video_path=video_path,
                        thumbnail_path=thumbnail_path,
                        title=title,
                        description=description,
                        tags=tags,
                        publish_at=publish_at,
                    )
                else:
                    upload_result = self.uploader.upload_video(
                        video_path=video_path,
                        title=title,
                        description=description,
                        tags=tags,
                        publish_at=publish_at,
                    )

                result["video_url"] = upload_result.get("url")
                result["video_id"] = upload_result.get("video_id")
                result["success"] = True

                logger.info("   Video URL: %s ✓", result["video_url"])

            except Exception as exc:
                logger.error("❌ STEP 6 FAILED (Upload): %s", exc)
                logger.debug(traceback.format_exc())
                result["error"] = f"Upload failed: {exc}"
                result["video_path"] = video_path  # Still accessible locally

        # ================================================================
        # STEP 7: Cleanup
        # ================================================================
        try:
            logger.info("-" * 50)
            logger.info("🧹 STEP 7/7: Cleaning up temporary files...")
            logger.info("-" * 50)
            self._cleanup()
        except Exception as exc:
            logger.warning("⚠️ Cleanup failed: %s", exc)

        # ================================================================
        # Summary
        # ================================================================
        elapsed = time.time() - start_time

        logger.info("=" * 70)
        if result["success"]:
            logger.info("✅ PIPELINE COMPLETE | Time: %.1f seconds (%.1f min)", elapsed, elapsed / 60)
            if result.get("video_url"):
                logger.info("   Video URL: %s", result["video_url"])
            elif result.get("video_path"):
                logger.info("   Video saved: %s", result["video_path"])
        else:
            logger.error("❌ PIPELINE FAILED | Time: %.1f seconds", elapsed)
            logger.error("   Error: %s", result.get("error", "Unknown"))
        logger.info("=" * 70)

        return result


# ===========================================================================
# Convenience Functions
# ===========================================================================

def run_slot(slot_number: int, dry_run: bool = False) -> dict:
    """
    Run the pipeline for a single slot.

    Args:
        slot_number: Slot index (1-6).
        dry_run:     If True, skip upload.

    Returns:
        Pipeline result dict.
    """
    pipeline = NewsPipeline(slot_number=slot_number, dry_run=dry_run)
    return pipeline.run()


def run_all_slots(dry_run: bool = False) -> list:
    """
    Run the pipeline for all 6 slots sequentially.
    Primarily useful for testing.

    Args:
        dry_run: If True, skip uploads.

    Returns:
        List of pipeline result dicts.
    """
    results = []
    total_slots = len(SCHEDULE_SLOTS)

    logger.info("Running all %d slots sequentially...", total_slots)

    for i in range(1, total_slots + 1):
        logger.info("\n" + "▶" * 40)
        logger.info("Starting slot %d of %d", i, total_slots)
        logger.info("▶" * 40 + "\n")

        try:
            result = run_slot(i, dry_run=dry_run)
            results.append(result)
        except Exception as exc:
            logger.error("Slot %d failed with unhandled exception: %s", i, exc)
            results.append({"success": False, "slot": i, "error": str(exc)})

        # Brief pause between slots to avoid rate limiting
        if i < total_slots:
            logger.info("Waiting 10 seconds before next slot...")
            time.sleep(10)

    # Summary
    successful = sum(1 for r in results if r.get("success"))
    logger.info("\n" + "=" * 70)
    logger.info("ALL SLOTS COMPLETE: %d/%d successful", successful, total_slots)
    logger.info("=" * 70)

    return results


# ===========================================================================
# CLI – argparse
# ===========================================================================

def build_parser() -> argparse.ArgumentParser:
    """Build the command-line argument parser."""
    parser = argparse.ArgumentParser(
        prog="main.py",
        description="🎬 YouTube News Automation Pipeline – Master Orchestrator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py --slot 1            Run morning slot
  python main.py --slot 3 --test     Dry run for afternoon slot
  python main.py --all               Run all 6 slots
  python main.py --all --test        Dry run all slots
  python main.py --scrape-only       Just scrape and display news
  python main.py --script-only 2     Scrape + generate script for slot 2
        """,
    )

    group = parser.add_mutually_exclusive_group(required=True)

    group.add_argument(
        "--slot",
        type=int,
        choices=range(1, len(SCHEDULE_SLOTS) + 1),
        metavar="N",
        help=f"Run a specific slot (1-{len(SCHEDULE_SLOTS)})",
    )

    group.add_argument(
        "--all",
        action="store_true",
        help="Run all slots sequentially",
    )

    group.add_argument(
        "--scrape-only",
        action="store_true",
        help="Only scrape news and display articles (no video)",
    )

    group.add_argument(
        "--script-only",
        type=int,
        choices=range(1, len(SCHEDULE_SLOTS) + 1),
        metavar="N",
        help="Scrape + generate script for slot N (no video/upload)",
    )

    parser.add_argument(
        "--test",
        action="store_true",
        help="Dry run – skip YouTube upload",
    )

    return parser


def handle_scrape_only():
    """Scrape news and print the results (no video generation)."""
    logger.info("🔍 Scrape-only mode: fetching news articles...")
    scraper = NewsScraper()
    articles = scraper.scrape_all()

    if isinstance(articles, dict):
        for category, items in articles.items():
            print(f"\n{'=' * 50}")
            print(f"  {category.upper()} ({len(items)} articles)")
            print(f"{'=' * 50}")
            for i, article in enumerate(items, 1):
                title = article.get("title", "No title")
                source = article.get("source", "Unknown")
                print(f"  {i}. [{source}] {title}")
    else:
        for i, article in enumerate(articles or [], 1):
            title = article.get("title", "No title")
            print(f"  {i}. {title}")

    print(f"\nTotal articles: {sum(len(v) for v in articles.values()) if isinstance(articles, dict) else len(articles or [])}")


def handle_script_only(slot_number: int):
    """Scrape news and generate a script for the given slot."""
    logger.info("📝 Script-only mode: slot %d", slot_number)

    slot = SCHEDULE_SLOTS[slot_number - 1]

    # Step 1: Scrape
    scraper = NewsScraper()
    articles = scraper.scrape_all()

    # Step 2: Generate script
    script_gen = ScriptGenerator()
    script_data = script_gen.generate(articles, slot)

    # Display the result
    print(f"\n{'=' * 60}")
    print(f"  GENERATED SCRIPT – Slot {slot_number} ({slot.get('name', 'unknown')})")
    print(f"{'=' * 60}")
    print(f"\nTitle: {script_data.get('title', 'N/A')}")
    print(f"Tags:  {', '.join(script_data.get('tags', []))}")
    print(f"\n--- SCRIPT ---\n")
    print(script_data.get("full_narration", "(empty)"))
    print(f"\n--- END SCRIPT ---")
    print(f"Word count: {len(script_data.get('full_narration', '').split())}")


# ===========================================================================
# Entry Point
# ===========================================================================

if __name__ == "__main__":
    # Configure console encoding for Unicode/Kannada characters
    if sys.platform.startswith("win"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
            sys.stderr.reconfigure(encoding="utf-8")
        except AttributeError:
            pass

    # Setup logging
    setup_logging(os.path.join(PROJECT_ROOT, "logs"))

    # Parse arguments
    parser = build_parser()
    args = parser.parse_args()

    exit_code = 0

    try:
        if args.scrape_only:
            handle_scrape_only()

        elif args.script_only:
            handle_script_only(args.script_only)

        elif args.all:
            results = run_all_slots(dry_run=args.test)
            failed = [r for r in results if not r.get("success")]
            if failed:
                exit_code = 1

        elif args.slot:
            result = run_slot(args.slot, dry_run=args.test)
            if not result.get("success"):
                exit_code = 1

    except KeyboardInterrupt:
        logger.info("\n⚠️ Pipeline interrupted by user (Ctrl+C)")
        exit_code = 130

    except Exception as exc:
        logger.error("💥 Unhandled exception: %s", exc)
        logger.debug(traceback.format_exc())
        exit_code = 1

    sys.exit(exit_code)
