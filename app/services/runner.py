"""Collection runner for all configured news sources."""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.sources import YOUTUBE_CHANNELS
from app.db.models import SourceType
from app.db.repository import NewsRepository
from app.db.session import SessionLocal
from app.scrapers.anthropic import ANTHROPIC_FEEDS, AnthropicArticle, AnthropicScraper
from app.scrapers.openai import OPENAI_NEWS_RSS_URL, OpenAIArticle, OpenAIScraper
from app.scrapers.youtube import ChannelVideo, YouTubeScraper


class NewsRunResult(BaseModel):
    """All source metadata collected during one runner execution."""

    lookback_hours: int
    collected_at: datetime
    youtube_videos: list[ChannelVideo]
    anthropic_articles: list[AnthropicArticle]
    openai_articles: list[OpenAIArticle]


class NewsRunner:
    """Collect source metadata, then optionally persist it to PostgreSQL."""

    def __init__(
        self,
        *,
        youtube_channels: list[str] | None = None,
        youtube_scraper: YouTubeScraper | None = None,
        anthropic_scraper: AnthropicScraper | None = None,
        openai_scraper: OpenAIScraper | None = None,
    ) -> None:
        self.youtube_channels = youtube_channels if youtube_channels is not None else YOUTUBE_CHANNELS
        self.youtube_scraper = youtube_scraper or YouTubeScraper()
        self.anthropic_scraper = anthropic_scraper or AnthropicScraper()
        self.openai_scraper = openai_scraper or OpenAIScraper()
        self._video_sources: dict[str, str] = {}

    def collect(self, *, hours: int = 24, now: datetime | None = None) -> NewsRunResult:
        """Fetch source metadata without transcripts, LLM calls, or database writes."""
        collected_at = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        youtube_videos: list[ChannelVideo] = []
        self._video_sources = {}
        for channel in self.youtube_channels:
            channel_id = self.youtube_scraper.resolve_channel_id(channel)
            videos = self.youtube_scraper.fetch_recent_videos(channel_id, hours=hours, now=now)
            youtube_videos.extend(videos)
            self._video_sources.update({video.video_id: channel_id for video in videos})

        return NewsRunResult(
            lookback_hours=hours,
            collected_at=collected_at,
            youtube_videos=youtube_videos,
            anthropic_articles=self.anthropic_scraper.fetch_recent_articles(hours=hours, now=now),
            openai_articles=self.openai_scraper.fetch_recent_articles(hours=hours, now=now),
        )

    def run(
        self,
        *,
        hours: int = 24,
        now: datetime | None = None,
        persist: bool = True,
        session: Session | None = None,
    ) -> NewsRunResult:
        """Collect metadata and persist it unless ``persist`` is disabled."""
        result = self.collect(hours=hours, now=now)
        if persist:
            if session is not None:
                self.persist(result, session)
            else:
                with SessionLocal() as owned_session:
                    self.persist(result, owned_session)
        return result

    def persist(self, result: NewsRunResult, session: Session) -> None:
        """Upsert collected metadata while leaving content for later processing."""
        repository = NewsRepository(session)
        source_ids: dict[tuple[SourceType, str], int] = {}

        def source_id(*, name: str, source_type: SourceType, url: str, youtube_channel_id: str | None = None) -> int:
            key = (source_type, url)
            if key not in source_ids:
                source = repository.get_or_create_source(
                    name=name,
                    source_type=source_type,
                    url=url,
                    youtube_channel_id=youtube_channel_id,
                )
                source_ids[key] = source.id
            return source_ids[key]

        for video in result.youtube_videos:
            channel_id = self._video_sources.get(video.video_id)
            if channel_id is None:
                raise ValueError(f"No source channel recorded for video {video.video_id}")
            sid = source_id(
                name=f"YouTube channel {channel_id}",
                source_type=SourceType.YOUTUBE,
                url=f"https://www.youtube.com/channel/{channel_id}",
                youtube_channel_id=channel_id,
            )
            repository.create_article_if_new(
                source_id=sid,
                external_id=video.video_id,
                title=video.title,
                url=video.url,
                published_at=video.published_at,
                summary=video.description,
            )

        for article in [*result.anthropic_articles, *result.openai_articles]:
            is_anthropic = isinstance(article, AnthropicArticle)
            source_name = "Anthropic" if is_anthropic else "OpenAI"
            feed_url = ANTHROPIC_FEEDS[article.topic] if is_anthropic else OPENAI_NEWS_RSS_URL
            sid = source_id(
                name=f"{source_name} News RSS",
                source_type=SourceType.BLOG,
                url=feed_url,
            )
            repository.create_article_if_new(
                source_id=sid,
                external_id=article.article_id,
                title=article.title,
                url=article.url,
                published_at=article.published_at,
                summary=article.description,
            )
        session.commit()
