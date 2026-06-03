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
# 30-DAY DEVOTIONAL CALENDAR FOR SLOT 6
# =============================================================================
DEVOTIONAL_CALENDAR = [
    {
        "day": 1,
        "deity": "Krishna",
        "title": "Krishna and Putana",
        "focus": "How infant Krishna defeated the demon Putana disguised as a nurse. The power of divine innocence.",
        "source": "Bhagavata Purana 10.6"
    },
    {
        "day": 2,
        "deity": "Shiva",
        "title": "Shiva drinks the poison",
        "focus": "During Samudra Manthan, Shiva swallows Halahala to save the universe. He is called Neelakantha.",
        "source": "Vishnu Purana"
    },
    {
        "day": 3,
        "deity": "Rama",
        "title": "Rama breaks the Shiva Dhanush",
        "focus": "At Sita's swayamvara, Rama lifts and breaks the divine bow — and wins Sita's hand.",
        "source": "Valmiki Ramayana, Bal Kand"
    },
    {
        "day": 4,
        "deity": "Devi",
        "title": "Chamundeshwari kills Mahishasura",
        "focus": "The fierce goddess battles the buffalo demon Mahishasura for 9 days and emerges victorious.",
        "source": "Devi Mahatmya, Markandeya Purana"
    },
    {
        "day": 5,
        "deity": "Ganesh",
        "title": "Ganesh and the moon's curse",
        "focus": "Ganesh curses the moon for laughing at him. The story of humility and the origin of Chaturthi.",
        "source": "Shiva Purana"
    },
    {
        "day": 6,
        "deity": "Krishna",
        "title": "Govardhan Parvata",
        "focus": "Krishna lifts the Govardhan hill with his little finger to protect villagers from Indra's wrath.",
        "source": "Bhagavata Purana 10.25"
    },
    {
        "day": 7,
        "deity": "Hanuman",
        "title": "Hanuman burns Lanka",
        "focus": "After finding Sita, Hanuman allows Ravana's soldiers to set his tail on fire — then burns all of Lanka.",
        "source": "Valmiki Ramayana, Sundara Kand"
    },
    {
        "day": 8,
        "deity": "Shiva",
        "title": "Shiva and Parvati's marriage",
        "focus": "The divine love story of Parvati's tapasya and Shiva finally accepting her as his eternal wife.",
        "source": "Shiva Purana, Rudra Samhita"
    },
    {
        "day": 9,
        "deity": "Krishna",
        "title": "Kaliya Mardana",
        "focus": "Krishna tames the deadly serpent Kaliya in the Yamuna river — dancing on his hundred hoods.",
        "source": "Bhagavata Purana 10.16"
    },
    {
        "day": 10,
        "deity": "Rama",
        "title": "Shabari's berries",
        "focus": "The devoted old woman Shabari offers half-eaten berries to Rama. He eats them with joy — love over ritual.",
        "source": "Valmiki Ramayana, Aranya Kand"
    },
    {
        "day": 11,
        "deity": "Regional",
        "title": "Renuka Devi of Saundatti",
        "focus": "The powerful story of Yellamma / Renuka Devi — revered across Karnataka and Maharashtra.",
        "source": "Karnataka folk tradition"
    },
    {
        "day": 12,
        "deity": "Krishna",
        "title": "Sudama visits Dwarka",
        "focus": "Poor Sudama brings only beaten rice for his friend Krishna. Krishna blesses him with unimaginable wealth.",
        "source": "Bhagavata Purana 10.80"
    },
    {
        "day": 13,
        "deity": "Ganesh",
        "title": "Ganesh and Kubera's feast",
        "focus": "Ganesh eats all of Kubera's food, then eats Kubera himself. Only Shiva's earth calms him.",
        "source": "Shiva Purana"
    },
    {
        "day": 14,
        "deity": "Shiva",
        "title": "Shiva as Nataraja",
        "focus": "The cosmic dance of Shiva — Tandava — destroying and creating the universe in one eternal rhythm.",
        "source": "Shaiva Agamas"
    },
    {
        "day": 15,
        "deity": "Devi",
        "title": "Lakshmi and the ocean of milk",
        "focus": "How Goddess Lakshmi emerged from the churning of the ocean and chose Vishnu as her eternal companion.",
        "source": "Vishnu Purana"
    },
    {
        "day": 16,
        "deity": "Krishna",
        "title": "Arjuna's vishada and the Gita",
        "focus": "On the Kurukshetra battlefield, Arjuna breaks down. Krishna speaks the 18 chapters of the Bhagavad Gita.",
        "source": "Mahabharata, Bhishma Parva"
    },
    {
        "day": 17,
        "deity": "Hanuman",
        "title": "Hanuman brings the Sanjeevani",
        "focus": "Hanuman flies to the Himalayas to fetch the life-giving herb and saves Lakshmana's life.",
        "source": "Valmiki Ramayana, Yuddha Kand"
    },
    {
        "day": 18,
        "deity": "Regional",
        "title": "Chamundi of Mysuru",
        "focus": "The story of Chamundeshwari, the fierce goddess atop Chamundi Hills — protector of Mysuru kingdom.",
        "source": "Karnataka / Mysuru tradition"
    },
    {
        "day": 19,
        "deity": "Shiva",
        "title": "Markandeya defeats death",
        "focus": "The boy Markandeya holds Shiva's Lingam as Yama comes to take him. Shiva kicks Yama away — defeating death.",
        "source": "Shiva Purana"
    },
    {
        "day": 20,
        "deity": "Krishna",
        "title": "Draupadi's vastraharan",
        "focus": "Draupadi calls out to Krishna in her hour of deepest shame. Krishna provides infinite cloth and saves her honor.",
        "source": "Mahabharata, Sabha Parva"
    },
    {
        "day": 21,
        "deity": "Rama",
        "title": "Jatayu fights Ravana",
        "focus": "The old eagle king Jatayu battles Ravana alone to save Sita — losing his wings but never his dharma.",
        "source": "Valmiki Ramayana, Aranya Kand"
    },
    {
        "day": 22,
        "deity": "Devi",
        "title": "Saraswati and the origin of knowledge",
        "focus": "How Saraswati was born, why she holds the veena and the book, and why she is worshipped before any learning.",
        "source": "Brahma Vaivarta Purana"
    },
    {
        "day": 23,
        "deity": "Ganesh",
        "title": "Ganesh writes the Mahabharata",
        "focus": "Vyasa recites the Mahabharata and Ganesh writes it — with one condition that Vyasa must never pause.",
        "source": "Mahabharata, Adi Parva"
    },
    {
        "day": 24,
        "deity": "Krishna",
        "title": "Krishna and Kuchela",
        "focus": "Same as Sudama — told in the South Indian tradition with regional details and Tamil Bhakti flavor.",
        "source": "Bhagavata Purana / Alvar tradition"
    },
    {
        "day": 25,
        "deity": "Shiva",
        "title": "Kannappa the hunter",
        "focus": "A tribal hunter offers his own eyes to a Shiva Lingam when it bleeds. Shiva calls him his greatest devotee.",
        "source": "Shaiva tradition / Skanda Purana"
    },
    {
        "day": 26,
        "deity": "Hanuman",
        "title": "Hanuman shows Rama in his heart",
        "focus": "Hanuman tears open his chest to show that Rama and Sita live inside his heart. The ultimate bhakti.",
        "source": "Post-Ramayana tradition"
    },
    {
        "day": 27,
        "deity": "Regional",
        "title": "Basavanna and Shiva's grace",
        "focus": "The 12th century Karnataka saint Basavanna's devotion to Shiva and his Vachana movement.",
        "source": "Karnataka Shaiva tradition"
    },
    {
        "day": 28,
        "deity": "Krishna",
        "title": "Mirabai's devotion to Krishna",
        "focus": "Mirabai drinks poison sent by her husband — it becomes nectar because of her love for Krishna.",
        "source": "Bhakti tradition / Rajasthan"
    },
    {
        "day": 29,
        "deity": "Devi",
        "title": "Durga and the 9 nights",
        "focus": "The complete story of Navratri — 9 forms of Durga and the battles she fought each night.",
        "source": "Devi Mahatmya / Markandeya Purana"
    },
    {
        "day": 30,
        "deity": "Krishna",
        "title": "Krishna's final message",
        "focus": "The last chapter of the Bhagavad Gita — Krishna's promise: I will carry what you lack and preserve what you have.",
        "source": "Bhagavad Gita 9.22"
    }
]

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
                script["slot_number"] = slot.get("slot_number", 1)

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

    def _format_news_for_prompt(self, news_data: dict) -> str:
        """Format news articles for the prompt."""
        if not news_data:
            return "No news articles available."
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
        return "\n\n".join(news_sections)

    def _build_prompt(self, news_data: dict, slot: dict) -> str:
        """Construct the full prompt for Gemini with system instructions,
        news data, and slot context.
        """
        today_str = datetime.now(config.IST).strftime("%d %B %Y, %A")
        slot_number = slot.get("slot_number", 1)
        target_duration = config.VIDEO_SETTINGS["target_duration_minutes"]

        # Base instructions specifying JSON structure
        base_instructions = f"""You are a professional Kannada content creator and scriptwriter for the YouTube channel "{config.CHANNEL_NAME}".

## YOUR TASK
Write a complete video script in **Kannada** for today's bulletin.

RESPOND WITH ONLY A VALID JSON OBJECT (no extra text, no markdown code fences). The structure MUST strictly match this output format:
{{
    "title": "Compelling video title in Kannada",
    "description": "SEO-optimized YouTube description in Kannada, 200-300 words with hashtags.",
    "tags": ["relevant", "Kannada", "tags", "for", "YouTube", "SEO", "at least 10 tags"],
    "sections": [
        {{
            "name": "section_name",
            "headline": "Short punchy section title/headline in Kannada (max 6-8 words)",
            "duration_seconds": 60,
            "narration": "Narration text in Kannada for this section",
            "visual_cue": "visual instructions/description for this section",
            "broll_keywords": ["keyword1", "keyword2"]
        }}
    ],
    "full_narration": "The complete combined narration text of all sections",
    "thumbnail_headline": "Short punchy headline in Kannada (max 6-8 words) for the video thumbnail"
}}

IMPORTANT GUIDELINES:
1. ALL narration, section titles, and description text must be in **Kannada** (ಕನ್ನಡ). Use formal and natural Kannada.
2. The description and tags can include both Kannada and English for SEO.
3. The broll_keywords MUST be in English for stock footage search (max 2-3 words per keyword).
"""

        if slot_number == 1:
            # Slot 1: Morning News
            news_text = self._format_news_for_prompt(news_data)
            prompt = base_instructions + f"""
## SLOT SPECIFICS: SLOT 1 — MORNING NEWS
- **Reference Channels:** TV9 Kannada, Republic Bharat, NDTV India (breaking news, alert, urgent tone)
- **Visual Cue Style:** Map layouts, official photos, news anchor desk visual cues.
- **Narrative Style:** Active, breaking news reportage style.
- **Narration Duration:** 5-8 minutes total.

## SCRIPT FORMAT REQUIREMENTS:
- The script must open with: "ನಮಸ್ಕಾರ, ಟೆಕ್ ಟೇಲ್ಸ್ ಗೆ ಸ್ವಾಗತ! ಈ ಹಾಗೆ ಇರುತ್ತೆ ಇವತ್ತಿನ ಪ್ರಧಾನ ಸಮಾಚಾರ..." (or equivalent Kannada translation for opening).
- Include 3 to 5 distinct breaking news stories from the following data (prioritize political relevance, weather/disaster alerts, government policy, or major accidents/crimes).
- The script must end with: "ಮತ್ತೆ ಸಿಗೋಣ ಟೆಕ್ ಟೇಲ್ಸ್ ನಲ್ಲಿ. ಲೈಕ್ ಮಾಡಿ, ಶೇರ್ ಮಾಡಿ!" (or equivalent Kannada translation).

## TODAY'S NEWS DATA:
{news_text}
"""
        elif slot_number == 2:
            # Slot 2: Crime Thrillers
            prompt = base_instructions + f"""
## SLOT SPECIFICS: SLOT 2 — CRIME THRILLERS
- **Reference Channels:** Crime Tak, Savdhaan India, Vikatan Tamil (suspenseful, dark, dramatic recreation cues)
- **Visual Cue Style:** Dark city alley at night, suspect silhouettes, crime scene drawings, police cars, courtroom.
- **Narrative Style:** Suspenseful, slow, dramatic documentary-style storytelling. Building tension.
- **Narration Duration:** 10-15 minutes total.

## SCRIPT FORMAT REQUIREMENTS:
- **Hook:** Start with a shocking moment or mystery opening (e.g., "ರಾತ್ರಿ 2 ಗಂಟೆಗೆ... ಒಂದು ಕಾಲ್ ಬಂತು..." style in Kannada).
- **Background:** Introduce the victims, location, and suspects/characters involved.
- **Crime:** Describe step-by-step how the crime took place based on factual accounts. Do not glorify.
- **Investigation:** Detail how the police or CBI tracked down clues and caught the culprit.
- **Verdict/Outcome:** Describe the final court verdict or legal outcome.
- **Moral closing:** Provide a brief reflection on safety or justice (e.g. "ಈ ಲೋಕದಲ್ಲಿ..." type ending in Kannada).
- Select or base the narrative on one real famous true crime story set in India (choose a recent famous heist, cyber fraud, murder mystery, or historical detective case).
"""
        elif slot_number == 3:
            # Slot 3: Evening News
            news_text = self._format_news_for_prompt(news_data)
            prompt = base_instructions + f"""
## SLOT SPECIFICS: SLOT 3 — EVENING NEWS (Evening Update)
- **Reference Channels:** Suvarna News Kannada, Zee Kannada News, ABP Desam (warm tones, afternoon energy)
- **Visual Cue Style:** City skyline at midday, business charts, stock market graphs, sports stadiums, scoreboards.
- **Narrative Style:** Professional, updates on sports, technology, business, global and Karnataka stories.
- **Narration Duration:** 6-10 minutes total.

## SCRIPT FORMAT REQUIREMENTS:
- The script must open differently from Slot 1: "ಸಂಜೆ ಆಯಿತು, ಟೆಕ್ ಟೇಲ್ಸ್ ಗೆ ಮತ್ತೆ ಏಕ ಬಾರಿ ಸ್ವಾಗತ! ಈ ಸರಿಯಾಗಿ ಹೇಳ್ತೀನಿ ಇವತ್ತು ಅಂತರ ಪ್ರಧಾನ..." (or equivalent Kannada translation welcoming viewers to the evening update).
- Select 4 to 6 stories from the news data below. Focus on business/economy, sports, entertainment, technology, or global updates.
- **CRITICAL:** Cross-check and do NOT duplicate stories that would be typical morning breaking news (Slot 1).
- **Did You Know Segment:** Include one interesting "Did You Know / Today's Fact" segment as the final section before sign-off.
- The script must end with a subscribe prompt.

## TODAY'S NEWS DATA:
{news_text}
"""
        elif slot_number == 4:
            # Slot 4: Viral Entertainment
            prompt = base_instructions + f"""
## SLOT SPECIFICS: SLOT 4 — VIRAL ENTERTAINMENT
- **Reference Channels:** MostlySane, Round2Hell, Trakin Tech, Mythpat (bright, colorful, energetic)
- **Visual Cue Style:** Meme graphics, reaction-face visuals, colorful overlay text cues, excited face expressions.
- **Narrative Style:** High energy, comedic, conversational, and reaction-based.
- **Narration Duration:** 5-10 minutes total.

## SCRIPT FORMAT REQUIREMENTS:
- **Hook:** Start with a high-energy hook (e.g., "ಇವತ್ತಿನ ಅತ್ಯಂತ ವೈರಲ್ ವಿಡಿಯೋ ನೋಡಿದ್ದೀರಾ? ಇಲ್ಲದಿದ್ದರೆ ಪರವಾಗಿಲ್ಲ, ನಾವು ಹೇಳ್ತೀವಿ!" or equivalent Kannada).
- **Context:** Select a trending movie trailer, viral meme trend, comedy skit, or viral moment in India, and explain why everyone is talking about it.
- **Reaction/Commentary:** Share your channel's original humorous reaction, review, or inspired commentary.
- **Audience Engagement:** Ask the viewers to comment their thoughts (e.g., "ನಿಮ್ಮ ಅನಿಸಿಕೆಯನ್ನು ಕಮೆಂಟ್ ಮಾಡಿ!").
"""
        elif slot_number == 5:
            # Slot 5: Social Media Buzz
            prompt = base_instructions + f"""
## SLOT SPECIFICS: SLOT 5 — SOCIAL MEDIA BUZZ
- **Reference Channels:** Dhruv Rathee, Sochta India, Revolver Rani (explainer, balanced dual-view)
- **Visual Cue Style:** Mobile phone mockups showing social media layouts, notification icons, trending graphs, split screens showing both sides of a debate.
- **Narrative Style:** Analytical, balanced, explanatory.
- **Narration Duration:** 6-9 minutes total.

## SCRIPT FORMAT REQUIREMENTS:
- **Hook:** Start with a catchy hook (e.g., "ಇವತ್ತು ಸೋಷಿಯಲ್ ಮೀಡಿಯಾದಲ್ಲಿ ಏನಾಗ್ತಿದೆ? ಎಲ್ಲರ ಫೋನ್ ಕೂಡ ಬಿಸಿಯಾಗಿದೆ..." or equivalent Kannada).
- **Show the Trend:** Select a viral social controversy, a tweet that blew up, or a major reel/ Shorts trend, and explain what happened and who was involved.
- **Reactions:** Show a balanced, dual-sided view of the public's and internet's reactions.
- **Analysis:** Discuss what this trend shows about today's society or digital culture.
- **Call to Action:** Prompt viewers to discuss and share.
"""
        elif slot_number == 6:
            # Slot 6: Devotional Stories
            # Get the active day
            day_number = (datetime.now(config.IST).day - 1) % 30 + 1
            story = DEVOTIONAL_CALENDAR[day_number - 1]
            
            prompt = base_instructions + f"""
## SLOT SPECIFICS: SLOT 6 — DEVOTIONAL STORIES (Krishna & Indian Gods)
- **Reference Channels:** Spiritual Talks, Mahabharat Stories, ShriKrishna Katha, Bhakti Sagar (saffron/gold themes, soft glows)
- **Visual Cue Style:** Divine paintings, temple bells, holy fire, lotuses, glowing icons of deities (Krishna with flute, Shiva meditating, divine rays).
- **Narrative Style:** Slow, peaceful, respectful, and story-telling (katha) tone.
- **Narration Duration:** 8-15 minutes total.

## SCRIPT FORMAT REQUIREMENTS:
- **Opening:** Start with a Sanskrit devotional shloka or mantra relevant to the deity ({story['deity']}), followed by its meaning in Kannada.
- **Story Introduction:** Introduce today's katha: "{story['title']}".
- **Narration:** Write a slow, detailed, and respectful katha of "{story['title']}" based on {story['source']}. Tell the story of {story['focus']} using rich Kannada narration.
- **Life Lesson:** Dedicate a section explaining: "ಈ ಕಥೆಯಿಂದ ನಾವು ಕಲಿಯಬೇಕಾದ ನೀತಿಪಾಠವೇನು?" (What life lesson/moral do we learn from this story?).
- **Closing:** End with a respectful devotional chant (e.g., "ಜೈ ಶ್ರೀ ಕೃಷ್ಣ" / "ಹರ ಹರ ಮಹಾದೇವ" depending on the deity {story['deity']}) and a subscribe prompt.
"""
        else:
            # Fallback
            prompt = base_instructions + f"\n## BULLETINS\n{self._format_news_for_prompt(news_data)}"

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
