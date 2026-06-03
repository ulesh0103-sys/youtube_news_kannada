"""
thumbnail_maker.py - YouTube Thumbnail Auto-Generator using Pillow

Generates eye-catching YouTube thumbnails for news videos with:
    - Dark gradient backgrounds (dark blue → dark red)
    - Bold headline text with auto-sizing (supports Kannada Unicode)
    - Semi-transparent red banner for headline area
    - Channel name watermark
    - LIVE / BREAKING badges
    - Date stamp overlay

All rendering done with Pillow — completely free, no paid APIs.

Dependencies:
    - Pillow (pip install Pillow)
"""

from PIL import Image, ImageDraw, ImageFont, ImageFilter
import os
import logging
import re
import time
import urllib.request
import urllib.parse
import json
from datetime import datetime
from typing import Optional, Dict, Any, List

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

# ─── Constants ────────────────────────────────────────────────────────────────
THUMBNAIL_WIDTH = 1280
THUMBNAIL_HEIGHT = 720
JPEG_QUALITY = 95

# Default color scheme
COLOR_GRADIENT_START = (10, 10, 46)     # Dark blue (#0a0a2e)
COLOR_GRADIENT_END = (26, 10, 10)       # Dark red (#1a0a0a)
COLOR_BANNER = (200, 30, 30, 180)       # Semi-transparent red
COLOR_TEXT_WHITE = (255, 255, 255)
COLOR_TEXT_SHADOW = (0, 0, 0)
COLOR_BADGE_RED = (220, 20, 20)
COLOR_BADGE_YELLOW = (255, 200, 0)
COLOR_DATE_BG = (0, 0, 0, 150)

# Category color presets
CATEGORY_COLORS = {
    "karnataka": {"banner": (200, 30, 30, 180), "accent": (255, 50, 50)},
    "national": {"banner": (30, 80, 200, 180), "accent": (50, 100, 255)},
    "international": {"banner": (30, 150, 80, 180), "accent": (50, 200, 100)},
    "sports": {"banner": (200, 150, 30, 180), "accent": (255, 200, 50)},
    "technology": {"banner": (100, 30, 200, 180), "accent": (150, 50, 255)},
}

# Font search list (priority order)
FONT_CANDIDATES = [
    # Kannada fonts
    "NotoSansKannada-Bold.ttf",
    "NotoSansKannada-Regular.ttf",
    "Tunga Bold",
    "Tunga",
    "tungab.ttf",
    "tunga.ttf",
    # Fallback fonts
    "arialbd.ttf",
    "arial.ttf",
    "Impact",
    "DejaVuSans-Bold.ttf",
    "DejaVuSans.ttf",
    "LiberationSans-Bold.ttf",
]


