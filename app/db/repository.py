"""Small CRUD repository for sources and collected articles."""

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from .models import Article, Digest, DigestItem, Source, SourceType


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

    def list_unprocessed_articles(
        self,
        *,
        limit: int = 50,
        retry_failed: bool = False,
    ) -> list[Article]:
        """Return collected articles that do not yet have extracted content."""
        statement = (
            select(Article)
            .join(Article.source)
            .where(Article.content_text.is_(None))
            .order_by(Article.created_at.asc())
            .limit(limit)
        )
        if not retry_failed:
            statement = statement.where(Article.processing_error.is_(None))
        return list(self.session.scalars(statement))

    def save_article_content(
        self,
        article: Article,
        *,
        content_text: str,
        content_hash: str,
        processed_at: datetime,
    ) -> Article:
        """Save extracted content and mark an article as successfully processed."""
        article.content_text = content_text
        article.content_hash = content_hash
        article.processed_at = processed_at
        article.processing_error = None
        return article

    def save_article_processing_error(self, article: Article, error: str) -> Article:
        """Record a processing failure without removing the collected metadata."""
        article.processing_error = error
        return article

    def list_articles_without_digest_item(self, *, limit: int = 100) -> list[Article]:
        """Return articles that do not yet have an LLM-generated digest item."""
        statement = (
            select(Article)
            .outerjoin(DigestItem, DigestItem.article_id == Article.id)
            .where(DigestItem.id.is_(None))
            .order_by(Article.published_at.asc(), Article.id.asc())
            .limit(limit)
        )
        return list(self.session.scalars(statement))

    def create_digest(
        self,
        *,
        period_start: datetime,
        period_end: datetime,
        prompt_version: str,
    ) -> Digest:
        """Create a digest run that will own generated digest items."""
        digest = Digest(
            period_start=period_start,
            period_end=period_end,
            prompt_version=prompt_version,
            content="",
        )
        self.session.add(digest)
        self.session.flush()
        return digest

    def create_digest_item_if_new(
        self,
        *,
        digest_id: int,
        article_id: int,
        title: str,
        url: str,
        summary: str,
    ) -> DigestItem:
        """Create one digest item unless the article was already summarized."""
        existing = self.session.scalar(
            select(DigestItem).where(DigestItem.article_id == article_id)
        )
        if existing is not None:
            return existing

        item = DigestItem(
            digest_id=digest_id,
            article_id=article_id,
            title=title,
            url=url,
            summary=summary,
        )
        self.session.add(item)
        return item

    def list_recent_digest_items_for_ranking(
        self,
        *,
        since: datetime,
        until: datetime,
        limit: int = 100,
        only_unranked: bool = False,
    ) -> list[DigestItem]:
        """Return digest items for a ranking window."""
        publication_time = func.coalesce(Article.published_at, DigestItem.created_at)
        statement = (
            select(DigestItem)
            .join(DigestItem.article)
            .options(joinedload(DigestItem.article).joinedload(Article.source))
            .where(publication_time >= since, publication_time <= until)
            .order_by(publication_time.desc(), DigestItem.id.desc())
            .limit(limit)
        )
        if only_unranked:
            statement = statement.where(DigestItem.ranked_at.is_(None))
        return list(self.session.scalars(statement))

    def list_ranked_digest_items_for_email(
        self,
        *,
        since: datetime,
        until: datetime,
        limit: int = 10,
    ) -> list[DigestItem]:
        """Return the highest-ranked digest items in an email time window."""
        if limit < 1:
            raise ValueError("limit must be at least 1")

        publication_time = func.coalesce(Article.published_at, DigestItem.created_at)
        statement = (
            select(DigestItem)
            .join(DigestItem.article)
            .options(joinedload(DigestItem.article).joinedload(Article.source))
            .where(
                DigestItem.rank.is_not(None),
                publication_time >= since,
                publication_time <= until,
            )
            .order_by(DigestItem.rank.asc(), DigestItem.id.asc())
            .limit(limit)
        )
        return list(self.session.scalars(statement))

    def save_digest_item_ranking(
        self,
        item: DigestItem,
        *,
        rank: int,
        relevance_score: int,
        ranking_reason: str,
        ranked_at: datetime,
    ) -> DigestItem:
        """Save one curator ranking on a digest item."""
        item.rank = rank
        item.relevance_score = relevance_score
        item.ranking_reason = ranking_reason
        item.ranked_at = ranked_at
        return item
