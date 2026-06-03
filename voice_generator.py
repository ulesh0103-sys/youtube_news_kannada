"""
voice_generator.py - Voiceover Audio Generator using Edge TTS

Generates high-quality voiceover audio for news videos using Microsoft
Edge TTS (completely free, unlimited usage). Supports multiple languages
with a focus on Kannada news narration.

Features:
    - Async audio generation with Edge TTS
    - Synchronous wrapper for simple usage
    - Word-level subtitle generation (SRT format)
    - Configurable voice selection per language
    - Automatic duration logging

Dependencies:
    - edge-tts (pip install edge-tts)
"""

import edge_tts
import asyncio
import logging
import os
import time

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

# ─── Default TTS Settings (used if config module is unavailable) ─────────────
DEFAULT_TTS_SETTINGS = {
    "kannada": {
        "voice": "kn-IN-SapnaNeural",      # Female Kannada voice
        "rate": "+0%",                       # Normal speed
        "volume": "+0%",                     # Normal volume
        "pitch": "+0Hz",                     # Normal pitch
    },
    "hindi": {
        "voice": "hi-IN-SwaraNeural",
        "rate": "+0%",
        "volume": "+0%",
        "pitch": "+0Hz",
    },
    "english": {
        "voice": "en-IN-NeerjaNeural",
        "rate": "+0%",
        "volume": "+0%",
        "pitch": "+0Hz",
    },
}


