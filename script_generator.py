"""
script_generator.py - Video Script Generator using Google Gemini API
=====================================================================

This module takes structured news data (from ``news_scraper.py``) and a
schedule slot, then generates a complete Kannada-language video script
using the Google Gemini 2.0 Flash API (free tier).

The output is a structured JSON dict with sections, narration text,
visual cues, B-roll keywords, YouTube metadata, and thumbnail headline.

Usage:
    from script_generator import generate
    from news_scraper import scrape_news
    import config

    news_data = scrape_news()
    slot = config.SCHEDULE_SLOTS[0]  # morning slot
    script = generate(news_data, slot)
    print(script["title"])
    print(script["full_narration"])
"""

import json
import logging
import re
import time
from datetime import datetime
from typing import Any, Dict, Optional

import google.generativeai as genai

import config

logger = logging.getLogger(__name__)

# =============================================================================
# CONSTANTS
# =============================================================================
MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 5  # base delay; doubles with each retry (exponential backoff)


# =============================================================================
# SCRIPT GENERATOR CLASS
# =============================================================================
class ScriptGenerator:
    """Generates structured Kannada video scripts using Google Gemini API.

    The generator sends a carefully constructed prompt containing the scraped
    news data and slot context to Gemini, and parses the response into a
    structured JSON script ready for TTS, video assembly, and YouTube upload.

    Attributes:
        model: The configured ``genai.GenerativeModel`` instance.

    Example:
        >>> gen = ScriptGenerator()
        >>> script = gen.generate_script(news_data, slot)
        >>> print(script["sections"][0]["narration"])
    """

    def __init__(self):
        """Initialize the Gemini model with the API key from config."""
        if not config.GEMINI_API_KEY:
            logger.warning(
                "GEMINI_API_KEY is empty in config.py. "
                "Set it before calling generate_script()."
            )

        genai.configure(api_key=config.GEMINI_API_KEY)

        self.model = genai.GenerativeModel(
            model_name=config.GEMINI_MODEL,
            generation_config=genai.GenerationConfig(
                temperature=0.7,
                top_p=0.9,
                max_output_tokens=8192,
            ),
        )
        logger.info(
            "ScriptGenerator initialized with model=%s", config.GEMINI_MODEL
        )

    def generate(self, news_data: dict, slot: dict) -> dict:
        """Alias for generate_script to ensure compatibility with orchestrator."""
        return self.generate_script(news_data, slot)

    def generate_script(self, news_data: dict, slot: dict) -> dict:
        """Generate a complete video script from news data and a schedule slot.

        This method builds a prompt, sends it to Gemini, parses the JSON
        response, and returns the structured script. Includes retry logic
        with exponential backoff for transient failures.

        Args:
            news_data: Dict with keys 'karnataka', 'national', 'international',
                       each containing a list of article dicts (from scrape_news).
            slot: A schedule slot dict from config.SCHEDULE_SLOTS.

        Returns:
            A dict with the following structure::

                {
                    "title": "video title in Kannada",
                    "description": "YouTube description",
                    "tags": ["tag1", "tag2", ...],
                    "sections": [
                        {
                            "name": "intro",
                            "duration_seconds": 40,
                            "narration": "narration text in Kannada",
                            "visual_cue": "what to show on screen",
                            "broll_keywords": ["keyword1", ...]
                        },
                        ...
                    ],
                    "full_narration": "complete narration for TTS",
                    "thumbnail_headline": "short punchy headline"
                }

        Raises:
            RuntimeError: If script generation fails after all retries.
        """
        prompt = self._build_prompt(news_data, slot)
        logger.info(
            "Generating script for slot %d (%s) — prompt length: %d chars",
            slot["slot_number"],
            slot["name"],
            len(prompt),
        )

        last_error: Optional[Exception] = None

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                logger.info("Attempt %d/%d to generate script...", attempt, MAX_RETRIES)

                response = self.model.generate_content(prompt)

                if not response or not response.text:
                    raise ValueError("Empty response received from Gemini API.")

                raw_text = response.text
                logger.debug(
                    "Gemini response received (%d chars).", len(raw_text)
                )

                script = self._parse_response(raw_text)

                # Validate required fields
                self._validate_script(script)

                logger.info(
                    "Script generated successfully: '%s' (%d sections)",
                    script.get("title", "untitled")[:60],
                    len(script.get("sections", [])),
                )
                return script

            except json.JSONDecodeError as exc:
                last_error = exc
                logger.warning(
                    "Attempt %d: Failed to parse JSON from Gemini response: %s",
                    attempt,
                    exc,
                )
            except ValueError as exc:
                last_error = exc
                logger.warning("Attempt %d: Validation error: %s", attempt, exc)
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "Attempt %d: Unexpected error: %s: %s",
                    attempt,
                    type(exc).__name__,
                    exc,
                )

            # Exponential backoff before retry
            if attempt < MAX_RETRIES:
                delay = RETRY_DELAY_SECONDS * (2 ** (attempt - 1))
                logger.info("Retrying in %d seconds...", delay)
                time.sleep(delay)

        error_msg = (
            f"Script generation failed after {MAX_RETRIES} attempts. "
            f"Last error: {last_error}"
        )
        logger.error(error_msg)
        raise RuntimeError(error_msg)

    # --------------------------------------------------------------------- #
    # PRIVATE METHODS
    # --------------------------------------------------------------------- #

    def _build_prompt(self, news_data: dict, slot: dict) -> str:
        """Construct the full prompt for Gemini with system instructions,
        news data, and slot context.

        Args:
            news_data: Structured news data from scrape_news().
            slot: Schedule slot dict from config.SCHEDULE_SLOTS.

        Returns:
            The complete prompt string.
        """
        today_str = datetime.now(config.IST).strftime("%d %B %Y, %A")

        # Format news articles for the prompt
        news_sections = []
        for category in ("karnataka", "national", "international"):
            articles = news_data.get(category, [])
            if not articles:
                news_sections.append(
                    f"### {category.upper()} NEWS\nNo articles available."
                )
                continue

            section_lines = [f"### {category.upper()} NEWS"]
            for i, article in enumerate(articles, 1):
                section_lines.append(
                    f"{i}. **{article.get('title', 'No title')}**\n"
                    f"   Source: {article.get('source', 'Unknown')}\n"
                    f"   Summary: {article.get('summary', 'No summary available.')}\n"
                    f"   Keywords: {', '.join(article.get('keywords', []))}"
                )
            news_sections.append("\n".join(section_lines))

        news_text = "\n\n".join(news_sections)

        target_duration = config.VIDEO_SETTINGS["target_duration_minutes"]

        prompt = f"""You are a professional Kannada news anchor and scriptwriter for the YouTube channel "{config.CHANNEL_NAME}".

## YOUR TASK
Write a complete news video script in **Kannada** for today's bulletin.

## CONTEXT
- **Date**: {today_str}
- **Bulletin**: {slot['name']} — Slot {slot['slot_number']}
- **Publish Time (IST)**: {slot['publish_time_ist']}
- **Content Focus**: {slot['content_focus']}
- **Title Template**: {slot['video_title_template']}
- **Target Duration**: {target_duration} minutes (~{target_duration * 60} seconds of narration)

## TODAY'S NEWS DATA

{news_text}

## OUTPUT FORMAT
You MUST respond with ONLY a valid JSON object (no extra text, no markdown fences) with this exact structure:

{{
    "title": "Compelling video title in Kannada using the template: {slot['video_title_template']}",
    "description": "SEO-optimized YouTube description in Kannada with key topics, hashtags, and a call-to-subscribe. 200-300 words.",
    "tags": ["relevant", "Kannada", "tags", "for", "YouTube", "SEO", "at least 10 tags"],
    "sections": [
        {{
            "name": "intro",
            "headline": "Short punchy introduction headline in Kannada",
            "duration_seconds": 40,
            "narration": "Engaging intro narration in Kannada greeting viewers, mentioning the date and bulletin name. Set the tone for the bulletin.",
            "visual_cue": "Channel logo animation, date overlay, anchor intro graphics",
            "broll_keywords": ["news studio", "Karnataka"]
        }},
        {{
            "name": "karnataka",
            "headline": "Short punchy Karnataka news headline in Kannada",
            "duration_seconds": 180,
            "narration": "Detailed coverage of 2-3 Karnataka stories in Kannada. Each story should have a clear transition. Include facts, quotes if available, and context.",
            "visual_cue": "Maps of Karnataka, relevant location shots, government buildings",
            "broll_keywords": ["Karnataka", "Bengaluru"]
        }},
        {{
            "name": "national",
            "headline": "Short punchy national news headline in Kannada",
            "duration_seconds": 150,
            "narration": "Coverage of 2-3 national news stories in Kannada with smooth transitions between stories.",
            "visual_cue": "India map, Parliament, relevant city shots",
            "broll_keywords": ["India", "Delhi", "Parliament"]
        }},
        {{
            "name": "international",
            "headline": "Short punchy international news headline in Kannada",
            "duration_seconds": 120,
            "narration": "Coverage of 1-2 international stories in Kannada, explaining global impact.",
            "visual_cue": "World map, relevant country visuals",
            "broll_keywords": ["world news", "global"]
        }},
        {{
            "name": "outro",
            "headline": "Short punchy outro headline in Kannada",
            "duration_seconds": 30,
            "narration": "Sign-off in Kannada thanking viewers, asking to like-subscribe-share, and previewing next bulletin.",
            "visual_cue": "Subscribe button animation, channel logo, next bulletin time",
            "broll_keywords": ["subscribe", "news channel"]
        }}
    ],
    "full_narration": "The COMPLETE narration text combining all sections, ready for text-to-speech. This must be natural-sounding Kannada suitable for a news anchor voice.",
    "thumbnail_headline": "Short punchy headline in Kannada (max 6-8 words) for the video thumbnail. Must be attention-grabbing."
}}

## IMPORTANT GUIDELINES
1. ALL narration must be in **Kannada** (ಕನ್ನಡ). Use formal news Kannada.
2. The total narration across all sections should approximately fill {target_duration} minutes when read aloud.
3. Each section's narration should be detailed enough to fill its allocated duration.
4. Include smooth transitions between stories (e.g., "ಈಗ ರಾಷ್ಟ್ರೀಯ ಸುದ್ದಿಗಳ ಕಡೆ ನೋಡೋಣ...").
5. The description and tags can include both Kannada and English for SEO.
6. The broll_keywords should be in English for stock footage search.
7. Make the narration engaging, authoritative, and viewer-friendly.
8. RESPOND WITH ONLY THE JSON — no explanation, no markdown code fences.
"""
        return prompt

    @staticmethod
    def _parse_response(response_text: str) -> dict:
        """Extract and parse JSON from the Gemini API response.

        Handles common response patterns:
        - Pure JSON response
        - JSON wrapped in markdown code blocks (```json ... ```)
        - JSON with leading/trailing whitespace or text

        Args:
            response_text: The raw text response from Gemini.

        Returns:
            Parsed JSON as a Python dict.

        Raises:
            json.JSONDecodeError: If no valid JSON can be extracted.
        """
        text = response_text.strip()

        # Attempt 1: Direct JSON parse
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Attempt 2: Extract from markdown code block (```json ... ``` or ``` ... ```)
        code_block_pattern = r"```(?:json)?\s*\n?(.*?)\n?\s*```"
        match = re.search(code_block_pattern, text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1).strip())
            except json.JSONDecodeError:
                pass

        # Attempt 3: Find the first { ... } block (greedy match for nested JSON)
        brace_match = re.search(r"\{.*\}", text, re.DOTALL)
        if brace_match:
            try:
                return json.loads(brace_match.group(0))
            except json.JSONDecodeError:
                pass

        # All attempts failed
        logger.error(
            "Could not extract valid JSON from response. First 500 chars: %s",
            text[:500],
        )
        raise json.JSONDecodeError(
            "No valid JSON found in Gemini response",
            text,
            0,
        )

    @staticmethod
    def _validate_script(script: dict) -> None:
        """Validate that the parsed script contains all required fields.

        Args:
            script: The parsed script dict.

        Raises:
            ValueError: If any required field is missing or empty.
        """
        required_top_level = [
            "title",
            "description",
            "tags",
            "sections",
            "full_narration",
            "thumbnail_headline",
        ]

        for field_name in required_top_level:
            if field_name not in script or not script[field_name]:
                raise ValueError(
                    f"Script is missing required field: '{field_name}'"
                )

        # Validate sections structure
        sections = script["sections"]
        if not isinstance(sections, list) or len(sections) < 3:
            raise ValueError(
                f"Script must have at least 3 sections, got {len(sections)}."
            )

        required_section_fields = [
            "name",
            "headline",
            "narration",
            "visual_cue",
            "broll_keywords",
        ]
        for i, section in enumerate(sections):
            for field_name in required_section_fields:
                if field_name not in section:
                    raise ValueError(
                        f"Section {i} ('{section.get('name', '?')}') is "
                        f"missing required field: '{field_name}'"
                    )

        logger.debug("Script validation passed. All required fields present.")


