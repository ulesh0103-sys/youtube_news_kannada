"""
news_scraper.py - RSS News Fetcher & Categorizer
==================================================

This module fetches news articles from configured RSS feeds, categorizes
them by region (Karnataka, National, International), extracts keywords
for B-roll searches, and returns structured data ready for script generation.

Usage:
    from news_scraper import scrape_news
    news_data = scrape_news()
    # news_data = {
    #     "karnataka": [NewsArticle, ...],
    #     "national": [NewsArticle, ...],
    #     "international": [NewsArticle, ...],
    #     "scraped_at": "2026-06-02T20:30:00+05:30"
    # }
"""

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional

import feedparser
import requests
from dateutil import parser as dateutil_parser

import config

logger = logging.getLogger(__name__)

# =============================================================================
# CONSTANTS
# =============================================================================
REQUEST_TIMEOUT = 10  # seconds
# Common stop words to exclude from keyword extraction
_STOP_WORDS = frozenset({
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "is", "are", "was", "were", "be", "been",
    "being", "have", "has", "had", "do", "does", "did", "will", "would",
    "shall", "should", "may", "might", "can", "could", "not", "no", "nor",
    "so", "if", "then", "than", "that", "this", "these", "those", "it",
    "its", "he", "she", "they", "we", "you", "i", "me", "him", "her",
    "us", "them", "my", "your", "his", "our", "their", "what", "which",
    "who", "whom", "how", "when", "where", "why", "all", "each", "every",
    "both", "few", "more", "most", "other", "some", "such", "only", "own",
    "same", "also", "very", "just", "about", "above", "after", "again",
    "as", "up", "out", "off", "over", "under", "into", "through", "during",
    "before", "between", "here", "there", "once", "new", "said", "says",
    "news", "report", "reports", "according", "amid", "per", "via",
})


# =============================================================================
# DATA MODEL
# =============================================================================
@dataclass
class NewsArticle:
    """Represents a single news article scraped from an RSS feed.

    Attributes:
        title: The headline of the article.
        summary: A brief description or first paragraph.
        source: Name of the news source (e.g. 'The Hindu').
        category: Region category — 'karnataka', 'national', or 'international'.
        link: URL to the full article.
        published_date: Publication datetime (timezone-aware if available).
        keywords: Extracted keywords useful for B-roll video search.
    """
    title: str
    summary: str
    source: str
    category: str
    link: str
    published_date: Optional[datetime] = None
    keywords: List[str] = field(default_factory=list)

    def __repr__(self) -> str:
        date_str = (
            self.published_date.strftime("%Y-%m-%d %H:%M")
            if self.published_date
            else "unknown date"
        )
        return (
            f"NewsArticle(title={self.title!r}, source={self.source!r}, "
            f"category={self.category!r}, date={date_str})"
        )