class ThumbnailMaker:
    """
    Auto-generates YouTube thumbnails optimized for news content.

    Creates visually appealing thumbnails with gradient backgrounds,
    headline text with auto-sizing, channel branding, and optional
    LIVE/BREAKING badges.

    Usage:
        >>> maker = ThumbnailMaker()
        >>> path = maker.create_thumbnail(
        ...     headline="ಕರ್ನಾಟಕದಲ್ಲಿ ಭಾರೀ ಮಳೆ",
        ...     output_path="output/thumbnail.jpg"
        ... )
    """

    def __init__(self):
        """
        Initialize ThumbnailMaker with dimensions, fonts, and channel info.
        """
        self.width = THUMBNAIL_WIDTH
        self.height = THUMBNAIL_HEIGHT

        # Channel name from config
        self.channel_name = "News Channel"
        if config and hasattr(config, "CHANNEL_NAME"):
            self.channel_name = config.CHANNEL_NAME

        # Locate fonts
        self.font_path = self._find_font()
        if self.font_path:
            logger.info("Using font: %s", self.font_path)
        else:
            logger.warning(
                "No suitable font found. Thumbnails will use PIL default font. "
                "For best results, install Noto Sans Kannada."
            )

        logger.info(
            "ThumbnailMaker initialized: %dx%d, channel='%s'",
            self.width, self.height, self.channel_name,
        )

    def _search_pexels(self, query: str) -> Optional[str]:
        """Search Pexels API for a stock photo matching the query and download it."""
        api_key = ""
        if config and hasattr(config, "PEXELS_API_KEY") and config.PEXELS_API_KEY:
            api_key = config.PEXELS_API_KEY
        if not api_key:
            api_key = os.environ.get("PEXELS_API_KEY", "")
            
        if not api_key:
            logger.warning("Pexels API key is not configured. Skipping Pexels image search.")
            return None
            
        try:
            url = f"https://api.pexels.com/v1/search?query={urllib.parse.quote(query)}&per_page=1"
            req = urllib.request.Request(url)
            req.add_header("Authorization", api_key)
            req.add_header("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
            
            logger.info("Searching Pexels for keyword: '%s'", query)
            with urllib.request.urlopen(req, timeout=10) as response:
                res_data = json.loads(response.read().decode())
                photos = res_data.get("photos", [])
                if photos:
                    photo_url = photos[0].get("src", {}).get("large2x") or photos[0].get("src", {}).get("large")
                    if photo_url:
                        logger.info("Found Pexels photo: %s", photo_url)
                        temp_dir = config.PATHS.get("temp", "temp/") if config else "temp/"
                        os.makedirs(temp_dir, exist_ok=True)
                        temp_path = os.path.join(temp_dir, f"pexels_{int(time.time())}.jpg")
                        
                        # Download image
                        img_req = urllib.request.Request(photo_url)
                        img_req.add_header("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
                        with urllib.request.urlopen(img_req, timeout=15) as img_response:
                            with open(temp_path, "wb") as f:
                                f.write(img_response.read())
                        return temp_path
                else:
                    logger.warning("No Pexels photo found for query '%s'", query)
        except Exception as e:
            logger.warning("Error fetching/downloading Pexels image for query '%s': %s", query, e)
            
        return None

    def _get_slot_styles(self, slot_num: int) -> dict:
        """Get slot-specific color schemes and layouts."""
        # Palettes: gradient_start, gradient_end, accent, badge_text, badge_bg, text_color
        styles = {
            1: {
                "gradient_start": (80, 5, 5),      # Dark Red
                "gradient_end": (15, 0, 0),        # Near Black
                "accent": (255, 30, 30),           # Bright Red
                "badge_text": "LIVE",
                "badge_bg": (220, 20, 20),
                "text_color": (255, 255, 255),
                "title_label": "BREAKING NEWS"
            },
            2: {
                "gradient_start": (45, 0, 0),      # Dark Crimson
                "gradient_end": (10, 10, 10),      # Jet Black
                "accent": (180, 10, 10),           # Deep Red
                "badge_text": "CRIME STORY",
                "badge_bg": (180, 10, 10),
                "text_color": (255, 200, 200),
                "title_label": "TRUE CRIME CASE"
            },
            3: {
                "gradient_start": (100, 35, 0),    # Dark Orange
                "gradient_end": (30, 15, 0),       # Dark Brownish Orange
                "accent": (255, 102, 0),           # Orange
                "badge_text": "NEWS UPDATE",
                "badge_bg": (255, 102, 0),
                "text_color": (255, 255, 255),
                "title_label": "EVENING BULLET"
            },
            4: {
                "gradient_start": (85, 0, 51),     # Deep Pink
                "gradient_end": (0, 51, 68),       # Dark Cyan
                "accent": (255, 0, 127),           # Neon Pink
                "badge_text": "VIRAL!",
                "badge_bg": (255, 0, 127),
                "text_color": (0, 240, 255),
                "title_label": "TRENDING NOW"
            },
            5: {
                "gradient_start": (0, 34, 68),     # Twitter Blue
                "gradient_end": (5, 5, 21),        # Dark Navy
                "accent": (0, 136, 204),           # Bright Blue
                "badge_text": "BUZZ",
                "badge_bg": (0, 136, 204),
                "text_color": (255, 255, 255),
                "title_label": "SOCIAL MEDIA EXPLAINER"
            },
            6: {
                "gradient_start": (120, 30, 0),    # Saffron
                "gradient_end": (45, 15, 0),       # Deep Gold
                "accent": (255, 153, 0),           # Gold
                "badge_text": "DEVOTIONAL",
                "badge_bg": (255, 120, 0),
                "text_color": (255, 215, 0),       # Gold
                "title_label": "SACRED KATHA"
            }
        }
        return styles.get(slot_num, styles[1])

    def create(self, script_data: dict, output_path: str) -> str:
        """
        Wrapper to generate thumbnail from script data, compatible with the master orchestrator.
        """
        slot_number = script_data.get("slot_number", 1)
        headline = script_data.get("thumbnail_headline", "")
        
        if not headline:
            sections = script_data.get("sections", [])
            if sections:
                headline = sections[0].get("headline", "")
            if not headline:
                headline = script_data.get("title", "ಪ್ರಮುಖ ಸುದ್ದಿಗಳು")

        if len(headline) > 80:
            headline = headline[:77] + "..."

        # Determine Pexels search query
        query = ""
        # Try to extract English keywords
        keywords = []
        for sec in script_data.get("sections", []):
            kw_list = sec.get("broll_keywords", [])
            if isinstance(kw_list, list):
                for kw in kw_list:
                    if re.search(r'[a-zA-Z]', kw):
                        keywords.append(kw)
        if keywords:
            seen = set()
            unique_kws = [x for x in keywords if not (x in seen or seen.add(x))]
            query = " ".join(unique_kws[:2])
            
        if not query:
            defaults = {
                1: "news studio desk",
                2: "crime scene police",
                3: "business stock market news",
                4: "shocked face expression",
                5: "social media buzz phone",
                6: "indian temple priest"
            }
            query = defaults.get(slot_number, "news")
            if slot_number == 6:
                full_text = (script_data.get("title", "") + " " + script_data.get("description", "")).lower()
                if "krishna" in full_text or "ಕೃಷ್ಣ" in full_text:
                    query = "lord krishna painting"
                elif "shiva" in full_text or "ಶಿವ" in full_text:
                    query = "lord shiva statue"
                elif "rama" in full_text or "ರಾಮ" in full_text:
                    query = "lord rama statue"
                elif "hanuman" in full_text or "ಹನುಮಾನ್" in full_text:
                    query = "lord hanuman painting"
                elif "devi" in full_text or "ದೇವಿ" in full_text:
                    query = "goddess durga"
                elif "ganesh" in full_text or "ಗಣೇಶ" in full_text:
                    query = "lord ganesha"

        # Search and download image
        bg_image_path = self._search_pexels(query)
        
        try:
            return self.create_thumbnail(
                headline=headline,
                output_path=output_path,
                slot_number=slot_number,
                bg_image_path=bg_image_path
            )
        finally:
            # Clean up temp image
            if bg_image_path and os.path.exists(bg_image_path):
                try:
                    os.remove(bg_image_path)
                    logger.debug("Cleaned up temp Pexels background image: %s", bg_image_path)
                except Exception as e:
                    logger.warning("Failed to remove temp Pexels image: %s", e)

    def create_thumbnail(
        self,
        headline: str,
        output_path: str,
        category_color: str = None,
        badge: str = None,
        slot_number: int = 1,
        bg_image_path: str = None,
    ) -> str:
        """
        Generate a complete YouTube thumbnail image.
        """
        if not headline or not headline.strip():
            raise ValueError("Headline text cannot be empty.")

        # Ensure output directory exists
        output_dir = os.path.dirname(output_path)
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)

        logger.info("Creating thumbnail (Slot %d): '%s'", slot_number, headline[:50])

        style = self._get_slot_styles(slot_number)

        # ── Step 1: Create gradient background ────────────────────────────
        img = self._create_gradient(
            self.width, self.height,
            style["gradient_start"], style["gradient_end"],
        )

        # Convert to RGBA for transparency support
        img = img.convert("RGBA")
        
        # ── Step 2: Blend Pexels stock photo ──────────────────────────────
        if bg_image_path and os.path.exists(bg_image_path):
            try:
                bg_img = Image.open(bg_image_path).convert("RGBA")
                
                # Crop and resize to 60% width of canvas
                target_w = int(self.width * 0.6)
                target_h = self.height
                
                bg_w, bg_h = bg_img.size
                ratio = max(target_w / bg_w, target_h / bg_h)
                new_size = (int(bg_w * ratio), int(bg_h * ratio))
                bg_img = bg_img.resize(new_size, Image.Resampling.LANCZOS)
                
                # Crop center
                left = (bg_img.size[0] - target_w) // 2
                top = (bg_img.size[1] - target_h) // 2
                bg_img = bg_img.crop((left, top, left + target_w, top + target_h))
                
                # Gradient mask for smooth horizontal fade
                mask = Image.new("L", (target_w, target_h), 255)
                for x in range(target_w):
                    if x < 180:
                        alpha = int((x / 180) * 255)
                        for y in range(target_h):
                            mask.putpixel((x, y), alpha)
                            
                img.paste(bg_img, (self.width - target_w, 0), mask=mask)
                logger.info("Blended Pexels background successfully.")
            except Exception as e:
                logger.warning("Failed to blend background image: %s", e)

        draw = ImageDraw.Draw(img)

        # ── Step 3: Draw text on the left side ────────────────────────────
        text_area_width = int(self.width * 0.48) # Limit text to left half
        font, font_size = self._fit_text(
            draw, headline, self.font_path,
            max_width=text_area_width,
            max_font_size=65,
            min_font_size=32,
        )
        
        wrapped_text = self._wrap_text(draw, headline, font, text_area_width)
        
        # Calculate text height for vertical centering
        bbox = draw.multiline_textbbox((0, 0), wrapped_text, font=font, spacing=8)
        text_h = bbox[3] - bbox[1]
        
        text_x = 60
        text_y = (self.height - text_h) // 2
        if text_y < 130:
            text_y = 130
            
        shadow_color = (0, 0, 0)
        if slot_number == 6:
            shadow_color = (60, 20, 0)
            
        self._add_text_with_shadow(
            draw,
            position=(text_x, text_y),
            text=wrapped_text,
            font=font,
            fill=style["text_color"],
            shadow_color=shadow_color,
            shadow_offset=4,
        )

        # ── Step 4: Add channel name watermark ────────────────────────────
        watermark_font = self._load_font(20)
        watermark_text = self.channel_name

        # Position in top-right corner
        wm_bbox = draw.textbbox((0, 0), watermark_text, font=watermark_font)
        wm_width = wm_bbox[2] - wm_bbox[0]
        wm_x = self.width - wm_width - 20
        wm_y = 15

        # Semi-transparent background for watermark
        wm_bg = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0))
        wm_bg_draw = ImageDraw.Draw(wm_bg)
        wm_bg_draw.rectangle(
            [(wm_x - 10, wm_y - 5), (wm_x + wm_width + 10, wm_y + 30)],
            fill=(0, 0, 0, 120),
        )
        img = Image.alpha_composite(img, wm_bg)
        draw = ImageDraw.Draw(img)

        draw.text(
            (wm_x, wm_y),
            watermark_text,
            font=watermark_font,
            fill=(255, 255, 255, 200),
        )

        # ── Step 5: Add slot-specific badge ─────────────────────────────
        badge_text = badge.upper() if badge else style["badge_text"]
        badge_font = self._load_font(24)

        b_bbox = draw.textbbox((0, 0), badge_text, font=badge_font)
        b_width = b_bbox[2] - b_bbox[0]
        b_height = b_bbox[3] - b_bbox[1]

        badge_x = 60
        badge_y = 35
        padding = 10

        bg_color = style["badge_bg"]

        badge_bg = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0))
        badge_bg_draw = ImageDraw.Draw(badge_bg)
        
        # Check if badge needs a border (like Slot 2 crime story)
        border_color = style.get("badge_border", None)
        outline_args = {"outline": border_color, "width": 2} if border_color else {}
        
        badge_bg_draw.rounded_rectangle(
            [
                (badge_x, badge_y),
                (badge_x + b_width + padding * 2, badge_y + b_height + padding * 2),
            ],
            radius=6,
            fill=(*bg_color, 230) if len(bg_color) == 3 else bg_color,
            **outline_args
        )
        img = Image.alpha_composite(img, badge_bg)
        draw = ImageDraw.Draw(img)

        # Draw badge text
        draw.text(
            (badge_x + padding, badge_y + padding),
            badge_text,
            font=badge_font,
            fill=COLOR_TEXT_WHITE,
        )

        # ── Step 6: Add date stamp ────────────────────────────────────────
        date_text = datetime.now().strftime("%d %b %Y")
        date_font = self._load_font(18)

        d_bbox = draw.textbbox((0, 0), date_text, font=date_font)
        d_width = d_bbox[2] - d_bbox[0]

        date_x = 60
        date_y = self.height - 50

        # Date background
        date_bg = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0))
        date_bg_draw = ImageDraw.Draw(date_bg)
        date_bg_draw.rectangle(
            [(date_x - 8, date_y - 4), (date_x + d_width + 8, date_y + 24)],
            fill=COLOR_DATE_BG,
        )
        img = Image.alpha_composite(img, date_bg)
        draw = ImageDraw.Draw(img)

        draw.text(
            (date_x, date_y),
            date_text,
            font=date_font,
            fill=(200, 200, 200, 255),
        )

        # ── Step 7: Save as high-quality JPEG ─────────────────────────────
        # Convert RGBA → RGB for JPEG output
        final = Image.new("RGB", img.size, (0, 0, 0))
        final.paste(img, mask=img.split()[3])

        try:
            final.save(output_path, "JPEG", quality=JPEG_QUALITY, optimize=True)
            file_size_kb = os.path.getsize(output_path) / 1024
            logger.info(
                "Thumbnail saved: %s (%.1f KB, %dx%d)",
                output_path, file_size_kb, self.width, self.height,
            )
            return os.path.abspath(output_path)
        except Exception as e:
            logger.error("Failed to save thumbnail: %s", str(e))
            raise IOError(f"Cannot save thumbnail: {e}") from e

    def _create_gradient(
        self,
        width: int,
        height: int,
        color1: tuple,
        color2: tuple,
    ) -> Image.Image:
        """
        Create a vertical gradient image from color1 (top) to color2 (bottom).

        Also adds a subtle diagonal gradient for visual depth.

        Args:
            width: Image width in pixels.
            height: Image height in pixels.
            color1: RGB tuple for the top color (e.g., (10, 10, 46)).
            color2: RGB tuple for the bottom color (e.g., (26, 10, 10)).

        Returns:
            PIL Image with gradient fill.
        """
        img = Image.new("RGB", (width, height))
        pixels = img.load()

        for y in range(height):
            # Vertical gradient ratio
            ratio_y = y / height

            # Add subtle horizontal gradient component for diagonal effect
            for x in range(width):
                ratio_x = x / width
                ratio = ratio_y * 0.8 + ratio_x * 0.2  # Mostly vertical

                r = int(color1[0] + (color2[0] - color1[0]) * ratio)
                g = int(color1[1] + (color2[1] - color1[1]) * ratio)
                b = int(color1[2] + (color2[2] - color1[2]) * ratio)

                # Clamp values
                r = max(0, min(255, r))
                g = max(0, min(255, g))
                b = max(0, min(255, b))

                pixels[x, y] = (r, g, b)

        return img

    def _fit_text(
        self,
        draw: ImageDraw.Draw,
        text: str,
        font_path: str,
        max_width: int,
        max_font_size: int = 70,
        min_font_size: int = 30,
    ) -> tuple:
        """
        Find the optimal font size to fit text within a given width.

        Uses binary search to efficiently find the largest font size
        that keeps the text within max_width.

        Args:
            draw: PIL ImageDraw instance.
            text: Text to measure.
            font_path: Path to the font file.
            max_width: Maximum allowed text width in pixels.
            max_font_size: Largest font size to try.
            min_font_size: Smallest font size to accept.

        Returns:
            Tuple of (font, font_size) where font is a PIL ImageFont.
        """
        best_font = self._load_font(min_font_size)
        best_size = min_font_size

        for size in range(max_font_size, min_font_size - 1, -2):
            font = self._load_font(size)

            # Use multiline_textbbox for text that may wrap
            bbox = draw.multiline_textbbox(
                (0, 0), text, font=font, spacing=8
            )
            text_width = bbox[2] - bbox[0]

            if text_width <= max_width:
                best_font = font
                best_size = size
                break

        # If text still too wide at min size, try wrapping
        if best_size == min_font_size:
            wrapped = self._wrap_text(draw, text, best_font, max_width)
            if wrapped != text:
                text = wrapped  # The calling code should use wrapped text
                logger.info("Text wrapped to fit: %d chars", len(wrapped))

        logger.info("Selected font size: %d for text length %d", best_size, len(text))
        return best_font, best_size

    @staticmethod
    def _wrap_text(
        draw: ImageDraw.Draw, text: str, font: ImageFont.FreeTypeFont, max_width: int
    ) -> str:
        """
        Wrap text to fit within a maximum pixel width.

        Args:
            draw: PIL ImageDraw instance for text measurement.
            text: Text to wrap.
            font: Font to use for measuring.
            max_width: Maximum width in pixels per line.

        Returns:
            Text with newlines inserted for wrapping.
        """
        words = text.split()
        lines = []
        current_line = []

        for word in words:
            test_line = " ".join(current_line + [word])
            bbox = draw.textbbox((0, 0), test_line, font=font)
            line_width = bbox[2] - bbox[0]

            if line_width <= max_width:
                current_line.append(word)
            else:
                if current_line:
                    lines.append(" ".join(current_line))
                current_line = [word]

        if current_line:
            lines.append(" ".join(current_line))

        return "\n".join(lines)

    def _add_text_with_shadow(
        self,
        draw: ImageDraw.Draw,
        position: tuple,
        text: str,
        font: ImageFont.FreeTypeFont,
        fill: tuple,
        shadow_color: tuple,
        shadow_offset: int = 3,
    ):
        """
        Draw text with a drop shadow for improved readability.

        The shadow is drawn first (offset), then the main text on top.

        Args:
            draw: PIL ImageDraw instance.
            position: (x, y) tuple for text position.
            text: Text to draw.
            font: Font to use.
            fill: Main text color (RGB tuple).
            shadow_color: Shadow color (RGB tuple).
            shadow_offset: Pixel offset for shadow (default: 3).
        """
        x, y = position

        # Draw shadow (multiple offsets for thicker shadow)
        for dx in range(1, shadow_offset + 1):
            for dy in range(1, shadow_offset + 1):
                draw.multiline_text(
                    (x + dx, y + dy),
                    text,
                    font=font,
                    fill=(*shadow_color, 150),
                    spacing=8,
                )

        # Draw main text
        draw.multiline_text(
            (x, y),
            text,
            font=font,
            fill=fill,
            spacing=8,
        )

    def _load_font(self, size: int) -> ImageFont.FreeTypeFont:
        """
        Load a font at the specified size, with fallback to default.

        Args:
            size: Font size in points.

        Returns:
            PIL ImageFont instance.
        """
        if self.font_path:
            try:
                return ImageFont.truetype(self.font_path, size)
            except (OSError, IOError) as e:
                logger.warning("Failed to load font %s: %s", self.font_path, e)

        # Try common system fonts
        for font_name in ["arial.ttf", "arialbd.ttf", "DejaVuSans.ttf"]:
            try:
                return ImageFont.truetype(font_name, size)
            except (OSError, IOError):
                continue

        # Ultimate fallback: PIL default bitmap font
        logger.warning("Using PIL default font (limited Unicode support).")
        return ImageFont.load_default()

    @staticmethod
    def _find_font() -> str:
        """
        Search for a suitable Kannada-capable font on the system.

        Checks common font directories across platforms.

        Returns:
            Absolute path to a font file, or empty string if not found.
        """
        font_dirs = [
            "assets/fonts/",
            "C:/Windows/Fonts/",
            "/usr/share/fonts/truetype/noto/",
            "/usr/share/fonts/truetype/",
            "/usr/share/fonts/",
            os.path.expanduser("~/.local/share/fonts/"),
            "/System/Library/Fonts/",
            "/Library/Fonts/",
        ]

        for font_dir in font_dirs:
            if not os.path.isdir(font_dir):
                continue
            for font_name in FONT_CANDIDATES:
                font_path = os.path.join(font_dir, font_name)
                if os.path.isfile(font_path):
                    return font_path

        return ""


