from datetime import datetime, timezone

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.db.models import Article, Source, SourceType
from app.db.session import Base
from app.services.content_processor import ContentProcessor
from app.scrapers.youtube import Transcript


class FakeYouTubeScraper:
    def get_transcript(self, video_id):
        return Transcript(text=f"Transcript for {video_id}")


def test_content_processor_processes_blog_and_youtube_records(monkeypatch):
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    now = datetime(2026, 9, 8, tzinfo=timezone.utc)

    with Session(engine) as session:
        blog_source = Source(name="OpenAI", source_type=SourceType.BLOG, url="https://openai.com/rss")
        youtube_source = Source(name="YouTube", source_type=SourceType.YOUTUBE, url="https://youtube.com/channel/test", youtube_channel_id="test")
        session.add_all([blog_source, youtube_source])
        session.flush()
        session.add_all([
            Article(source_id=blog_source.id, external_id="blog-1", title="Blog", url="https://example.com/blog", published_at=now),
            Article(source_id=youtube_source.id, external_id="video-1", title="Video", url="https://youtube.com/watch?v=video-1", published_at=now),
        ])
        session.commit()

    class Response:
        text = "<html><body><h1>Blog</h1><p>Important context.</p></body></html>"

        def raise_for_status(self):
            pass

    monkeypatch.setattr("app.services.content_processor.httpx.get", lambda *args, **kwargs: Response())
    processor = ContentProcessor(youtube_scraper=FakeYouTubeScraper())

    with Session(engine) as session:
        result = processor.process_pending(session=session, batch_size=10)
        articles = session.scalars(select(Article).order_by(Article.id)).all()

    assert result.requested == 2
    assert result.processed == 2
    assert result.failed == 0
    assert articles[0].content_text
    assert "Important context" in articles[0].content_text
    assert articles[1].content_text == "Transcript for video-1"
    assert all(article.processed_at is not None for article in articles)
