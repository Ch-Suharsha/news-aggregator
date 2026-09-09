from datetime import datetime, timezone

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.db.models import Article
from app.db.session import Base
from app.scrapers.anthropic import AnthropicArticle, AnthropicTopic
from app.scrapers.openai import OpenAIArticle
from app.scrapers.youtube import ChannelVideo
from app.services.runner import NewsRunResult, NewsRunner


class FakeYouTubeScraper:
    def resolve_channel_id(self, channel):
        return channel

    def fetch_recent_videos(self, channel, *, hours, now):
        return []

class FakeAnthropicScraper:
    def fetch_recent_articles(self, *, hours, now):
        return []


class FakeOpenAIScraper:
    def fetch_recent_articles(self, *, hours, now):
        return []


def test_runner_collects_all_sources_with_one_lookback_window():
    result = NewsRunner(
        youtube_channels=["channel-id"],
        youtube_scraper=FakeYouTubeScraper(),
        anthropic_scraper=FakeAnthropicScraper(),
        openai_scraper=FakeOpenAIScraper(),
    ).run(hours=24, now=datetime(2026, 9, 8, tzinfo=timezone.utc), persist=False)

    assert result.lookback_hours == 24
    assert result.youtube_videos == []
    assert result.anthropic_articles == []
    assert result.openai_articles == []


def test_runner_persists_metadata_without_processed_content():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    now = datetime(2026, 9, 8, tzinfo=timezone.utc)
    runner = NewsRunner(youtube_channels=["channel-id"])
    runner._video_sources = {"video-id": "channel-id"}
    result = NewsRunResult(
        lookback_hours=24,
        collected_at=now,
        youtube_videos=[ChannelVideo(title="Video", url="https://youtu.be/video-id", video_id="video-id", published_at=now, description="Video summary")],
        anthropic_articles=[AnthropicArticle(title="Anthropic", url="https://anthropic.com/a", article_id="a", published_at=now, description="Anthropic summary", topic=AnthropicTopic.NEWS)],
        openai_articles=[OpenAIArticle(title="OpenAI", url="https://openai.com/a", article_id="a", published_at=now, description="OpenAI summary")],
    )

    with Session(engine) as session:
        runner.persist(result, session)
        articles = session.scalars(select(Article)).all()

    assert len(articles) == 3
    assert all(article.content_text is None for article in articles)
    assert {article.summary for article in articles} == {"Video summary", "Anthropic summary", "OpenAI summary"}