# ─── Main: Test / Demo ───────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    if sys.platform.startswith("win"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
            sys.stderr.reconfigure(encoding="utf-8")
        except AttributeError:
            pass

    print("=" * 60)
    print("  Thumbnail Maker - Pillow Demo")
    print("=" * 60)

    os.makedirs("output", exist_ok=True)
    maker = ThumbnailMaker()

    # ── Test 1: Basic Kannada headline thumbnail ──────────────────────────
    print("\n[Test 1] Creating Kannada headline thumbnail...")
    try:
        path = maker.create_thumbnail(
            headline="ಕರ್ನಾಟಕದಲ್ಲಿ ಭಾರೀ ಮಳೆ ಎಚ್ಚರಿಕೆ",
            output_path="output/test_thumbnail_1.jpg",
            category_color="karnataka",
        )
        print(f"  ✓ Thumbnail saved: {path}")
    except Exception as e:
        print(f"  ✗ Error: {e}")

    # ── Test 2: Breaking news with badge ──────────────────────────────────
    print("\n[Test 2] Creating BREAKING news thumbnail...")
    try:
        path = maker.create_thumbnail(
            headline="ಪ್ರಧಾನ ಮಂತ್ರಿ ಮಹತ್ವದ ಘೋಷಣೆ",
            output_path="output/test_thumbnail_2.jpg",
            category_color="national",
            badge="BREAKING",
        )
        print(f"  ✓ Thumbnail saved: {path}")
    except Exception as e:
        print(f"  ✗ Error: {e}")

    # ── Test 3: LIVE badge thumbnail ──────────────────────────────────────
    print("\n[Test 3] Creating LIVE thumbnail...")
    try:
        path = maker.create_thumbnail(
            headline="International Summit Updates",
            output_path="output/test_thumbnail_3.jpg",
            category_color="international",
            badge="LIVE",
        )
        print(f"  ✓ Thumbnail saved: {path}")
    except Exception as e:
        print(f"  ✗ Error: {e}")

    # ── Test 4: Long text wrapping ────────────────────────────────────────
    print("\n[Test 4] Creating thumbnail with long headline...")
    try:
        path = maker.create_thumbnail(
            headline="ಬೆಂಗಳೂರಿನಲ್ಲಿ ಭಾರೀ ಮಳೆಯಿಂದ ಜನಜೀವನ ಅಸ್ತವ್ಯಸ್ತ - ಹಲವು ಪ್ರದೇಶಗಳಲ್ಲಿ ನೀರು ನಿಂತಿದೆ",
            output_path="output/test_thumbnail_4.jpg",
            category_color="karnataka",
            badge="BREAKING",
        )
        print(f"  ✓ Thumbnail saved: {path}")
    except Exception as e:
        print(f"  ✗ Error: {e}")

    print("\n" + "=" * 60)
    print("  Demo complete! Check the output/ directory for thumbnails.")
    print("=" * 60)