class VoiceGenerator:
    """
    Generates voiceover audio files using Microsoft Edge TTS.

    Edge TTS is completely free with no API key required and supports
    a wide range of natural-sounding neural voices across many languages.

    Usage:
        >>> vg = VoiceGenerator(language='kannada')
        >>> # Async usage
        >>> path = await vg.generate_audio("ನಮಸ್ಕಾರ", "output/narration.mp3")
        >>> # Sync usage
        >>> path = vg.generate_audio_sync("ನಮಸ್ಕಾರ", "output/narration.mp3")
    """

    def __init__(self, language: str = "kannada"):
        """
        Initialize VoiceGenerator with a specific language.

        Args:
            language: Language code ('kannada', 'hindi', 'english').
                      Determines the TTS voice used for audio generation.
        """
        self.language = language.lower()

        # Load TTS settings from config module if available, else use defaults
        if config and hasattr(config, "TTS_SETTINGS"):
            c_settings = config.TTS_SETTINGS
            # Map the config.py keys to what VoiceGenerator expects
            self.voice = c_settings.get(f"voice_{self.language}") or c_settings.get("voice_kannada") or "kn-IN-SapnaNeural"
            self.rate = c_settings.get("rate") or "+0%"
            self.volume = c_settings.get("volume") or "+0%"
            self.pitch = c_settings.get("pitch") or "+0Hz"
        else:
            tts_settings = DEFAULT_TTS_SETTINGS
            if self.language not in tts_settings:
                self.language = "kannada"
            lang_settings = tts_settings[self.language]
            self.voice = lang_settings.get("voice", "kn-IN-SapnaNeural")
            self.rate = lang_settings.get("rate", "+0%")
            self.volume = lang_settings.get("volume", "+0%")
            self.pitch = lang_settings.get("pitch", "+0Hz")

        logger.info(
            "VoiceGenerator initialized: language=%s, voice=%s",
            self.language,
            self.voice,
        )

    def generate(self, script_data: dict, output_path: str = None) -> str:
        """
        Convenience method to generate audio and subtitles from script_data.

        Args:
            script_data: Dict containing 'full_narration' or 'script' and 'sections'.
            output_path: Optional path for output audio file. If not provided,
                         it generates a temp file path under config.PATHS['temp'].

        Returns:
            The path to the generated audio file.
        """
        # 1. Extract text to speak
        text = script_data.get("full_narration") or script_data.get("script")
        if not text:
            # Fallback: combine section narrations
            sections = script_data.get("sections", [])
            text = " ".join([s.get("narration", "") for s in sections])

        if not text or not text.strip():
            raise ValueError("No narration text found in script_data.")

        # 2. Determine output path
        if not output_path:
            import datetime
            today = datetime.date.today().isoformat()
            temp_dir = "temp"
            if config and hasattr(config, "PATHS") and "temp" in config.PATHS:
                temp_dir = config.PATHS["temp"]
            os.makedirs(temp_dir, exist_ok=True)
            output_path = os.path.join(temp_dir, f"voiceover_{today}.mp3")
            subtitle_path = os.path.join(temp_dir, f"voiceover_{today}.srt")
        else:
            subtitle_path = os.path.splitext(output_path)[0] + ".srt"

        # 3. Generate both audio and subtitles
        audio_path, srt_path = asyncio.run(
            self.generate_with_subtitles(text, output_path, subtitle_path)
        )
        return audio_path

    async def generate_audio(self, text: str, output_path: str) -> str:
        """
        Generate an MP3 audio file from text using Edge TTS (async).

        Args:
            text: The text to convert to speech.
            output_path: File path where the MP3 will be saved.

        Returns:
            The absolute path to the generated MP3 file.

        Raises:
            ValueError: If text is empty or None.
            IOError: If the output file cannot be written.
        """
        # ── Validate input ────────────────────────────────────────────────
        if not text or not text.strip():
            raise ValueError("Text for audio generation cannot be empty.")

        if not output_path:
            raise ValueError("Output path must be specified.")

        # Ensure output directory exists
        output_dir = os.path.dirname(output_path)
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)

        logger.info(
            "Generating audio: %d chars, voice=%s, output=%s",
            len(text),
            self.voice,
            output_path,
        )

        start_time = time.time()

        try:
            # ── Create Edge TTS communicator ──────────────────────────────
            communicate = edge_tts.Communicate(
                text=text,
                voice=self.voice,
                rate=self.rate,
                volume=self.volume,
                pitch=self.pitch,
            )

            # ── Save audio to file ────────────────────────────────────────
            await communicate.save(output_path)

            elapsed = time.time() - start_time

            # ── Log file info ─────────────────────────────────────────────
            if os.path.exists(output_path):
                file_size_mb = os.path.getsize(output_path) / (1024 * 1024)
                logger.info(
                    "Audio generated successfully: %s (%.2f MB, took %.1fs)",
                    output_path,
                    file_size_mb,
                    elapsed,
                )
            else:
                raise IOError(f"Audio file was not created at: {output_path}")

            return os.path.abspath(output_path)

        except edge_tts.exceptions.NoAudioReceived:
            logger.error("No audio received from Edge TTS. Check voice/text validity.")
            raise
        except Exception as e:
            logger.error("Failed to generate audio: %s", str(e))
            raise IOError(f"Audio generation failed: {e}") from e

    def generate_audio_sync(self, text: str, output_path: str) -> str:
        """
        Synchronous wrapper for generate_audio().

        Convenient for use in non-async contexts. Internally uses
        asyncio.run() to execute the async method.

        Args:
            text: The text to convert to speech.
            output_path: File path where the MP3 will be saved.

        Returns:
            The absolute path to the generated MP3 file.
        """
        logger.info("Running audio generation synchronously...")
        return asyncio.run(self.generate_audio(text, output_path))

    async def generate_with_subtitles(
        self, text: str, audio_path: str, subtitle_path: str
    ) -> tuple:
        """
        Generate both audio and SRT subtitle file with word-level timestamps.

        Uses Edge TTS SubMaker to extract word-level timing information
        and converts it into standard SRT subtitle format.

        Args:
            text: The text to convert to speech.
            audio_path: File path for the output MP3 audio.
            subtitle_path: File path for the output SRT subtitle file.

        Returns:
            Tuple of (audio_path, subtitle_path) — absolute paths.

        Raises:
            ValueError: If text is empty.
            IOError: If files cannot be written.
        """
        if not text or not text.strip():
            raise ValueError("Text for subtitle generation cannot be empty.")

        # Ensure output directories exist
        for path in (audio_path, subtitle_path):
            out_dir = os.path.dirname(path)
            if out_dir:
                os.makedirs(out_dir, exist_ok=True)

        logger.info(
            "Generating audio with subtitles: audio=%s, srt=%s",
            audio_path,
            subtitle_path,
        )

        start_time = time.time()

        try:
            max_attempts = 3
            attempt = 0
            while attempt < max_attempts:
                attempt += 1
                try:
                    # ── Create communicator and SubMaker ──────────────────────────
                    communicate = edge_tts.Communicate(
                        text=text,
                        voice=self.voice,
                        rate=self.rate,
                        volume=self.volume,
                        pitch=self.pitch,
                    )
                    submaker = edge_tts.SubMaker()

                    # ── Stream audio and collect subtitle data ────────────────────
                    with open(audio_path, "wb") as audio_file:
                        async for chunk in communicate.stream():
                            if chunk["type"] == "audio":
                                audio_file.write(chunk["data"])
                            elif chunk["type"] == "WordBoundary":
                                submaker.feed(chunk)
                    break  # Succeeded, exit the retry loop
                except Exception as exc:
                    logger.warning(
                        "Attempt %d/%d to generate audio failed: %s",
                        attempt,
                        max_attempts,
                        exc,
                    )
                    if attempt >= max_attempts:
                        logger.error(
                            "Edge TTS failed after %d attempts: %s",
                            max_attempts,
                            exc,
                        )
                        raise
                    # Exponential backoff sleep before retrying
                    import asyncio
                    await asyncio.sleep(attempt * 2)

            # ── Generate SRT content ──────────────────────────────────────
            if hasattr(submaker, "get_srt"):
                srt_content = submaker.get_srt()
            else:
                srt_content = submaker.generate_subs()

            if srt_content and srt_content.strip():
                with open(subtitle_path, "w", encoding="utf-8") as srt_file:
                    srt_file.write(srt_content)
                logger.info("Subtitles written to: %s", subtitle_path)
            else:
                # If SubMaker didn't produce output, create a basic SRT
                logger.warning(
                    "SubMaker returned empty subtitles. Creating basic SRT from text."
                )
                basic_srt = self._create_basic_srt(text)
                with open(subtitle_path, "w", encoding="utf-8") as srt_file:
                    srt_file.write(basic_srt)

            elapsed = time.time() - start_time
            logger.info(
                "Audio + subtitles generated in %.1fs", elapsed
            )

            return os.path.abspath(audio_path), os.path.abspath(subtitle_path)

        except Exception as e:
            logger.error("Failed to generate audio with subtitles: %s", str(e))
            raise IOError(f"Audio+subtitle generation failed: {e}") from e

    @staticmethod
    def _format_srt(subtitles: list) -> str:
        """
        Format subtitle data into SRT string format.

        Args:
            subtitles: List of dicts with keys:
                - 'index': int, subtitle sequence number
                - 'start': str, start time in SRT format (HH:MM:SS,mmm)
                - 'end': str, end time in SRT format (HH:MM:SS,mmm)
                - 'text': str, subtitle text content

        Returns:
            Formatted SRT string ready to write to file.

        Example SRT entry:
            1
            00:00:00,000 --> 00:00:02,500
            ನಮಸ್ಕಾರ, ಇಂದಿನ ಸುದ್ದಿ
        """
        if not subtitles:
            return ""

        srt_lines = []
        for sub in subtitles:
            srt_lines.append(str(sub.get("index", 1)))
            srt_lines.append(
                f"{sub.get('start', '00:00:00,000')} --> {sub.get('end', '00:00:05,000')}"
            )
            srt_lines.append(sub.get("text", ""))
            srt_lines.append("")  # Blank line separator

        return "\n".join(srt_lines)

    @staticmethod
    def _create_basic_srt(text: str, chars_per_sub: int = 80) -> str:
        """
        Create a basic SRT file from text when word-level timing is unavailable.

        Splits text into chunks and assigns estimated timestamps based on
        an average speaking rate.

        Args:
            text: Full text to convert to subtitles.
            chars_per_sub: Approximate characters per subtitle entry.

        Returns:
            Formatted SRT string.
        """
        words = text.split()
        chunks = []
        current_chunk = []
        current_len = 0

        for word in words:
            current_chunk.append(word)
            current_len += len(word) + 1
            if current_len >= chars_per_sub:
                chunks.append(" ".join(current_chunk))
                current_chunk = []
                current_len = 0

        if current_chunk:
            chunks.append(" ".join(current_chunk))

        # Estimate ~150 words per minute → ~2.5 words/sec
        # Average word length ~5 chars → ~12.5 chars/sec
        srt_entries = []
        time_cursor = 0.0

        for i, chunk in enumerate(chunks, start=1):
            duration = max(2.0, len(chunk) / 12.5)
            start_ts = _seconds_to_srt_time(time_cursor)
            end_ts = _seconds_to_srt_time(time_cursor + duration)

            srt_entries.append(f"{i}")
            srt_entries.append(f"{start_ts} --> {end_ts}")
            srt_entries.append(chunk)
            srt_entries.append("")

            time_cursor += duration

        return "\n".join(srt_entries)