# =============================================================================
# NEWS SCRAPER CLASS
# =============================================================================
class NewsScraper:
    """Fetches and categorizes news articles from configured RSS feeds.

    This scraper iterates over all RSS feed URLs defined in ``config.RSS_FEEDS``,
    parses each feed with ``feedparser``, and returns structured
    ``NewsArticle`` objects grouped by category.

    Example:
        >>> scraper = NewsScraper()
        >>> all_news = scraper.fetch_all_feeds()
        >>> for article in all_news["karnataka"][:3]:
        ...     print(article.title)
    """

    def __init__(self):
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        })
        logger.info("NewsScraper initialized.")

    # --------------------------------------------------------------------- #
    # PUBLIC METHODS
    # --------------------------------------------------------------------- #

    def fetch_feed(self, url: str) -> List[dict]:
        """Fetch and parse a single RSS feed URL.

        Args:
            url: The RSS/Atom feed URL to fetch.

        Returns:
            A list of raw feed entry dicts from ``feedparser``.
            Returns an empty list on any network or parsing error.
        """
        logger.debug("Fetching feed: %s", url)
        try:
            response = self._session.get(url, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
        except requests.exceptions.Timeout:
            logger.warning("Timeout fetching feed: %s (limit=%ds)", url, REQUEST_TIMEOUT)
            return []
        except requests.exceptions.ConnectionError as exc:
            logger.warning("Connection error for feed %s: %s", url, exc)
            return []
        except requests.exceptions.HTTPError as exc:
            logger.warning("HTTP error for feed %s: %s", url, exc)
            return []
        except requests.exceptions.RequestException as exc:
            logger.error("Unexpected error fetching feed %s: %s", url, exc)
            return []

        feed = feedparser.parse(response.content)

        if feed.bozo and feed.bozo_exception:
            logger.warning(
                "Feed parsing issue for %s: %s (continuing with partial data)",
                url,
                feed.bozo_exception,
            )

        entries = feed.get("entries", [])
        logger.info("Fetched %d entries from %s", len(entries), url)
        return entries

    def fetch_all_feeds(self) -> Dict[str, List[NewsArticle]]:
        """Fetch articles from all configured RSS feeds, grouped by category.

        Returns:
            A dict with keys ``'karnataka'``, ``'national'``, ``'international'``,
            each mapping to a list of ``NewsArticle`` objects sorted by
            published date (newest first).
        """
        all_news: Dict[str, List[NewsArticle]] = {
            "karnataka": [],
            "national": [],
            "international": [],
        }

        for category, feed_urls in config.RSS_FEEDS.items():
            logger.info("--- Scraping category: %s (%d feeds) ---", category, len(feed_urls))
            for url in feed_urls:
                entries = self.fetch_feed(url)
                for entry in entries:
                    try:
                        article = self._categorize_article(entry, category)
                        all_news[category].append(article)
                    except Exception as exc:
                        logger.warning(
                            "Skipping malformed entry from %s: %s", url, exc
                        )

            # Sort by published date (newest first); articles without dates go last
            all_news[category].sort(
                key=lambda a: a.published_date or datetime.min.replace(tzinfo=timezone.utc),
                reverse=True,
            )
            logger.info(
                "Category '%s': %d total articles collected.",
                category,
                len(all_news[category]),
            )

        return all_news

    def get_top_stories(
        self,
        news_data: Dict[str, List[NewsArticle]],
        category: str,
        count: int = 3,
    ) -> List[NewsArticle]:
        """Return the top N articles for a given category.

        Articles are assumed to already be sorted by date (newest first)
        from ``fetch_all_feeds()``.

        Args:
            news_data: The dict returned by ``fetch_all_feeds()``.
            category: One of 'karnataka', 'national', 'international'.
            count: Number of top stories to return (default: 3).

        Returns:
            A list of up to ``count`` ``NewsArticle`` objects.
        """
        articles = news_data.get(category, [])
        top = articles[:count]
        logger.info(
            "Top %d stories for '%s': %s",
            len(top),
            category,
            [a.title[:50] for a in top],
        )
        return top

    def scrape_all(self, count: int = 3) -> Dict[str, List[dict]]:
        """Fetch all feeds and return serialized dicts of top stories.

        Args:
            count: Number of top stories to return per category.

        Returns:
            A dict with keys 'karnataka', 'national', 'international', each
            containing a list of serialized NewsArticle dicts.
        """
        all_news = self.fetch_all_feeds()
        result = {}
        for category in ("karnataka", "national", "international"):
            top_articles = self.get_top_stories(all_news, category, count=count)
            result[category] = []
            for a in top_articles:
                result[category].append({
                    "title": a.title,
                    "summary": a.summary,
                    "source": a.source,
                    "category": a.category,
                    "link": a.link,
                    "published_date": a.published_date.isoformat() if a.published_date else None,
                    "keywords": a.keywords,
                })
        return result

    # --------------------------------------------------------------------- #
    # PRIVATE HELPERS
    # --------------------------------------------------------------------- #

    def _categorize_article(self, entry: dict, category: str) -> NewsArticle:
        """Convert a raw feedparser entry into a ``NewsArticle``.

        Args:
            entry: A single entry dict from feedparser.
            category: The category label for this article.

        Returns:
            A fully populated ``NewsArticle`` object.

        Raises:
            ValueError: If the entry is missing a title.
        """
        title = entry.get("title", "").strip()
        if not title:
            raise ValueError("Entry has no title — skipping.")

        # Extract summary — try 'summary', then 'description', then fallback
        summary_raw = entry.get("summary", entry.get("description", ""))
        # Strip HTML tags from summary
        summary = re.sub(r"<[^>]+>", "", summary_raw).strip()
        # Truncate overly long summaries
        if len(summary) > 500:
            summary = summary[:497] + "..."

        # Determine source name from feed metadata
        source = ""
        if "source" in entry and "title" in entry["source"]:
            source = entry["source"]["title"]
        elif "feed" in entry and "title" in entry["feed"]:
            source = entry["feed"]["title"]
        else:
            # Derive source from link domain
            link = entry.get("link", "")
            domain_match = re.search(r"https?://(?:www\.)?([^/]+)", link)
            source = domain_match.group(1) if domain_match else "Unknown"

        link = entry.get("link", "")

        # Parse published date
        published_date = self._parse_date(entry)

        # Extract keywords from title + summary
        combined_text = f"{title} {summary}"
        keywords = self._extract_keywords(combined_text)

        return NewsArticle(
            title=title,
            summary=summary,
            source=source,
            category=category,
            link=link,
            published_date=published_date,
            keywords=keywords,
        )

    @staticmethod
    def _parse_date(entry: dict) -> Optional[datetime]:
        """Try to parse a publication date from an RSS entry.

        Attempts multiple date fields and uses ``dateutil.parser`` for
        flexible parsing. Returns ``None`` if no date can be determined.
        """
        for date_field in ("published", "updated", "created"):
            raw_date = entry.get(date_field)
            if raw_date:
                try:
                    return dateutil_parser.parse(raw_date)
                except (ValueError, OverflowError):
                    continue

        # feedparser sometimes pre-parses into a time struct
        for parsed_field in ("published_parsed", "updated_parsed"):
            time_struct = entry.get(parsed_field)
            if time_struct:
                try:
                    return datetime(*time_struct[:6], tzinfo=timezone.utc)
                except (TypeError, ValueError):
                    continue

        return None

    @staticmethod
    def _extract_keywords(text: str) -> List[str]:
        """Extract simple keywords from text for B-roll video search.

        This is a lightweight keyword extractor that:
        1. Tokenizes the text into words.
        2. Removes stop words and short tokens.
        3. Returns the most frequently occurring meaningful words.

        Args:
            text: The input text (title + summary).

        Returns:
            A list of up to 5 keywords, ordered by frequency (descending).
        """
        # Normalize: lowercase, keep only alphanumeric and spaces
        cleaned = re.sub(r"[^a-zA-Z0-9\s]", " ", text.lower())
        tokens = cleaned.split()

        # Filter out stop words and very short tokens
        meaningful = [
            tok for tok in tokens
            if tok not in _STOP_WORDS and len(tok) > 2
        ]

        # Count frequencies
        freq: Dict[str, int] = {}
        for tok in meaningful:
            freq[tok] = freq.get(tok, 0) + 1

        # Sort by frequency descending, then alphabetically for ties
        sorted_keywords = sorted(freq.keys(), key=lambda k: (-freq[k], k))

        return sorted_keywords[:5]


# =============================================================================
# CONVENIENCE FUNCTION
# =============================================================================

def scrape_news() -> dict:
    """Convenience function that scrapes all feeds and returns structured data.

    Returns:
        A dict with keys:
          - ``'karnataka'``: list of top 3 NewsArticle dicts
          - ``'national'``: list of top 3 NewsArticle dicts
          - ``'international'``: list of top 3 NewsArticle dicts
          - ``'all'``: full dict of all articles by category
          - ``'scraped_at'``: ISO timestamp of when scraping completed

        Each article dict in the top-stories lists contains:
        ``title``, ``summary``, ``source``, ``category``, ``link``,
        ``published_date``, ``keywords``.
    """
    scraper = NewsScraper()
    all_news = scraper.fetch_all_feeds()

    def _article_to_dict(article: NewsArticle) -> dict:
        """Serialize a NewsArticle to a plain dict for JSON compatibility."""
        return {
            "title": article.title,
            "summary": article.summary,
            "source": article.source,
            "category": article.category,
            "link": article.link,
            "published_date": (
                article.published_date.isoformat()
                if article.published_date
                else None
            ),
            "keywords": article.keywords,
        }

    result = {
        "karnataka": [
            _article_to_dict(a)
            for a in scraper.get_top_stories(all_news, "karnataka", count=3)
        ],
        "national": [
            _article_to_dict(a)
            for a in scraper.get_top_stories(all_news, "national", count=3)
        ],
        "international": [
            _article_to_dict(a)
            for a in scraper.get_top_stories(all_news, "international", count=3)
        ],
        "all": {
            cat: [_article_to_dict(a) for a in articles]
            for cat, articles in all_news.items()
        },
        "scraped_at": datetime.now(config.IST).isoformat(),
    }

    total = sum(len(v) for v in all_news.values())
    logger.info(
        "Scraping complete: %d total articles, %d top stories selected.",
        total,
        sum(len(result[cat]) for cat in ("karnataka", "national", "international")),
    )

    return result


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
    print("  YouTube News Automation — RSS Scraper Test Run")
    print("=" * 70)

    news_data = scrape_news()

    print(f"\nScraping completed at: {news_data['scraped_at']}")
    print("-" * 70)

    for category in ("karnataka", "national", "international"):
        stories = news_data[category]
        print(f"\n📰 {category.upper()} — Top {len(stories)} Stories:")
        for i, story in enumerate(stories, 1):
            print(f"  {i}. {story['title'][:80]}")
            print(f"     Source: {story['source']} | Keywords: {story['keywords']}")
            if story["summary"]:
                print(f"     Summary: {story['summary'][:120]}...")
            print()

    # Print total counts from all feeds
    print("-" * 70)
    for category, articles in news_data["all"].items():
        print(f"  Total {category}: {len(articles)} articles")
    print("=" * 70)
