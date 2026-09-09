"""Combined Anthropic RSS scraper."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from enum import StrEnum

import feedparser
import httpx
from pydantic import BaseModel, ConfigDict


class AnthropicTopic(StrEnum):
    NEWS = "news"
    RESEARCH = "research"
    ENGINEERING = "engineering"
    FRONTIER_RED_TEAM = "frontier_red_team"


ANTHROPIC_FEEDS: dict[AnthropicTopic, str] = {
    AnthropicTopic.NEWS: "https://raw.githubusercontent.com/Olshansk/rss-feeds/main/feeds/feed_anthropic_news.xml",
    AnthropicTopic.RESEARCH: "https://raw.githubusercontent.com/Olshansk/rss-feeds/main/feeds/feed_anthropic_research.xml",
    AnthropicTopic.ENGINEERING: "https://raw.githubusercontent.com/Olshansk/rss-feeds/main/feeds/feed_anthropic_engineering.xml",
    AnthropicTopic.FRONTIER_RED_TEAM: "https://raw.githubusercontent.com/Olshansk/rss-feeds/main/feeds/feed_anthropic_red.xml",
}


class AnthropicArticle(BaseModel):
    """One normalized article from an Anthropic feed."""

    model_config = ConfigDict(extra="forbid")

    title: str
    url: str
    article_id: str
    published_at: datetime
    description: str
    topic: AnthropicTopic


class AnthropicScraper:
    """Fetch and combine all configured Anthropic RSS feeds."""

    def __init__(
        self,
        *,
        feeds: dict[AnthropicTopic, str] | None = None,
        timeout: float = 20.0,
    ) -> None:
        self.feeds = feeds or ANTHROPIC_FEEDS
        self.timeout = timeout

    @staticmethod
    def _entry_datetime(entry: object) -> datetime:
        published = getattr(entry, "published_parsed", None) or getattr(
            entry, "updated_parsed", None
        )
        if published is None:
            raise ValueError("Anthropic RSS entry has no publication timestamp")
        return datetime(*published[:6], tzinfo=timezone.utc)

    def fetch_recent_articles(
        self,
        *,
        hours: int = 24,
        now: datetime | None = None,
    ) -> list[AnthropicArticle]:
        """Return articles from all Anthropic feeds within the time window."""
        current_time = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        cutoff = current_time - timedelta(hours=hours)
        articles: dict[str, AnthropicArticle] = {}

        for topic, feed_url in self.feeds.items():
            response = httpx.get(feed_url, timeout=self.timeout)
            response.raise_for_status()
            feed = feedparser.parse(response.text)
            if feed.bozo and not feed.entries:
                raise ValueError(f"Could not parse Anthropic {topic.value} RSS feed")

            for entry in feed.entries:
                published_at = self._entry_datetime(entry)
                if cutoff <= published_at <= current_time:
                    url = entry.get("link", "")
                    article = AnthropicArticle(
                        title=entry.get("title", "Untitled"),
                        url=url,
                        article_id=entry.get("guid", url),
                        published_at=published_at,
                        description=entry.get("summary", ""),
                        topic=topic,
                    )
                    articles[article.article_id] = article

        return sorted(articles.values(), key=lambda article: article.published_at, reverse=True)
