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
from datetime import datetime

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

    def create(self, script_data: dict, output_path: str) -> str:
        """
        Wrapper to generate thumbnail from script data, compatible with the master orchestrator.
        """
        sections = script_data.get("sections", [])
        headline = ""
        category = None

        if sections:
            headline = sections[0].get("headline", "")
            category = sections[0].get("category", None)

        if not headline:
            headline = script_data.get("title", "ಪ್ರಮುಖ ಸುದ್ದಿಗಳು")

        if len(headline) > 80:
            headline = headline[:77] + "..."

        badge = "LIVE"

        return self.create_thumbnail(
            headline=headline,
            output_path=output_path,
            category_color=category,
            badge=badge,
        )

    def create_thumbnail(
        self,
        headline: str,
        output_path: str,
        category_color: str = None,
        badge: str = None,
    ) -> str:
        """
        Generate a complete YouTube thumbnail image.

        Args:
            headline: Main headline text (supports Kannada Unicode).
            output_path: File path to save the thumbnail JPEG.
            category_color: Optional category key for color scheme
                           ('karnataka', 'national', 'international', etc.)
            badge: Optional badge text ('LIVE', 'BREAKING', etc.)

        Returns:
            Absolute path to the saved thumbnail file.

        Raises:
            ValueError: If headline is empty.
            IOError: If the file cannot be saved.
        """
        if not headline or not headline.strip():
            raise ValueError("Headline text cannot be empty.")

        # Ensure output directory exists
        output_dir = os.path.dirname(output_path)
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)

        logger.info("Creating thumbnail: '%s'", headline[:50])

        # ── Step 1: Create gradient background ────────────────────────────
        img = self._create_gradient(
            self.width, self.height,
            COLOR_GRADIENT_START, COLOR_GRADIENT_END,
        )

        # Convert to RGBA for transparency support
        img = img.convert("RGBA")
        draw = ImageDraw.Draw(img)

        # ── Step 2: Add decorative elements ───────────────────────────────
        # Diagonal accent lines for visual interest
        overlay = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0))
        overlay_draw = ImageDraw.Draw(overlay)

        # Subtle diagonal stripes
        for i in range(0, self.width + self.height, 80):
            overlay_draw.line(
                [(i, 0), (i - self.height, self.height)],
                fill=(255, 255, 255, 8),
                width=2,
            )

        img = Image.alpha_composite(img, overlay)
        draw = ImageDraw.Draw(img)

        # ── Step 3: Add semi-transparent banner at bottom ─────────────────
        banner_color = COLOR_BANNER
        if category_color and category_color in CATEGORY_COLORS:
            banner_color = CATEGORY_COLORS[category_color]["banner"]

        banner_overlay = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0))
        banner_draw = ImageDraw.Draw(banner_overlay)

        banner_top = self.height - 250
        banner_draw.rectangle(
            [(0, banner_top), (self.width, self.height)],
            fill=banner_color,
        )

        # Accent line above banner
        accent_color = (255, 50, 50)
        if category_color and category_color in CATEGORY_COLORS:
            accent_color = CATEGORY_COLORS[category_color]["accent"]
        banner_draw.rectangle(
            [(0, banner_top - 4), (self.width, banner_top)],
            fill=(*accent_color, 255) if len(accent_color) == 3 else accent_color,
        )

        img = Image.alpha_composite(img, banner_overlay)
        draw = ImageDraw.Draw(img)

        # ── Step 4: Add headline text with auto-sizing ────────────────────
        headline_area_width = self.width - 80  # 40px padding each side
        font, font_size = self._fit_text(
            draw, headline, self.font_path,
            max_width=headline_area_width,
            max_font_size=70,
            min_font_size=30,
        )

        # Calculate text position (centered in banner area)
        text_x = 40
        text_y = banner_top + 30

        # Draw text with shadow for readability
        self._add_text_with_shadow(
            draw,
            position=(text_x, text_y),
            text=headline,
            font=font,
            fill=COLOR_TEXT_WHITE,
            shadow_color=COLOR_TEXT_SHADOW,
        )

        # ── Step 5: Add channel name watermark ────────────────────────────
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

        # ── Step 6: Add LIVE / BREAKING badge ─────────────────────────────
        if badge:
            badge_text = badge.upper()
            badge_font = self._load_font(28)

            b_bbox = draw.textbbox((0, 0), badge_text, font=badge_font)
            b_width = b_bbox[2] - b_bbox[0]
            b_height = b_bbox[3] - b_bbox[1]

            badge_x = 20
            badge_y = 20
            padding = 12

            # Badge background color
            if "LIVE" in badge_text:
                bg_color = COLOR_BADGE_RED
            elif "BREAKING" in badge_text:
                bg_color = COLOR_BADGE_RED
            else:
                bg_color = COLOR_BADGE_YELLOW

            # Draw badge background (rounded rectangle via two rects + circles)
            badge_bg = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0))
            badge_bg_draw = ImageDraw.Draw(badge_bg)
            badge_bg_draw.rounded_rectangle(
                [
                    (badge_x, badge_y),
                    (badge_x + b_width + padding * 2, badge_y + b_height + padding * 2),
                ],
                radius=8,
                fill=(*bg_color, 230),
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

        # ── Step 7: Add date stamp ────────────────────────────────────────
        date_text = datetime.now().strftime("%d %b %Y")
        date_font = self._load_font(18)

        d_bbox = draw.textbbox((0, 0), date_text, font=date_font)
        d_width = d_bbox[2] - d_bbox[0]

        date_x = self.width - d_width - 20
        date_y = self.height - 40

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

        # ── Step 8: Save as high-quality JPEG ─────────────────────────────
        # Convert RGBA → RGB for JPEG output
        final = Image.new("RGB", img.size, (0, 0, 0))
        final.paste(img, mask=img.split()[3])  # Use alpha channel as mask

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
