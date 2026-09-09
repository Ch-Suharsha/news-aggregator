"""OpenAI News RSS scraper."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import feedparser
import httpx
from pydantic import BaseModel, ConfigDict

OPENAI_NEWS_RSS_URL = "https://openai.com/news/rss.xml"


class OpenAIArticle(BaseModel):
    """One article published in the OpenAI News RSS feed."""

    model_config = ConfigDict(extra="forbid")

    title: str
    url: str
    article_id: str
    published_at: datetime
    description: str
    category: str | None = None


class OpenAIScraper:
    """Fetch and normalize articles from OpenAI's public News RSS feed."""

    def __init__(self, *, timeout: float = 20.0) -> None:
        self.timeout = timeout

    @staticmethod
    def _entry_datetime(entry: object) -> datetime:
        published = getattr(entry, "published_parsed", None) or getattr(
            entry, "updated_parsed", None
        )
        if published is None:
            raise ValueError("OpenAI RSS entry has no publication timestamp")
        return datetime(*published[:6], tzinfo=timezone.utc)

    def fetch_recent_articles(
        self,
        *,
        hours: int = 24,
        now: datetime | None = None,
    ) -> list[OpenAIArticle]:
        """Return OpenAI News articles published within the last ``hours``."""
        response = httpx.get(OPENAI_NEWS_RSS_URL, timeout=self.timeout)
        response.raise_for_status()
        feed = feedparser.parse(response.text)
        if feed.bozo and not feed.entries:
            raise ValueError("Could not parse the OpenAI News RSS feed")

        current_time = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        cutoff = current_time - timedelta(hours=hours)
        articles: list[OpenAIArticle] = []
        for entry in feed.entries:
            published_at = self._entry_datetime(entry)
            if cutoff <= published_at <= current_time:
                url = entry.get("link", "")
                articles.append(
                    OpenAIArticle(
                        title=entry.get("title", "Untitled"),
                        url=url,
                        article_id=entry.get("guid", url),
                        published_at=published_at,
                        description=entry.get("summary", ""),
                        category=entry.get("category"),
                    )
                )
        return sorted(articles, key=lambda article: article.published_at, reverse=True)