# =============================================================================
# CONVENIENCE FUNCTION
# =============================================================================

def generate(
    news_data: dict,
    slot: Optional[dict] = None,
) -> dict:
    """Convenience function to generate a video script.

    Args:
        news_data: Structured news data from ``scrape_news()``.
        slot: A schedule slot dict. If None, defaults to the first slot
              (morning bulletin).

    Returns:
        The generated script as a dict.
    """
    if slot is None:
        slot = config.SCHEDULE_SLOTS[0]
        logger.info("No slot specified; defaulting to slot 1 (morning).")

    generator = ScriptGenerator()
    return generator.generate_script(news_data, slot)


# =============================================================================
# MAIN — Testing / CLI
# =============================================================================
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )

    print("=" * 70)
    print("  YouTube News Automation — Script Generator Test")
    print("=" * 70)

    # --- Sample news data for testing (without actual scraping) ---
    sample_news_data: Dict[str, Any] = {
        "karnataka": [
            {
                "title": "Bengaluru Metro Phase 2 completion date announced",
                "summary": "The BMRCL has confirmed that Phase 2 of the Namma Metro project will be completed by December 2027, covering 72 km of new routes across the city.",
                "source": "Deccan Herald",
                "category": "karnataka",
                "link": "https://example.com/metro-phase2",
                "published_date": "2026-06-02T08:00:00+05:30",
                "keywords": ["Bengaluru", "metro", "BMRCL", "infrastructure"],
            },
            {
                "title": "Karnataka budget session to begin next week",
                "summary": "The Karnataka Legislature budget session is set to commence on June 9, with the state government expected to present a revenue-surplus budget.",
                "source": "The Hindu",
                "category": "karnataka",
                "link": "https://example.com/karnataka-budget",
                "published_date": "2026-06-02T07:30:00+05:30",
                "keywords": ["Karnataka", "budget", "legislature", "government"],
            },
            {
                "title": "Heavy rain alert for coastal Karnataka",
                "summary": "IMD has issued a red alert for Dakshina Kannada and Udupi districts as heavy rainfall is expected over the next 48 hours.",
                "source": "Prajavani",
                "category": "karnataka",
                "link": "https://example.com/rain-alert",
                "published_date": "2026-06-02T06:00:00+05:30",
                "keywords": ["rain", "coastal", "Karnataka", "IMD", "weather"],
            },
        ],
        "national": [
            {
                "title": "Parliament monsoon session dates announced",
                "summary": "The monsoon session of Parliament will begin on July 14 and continue until August 15, according to a notification from the Lok Sabha Secretariat.",
                "source": "NDTV",
                "category": "national",
                "link": "https://example.com/parliament-session",
                "published_date": "2026-06-02T09:00:00+05:30",
                "keywords": ["Parliament", "monsoon", "session", "Lok Sabha"],
            },
            {
                "title": "RBI keeps repo rate unchanged at 6%",
                "summary": "The Reserve Bank of India has decided to keep the repo rate unchanged at 6% in its latest monetary policy review, citing stable inflation.",
                "source": "Times of India",
                "category": "national",
                "link": "https://example.com/rbi-rate",
                "published_date": "2026-06-02T08:30:00+05:30",
                "keywords": ["RBI", "repo", "rate", "economy", "inflation"],
            },
        ],
        "international": [
            {
                "title": "UN Climate Summit reaches historic agreement",
                "summary": "World leaders at the UN Climate Summit have agreed to a landmark deal to cut carbon emissions by 50% by 2035.",
                "source": "Reuters",
                "category": "international",
                "link": "https://example.com/un-climate",
                "published_date": "2026-06-02T05:00:00+05:30",
                "keywords": ["UN", "climate", "summit", "emissions", "global"],
            },
        ],
        "scraped_at": "2026-06-02T10:00:00+05:30",
    }

    # Use the morning slot for testing
    test_slot = config.SCHEDULE_SLOTS[0]

    print(f"\nSlot: {test_slot['name']} ({test_slot['publish_time_ist']} IST)")
    print(f"Template: {test_slot['video_title_template']}")
    print("-" * 70)

    if not config.GEMINI_API_KEY:
        print("\n⚠️  GEMINI_API_KEY is not set in config.py!")
        print("   Set your API key and re-run this test.")
        print("\n   To test prompt generation without the API, here's the prompt:\n")

        gen = ScriptGenerator()
        prompt = gen._build_prompt(sample_news_data, test_slot)
        print(prompt[:2000])
        print(f"\n   ... (prompt continues for {len(prompt)} total characters)")
    else:
        try:
            script = generate(sample_news_data, test_slot)

            print(f"\n✅ Script generated successfully!")
            print(f"   Title: {script.get('title', 'N/A')}")
            print(f"   Thumbnail: {script.get('thumbnail_headline', 'N/A')}")
            print(f"   Sections: {len(script.get('sections', []))}")
            print(f"   Tags: {script.get('tags', [])}")
            print(f"\n   Full narration preview (first 500 chars):")
            narration = script.get("full_narration", "")
            print(f"   {narration[:500]}...")

            # Save the script to a JSON file for inspection
            import os

            os.makedirs(config.PATHS["output"], exist_ok=True)
            output_path = os.path.join(
                config.PATHS["output"], "test_script.json"
            )
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(script, f, ensure_ascii=False, indent=2)
            print(f"\n   Full script saved to: {output_path}")

        except RuntimeError as exc:
            print(f"\n❌ Script generation failed: {exc}")

    print("\n" + "=" * 70)
