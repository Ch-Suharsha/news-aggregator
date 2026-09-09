"""Stage 5 processing: build a daily email from curator-ranked articles."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from agent.email_agent import DailyDigestEmail, EmailAgent
from app.db.repository import NewsRepository
from app.db.session import SessionLocal


@dataclass
class EmailProcessingResult:
    """Summary and output of one email-generation run."""

    requested: int = 0
    generated: bool = False
    email: dict | None = None
    failed: int = 0
    failures: list[str] = field(default_factory=list)


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

            try:
                email: DailyDigestEmail = self.agent.build_email(items, digest_date=now.date())
                result.email = email.model_dump(mode="json")
                result.email["text_body"] = email.to_plain_text()
                result.email["html_body"] = email.to_html()
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
