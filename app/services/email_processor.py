"""Stage 5 processing: build a daily email from curator-ranked articles."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from agent.email_agent import DailyDigestEmail, EmailAgent
from app.db.repository import NewsRepository
from app.db.session import SessionLocal


class EmailProcessingResult(BaseModel):
    """Summary and output of one email-generation run."""

    requested: int = Field(default=0, ge=0)
    generated: bool = False
    email: DailyDigestEmail | None = None
    digest_ids: list[int] = Field(default_factory=list)
    failed: int = Field(default=0, ge=0)
    failures: list[str] = Field(default_factory=list)


class EmailProcessor:
    """Select the curator's top items and build a delivery-ready email."""

    def __init__(self, *, agent: EmailAgent | None = None) -> None:
        self.agent = agent or EmailAgent()

    def process_pending(
        self,
        *,
        hours: int = 24,
        limit: int = 10,
        session: Session | None = None,
    ) -> EmailProcessingResult:
        """Build an email from ranked digest items in the requested time window."""
        if hours < 1:
            raise ValueError("hours must be at least 1")
        if limit < 1:
            raise ValueError("limit must be at least 1")
        if limit > 10:
            raise ValueError("limit cannot be greater than 10")

        result = EmailProcessingResult()

        def process_with_session(active_session: Session) -> None:
            repository = NewsRepository(active_session)
            now = datetime.now(UTC)
            items = repository.list_ranked_digest_items_for_email(
                since=now - timedelta(hours=hours),
                until=now,
                limit=limit,
            )
            result.requested = len(items)
            if not items:
                return

            result.digest_ids = sorted({item.digest_id for item in items})

            try:
                email: DailyDigestEmail = self.agent.build_email(items, digest_date=now.date())
                result.email = email
                result.generated = True
            except Exception as exc:  # noqa: BLE001 - one failed preview should be reported, not raised
                result.failed = 1
                result.failures.append(f"{type(exc).__name__}: {exc}")

        if session is not None:
            process_with_session(session)
        else:
            with SessionLocal() as owned_session:
                process_with_session(owned_session)
        return result

    @staticmethod
    def mark_digests_sent(digest_ids: list[int], *, sent_at: datetime | None = None) -> None:
        """Persist successful delivery markers for a later idempotent run."""
        if not digest_ids:
            return

        with SessionLocal() as session:
            repository = NewsRepository(session)
            repository.mark_digests_sent(
                digest_ids,
                sent_at=sent_at or datetime.now(UTC),
            )
            session.commit()
