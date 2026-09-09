"""Stage 3 processing: generate one structured digest item per article."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from agent.digest_agent import DigestAgent, DigestItemOutput
from app.db.repository import NewsRepository
from app.db.session import SessionLocal

DIGEST_PROMPT_VERSION = "digest-item-v1"


@dataclass
class DigestProcessingResult:
    """Summary of one digest-item processing run."""

    requested: int = 0
    summarized: int = 0
    failed: int = 0
    digest_id: int | None = None
    summarized_titles: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)


class DigestProcessor:
    """Create structured summaries for articles not yet represented in a digest."""

    def __init__(self, *, agent: DigestAgent | None = None) -> None:
        self.agent = agent or DigestAgent()

    def process_pending(
        self,
        *,
        limit: int = 100,
        session: Session | None = None,
    ) -> DigestProcessingResult:
        """Summarize up to ``limit`` unsummarized articles."""
        if limit < 1:
            raise ValueError("limit must be at least 1")

        result = DigestProcessingResult()

        def process_with_session(active_session: Session) -> None:
            repository = NewsRepository(active_session)
            articles = repository.list_articles_without_digest_item(limit=limit)
            result.requested = len(articles)
            if not articles:
                return

            now = datetime.now(timezone.utc)
            published_dates = [article.published_at for article in articles if article.published_at]
            digest = repository.create_digest(
                period_start=min(published_dates, default=now),
                period_end=now,
                prompt_version=DIGEST_PROMPT_VERSION,
            )
            result.digest_id = digest.id
            active_session.commit()

            for article in articles:
                try:
                    output: DigestItemOutput = self.agent.summarize(article)
                    repository.create_digest_item_if_new(
                        digest_id=digest.id,
                        article_id=article.id,
                        title=output.title,
                        url=article.url,
                        summary=output.summary,
                    )
                    active_session.commit()
                    result.summarized += 1
                    result.summarized_titles.append(output.title)
                except Exception as exc:  # one failed article should not stop the batch
                    active_session.rollback()
                    result.failed += 1
                    result.failures.append(f"{article.title}: {type(exc).__name__}: {exc}")

        if session is not None:
            process_with_session(session)
        else:
            with SessionLocal() as owned_session:
                process_with_session(owned_session)
        return result