# ─── Helper Functions ─────────────────────────────────────────────────────────


def _seconds_to_srt_time(seconds: float) -> str:
    """
    Convert seconds to SRT timestamp format (HH:MM:SS,mmm).

    Args:
        seconds: Time in seconds (e.g., 65.5 → "00:01:05,500").

    Returns:
        Formatted SRT timestamp string.
    """
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


# ─── Main: Test / Demo ───────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("  Voice Generator - Edge TTS Demo")
    print("=" * 60)

    # Sample Kannada text for testing
    sample_text = "ನಮಸ್ಕಾರ, ಇಂದಿನ ಪ್ರಮುಖ ಸುದ್ದಿಗಳನ್ನು ನೋಡೋಣ"

    # Create output directory
    os.makedirs("output", exist_ok=True)

    # Initialize generator
    vg = VoiceGenerator(language="kannada")

    # ── Test 1: Basic audio generation ────────────────────────────────────
    print("\n[Test 1] Generating basic audio...")
    try:
        output_file = vg.generate_audio_sync(sample_text, "output/test_voice.mp3")
        print(f"  ✓ Audio saved to: {output_file}")
    except Exception as e:
        print(f"  ✗ Error: {e}")

    # ── Test 2: Audio with subtitles ──────────────────────────────────────
    print("\n[Test 2] Generating audio with subtitles...")
    try:
        audio_path, srt_path = asyncio.run(
            vg.generate_with_subtitles(
                sample_text,
                "output/test_voice_sub.mp3",
                "output/test_voice.srt",
            )
        )
        print(f"  ✓ Audio: {audio_path}")
        print(f"  ✓ Subtitles: {srt_path}")

        # Display generated SRT content
        if os.path.exists(srt_path):
            with open(srt_path, "r", encoding="utf-8") as f:
                print(f"\n  --- SRT Content ---\n{f.read()[:500]}")
    except Exception as e:
        print(f"  ✗ Error: {e}")

    print("\n" + "=" * 60)
    print("  Demo complete!")
    print("=" * 60)
