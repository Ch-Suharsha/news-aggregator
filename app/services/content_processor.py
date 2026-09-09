"""Stage 2 processing for collected articles and YouTube videos."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone

import httpx
from sqlalchemy.orm import Session

from app.db.models import Article, SourceType
from app.db.repository import NewsRepository
from app.db.session import SessionLocal
from app.scrapers.blog import extract_markdown
from app.scrapers.youtube import YouTubeScraper


@dataclass
class ContentProcessingResult:
    """Summary of one Stage 2 processing run."""

    requested: int = 0
    processed: int = 0
    failed: int = 0
    processed_titles: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)


class ContentProcessor:
    """Extract Markdown and transcripts for collected records."""

    def __init__(
        self,
        *,
        timeout: float = 30.0,
        youtube_scraper: YouTubeScraper | None = None,
    ) -> None:
        self.timeout = timeout
        self.youtube_scraper = youtube_scraper or YouTubeScraper(timeout=timeout)

    def _extract_blog_markdown(self, article: Article) -> str:
        response = httpx.get(
            article.url,
            headers={"User-Agent": "news-aggregator/0.1 (+local development)"},
            follow_redirects=True,
            timeout=self.timeout,
        )
        response.raise_for_status()
        return extract_markdown(response.text, url=article.url)

    def _extract_youtube_transcript(self, article: Article) -> str:
        transcript = self.youtube_scraper.get_transcript(article.external_id)
        if not transcript.text.strip():
            raise ValueError(f"Transcript is empty for YouTube video {article.external_id}")
        return transcript.text.strip()

    def _extract_content(self, article: Article) -> str:
        if article.source.source_type == SourceType.YOUTUBE:
            return self._extract_youtube_transcript(article)
        if article.source.source_type in {SourceType.BLOG, SourceType.NEWSLETTER}:
            return self._extract_blog_markdown(article)
        raise ValueError(f"Unsupported source type: {article.source.source_type}")

    def process_pending(
        self,
        *,
        batch_size: int = 50,
        retry_failed: bool = False,
        session: Session | None = None,
    ) -> ContentProcessingResult:
        """Process one batch of records missing ``content_text``."""
        if batch_size < 1:
            raise ValueError("batch_size must be at least 1")

        result = ContentProcessingResult()

        def process_with_session(active_session: Session) -> None:
            repository = NewsRepository(active_session)
            articles = repository.list_unprocessed_articles(
                limit=batch_size,
                retry_failed=retry_failed,
            )
            result.requested = len(articles)

            for article in articles:
                try:
                    content = self._extract_content(article)
                    repository.save_article_content(
                        article,
                        content_text=content,
                        content_hash=hashlib.sha256(content.encode("utf-8")).hexdigest(),
                        processed_at=datetime.now(timezone.utc),
                    )
                    active_session.commit()
                    result.processed += 1
                    result.processed_titles.append(article.title)
                except Exception as exc:  # one bad page should not stop the batch
                    active_session.rollback()
                    repository.save_article_processing_error(
                        article,
                        f"{type(exc).__name__}: {exc}",
                    )
                    active_session.commit()
                    result.failed += 1
                    result.failures.append(f"{article.title}: {type(exc).__name__}: {exc}")

        if session is not None:
            process_with_session(session)
        else:
            with SessionLocal() as owned_session:
                process_with_session(owned_session)
        return result
