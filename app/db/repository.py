"""Small CRUD repository for sources and collected articles."""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Article, Source, SourceType


class NewsRepository:
    """Database operations used by the collection runner."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def get_or_create_source(
        self,
        *,
        name: str,
        source_type: SourceType,
        url: str,
        youtube_channel_id: str | None = None,
    ) -> Source:
        source = self.session.scalar(
            select(Source).where(
                Source.source_type == source_type,
                Source.url == url,
            )
        )
        if source is None:
            source = Source(
                name=name,
                source_type=source_type,
                url=url,
                youtube_channel_id=youtube_channel_id,
            )
            self.session.add(source)
            self.session.flush()
        return source

    def get_article(self, *, source_id: int, external_id: str) -> Article | None:
        return self.session.scalar(
            select(Article).where(
                Article.source_id == source_id,
                Article.external_id == external_id,
            )
        )

    def create_article_if_new(
        self,
        *,
        source_id: int,
        external_id: str,
        title: str,
        url: str,
        published_at: datetime | None,
        summary: str | None,
    ) -> Article:
        existing = self.get_article(source_id=source_id, external_id=external_id)
        if existing is not None:
            return existing

        article = Article(
            source_id=source_id,
            external_id=external_id,
            title=title,
            url=url,
            published_at=published_at,
            summary=summary or None,
            content_text=None,
        )
        self.session.add(article)
        return article

    def list_recent_articles(self, *, limit: int = 100) -> list[Article]:
        statement = (
            select(Article)
            .order_by(Article.published_at.desc())
            .limit(limit)
        )
        return list(self.session.scalars(statement))
