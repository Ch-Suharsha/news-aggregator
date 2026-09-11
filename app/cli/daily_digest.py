"""Run the complete daily news pipeline from collection through email delivery."""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict, is_dataclass
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from app.db.session import create_tables
from app.services.content_processor import ContentProcessingResult, ContentProcessor
from app.services.curation_processor import CurationProcessingResult, CurationProcessor
from app.services.digest_processor import DigestProcessingResult, DigestProcessor
from app.services.email_processor import EmailProcessingResult, EmailProcessor
from app.services.email_sender import EmailSender, EmailSendResult
from app.services.runner import NewsRunner, NewsRunResult


class DailyDigestPipelineResult(BaseModel):
    """Serializable summary of one complete daily pipeline run."""

    status: str = "started"
    hours: int = Field(ge=1)
    collection: dict[str, int] | None = None
    content: dict[str, Any] | None = None
    digest: dict[str, Any] | None = None
    curation: dict[str, Any] | None = None
    email: EmailProcessingResult | None = None
    delivery: EmailSendResult | None = None
    failures: list[str] = Field(default_factory=list)


def _stage_dump(value: Any) -> dict[str, Any]:
    """Convert the existing dataclass stage results into JSON-safe dictionaries."""
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if is_dataclass(value):
        return asdict(value)
    raise TypeError(f"Unsupported pipeline result: {type(value).__name__}")


class DailyDigestPipeline:
    """Coordinate the existing stages without moving their responsibilities."""

    def __init__(
        self,
        *,
        news_runner: NewsRunner | None = None,
        content_processor: ContentProcessor | None = None,
        digest_processor: DigestProcessor | None = None,
        curation_processor: CurationProcessor | None = None,
        email_processor: EmailProcessor | None = None,
        email_sender: EmailSender | None = None,
    ) -> None:
        self.news_runner = news_runner or NewsRunner()
        self.content_processor = content_processor or ContentProcessor()
        self.digest_processor = digest_processor or DigestProcessor()
        self.curation_processor = curation_processor or CurationProcessor()
        self.email_processor = email_processor or EmailProcessor()
        self.email_sender = email_sender or EmailSender()

    def run(
        self,
        *,
        hours: int = 24,
        content_batch_size: int = 100,
        digest_limit: int = 100,
        curation_limit: int = 100,
        email_limit: int = 10,
    ) -> DailyDigestPipelineResult:
        """Run collection, enrichment, summarization, ranking, and delivery."""
        if hours < 1:
            raise ValueError("hours must be at least 1")

        result = DailyDigestPipelineResult(hours=hours)

        collected: NewsRunResult = self.news_runner.run(hours=hours)
        result.collection = {
            "youtube_videos": len(collected.youtube_videos),
            "anthropic_articles": len(collected.anthropic_articles),
            "openai_articles": len(collected.openai_articles),
        }

        content: ContentProcessingResult = self.content_processor.process_pending(
            batch_size=content_batch_size,
        )
        result.content = _stage_dump(content)
        result.failures.extend(content.failures)

        digest: DigestProcessingResult = self.digest_processor.process_pending(limit=digest_limit)
        result.digest = _stage_dump(digest)
        result.failures.extend(digest.failures)

        curation: CurationProcessingResult = self.curation_processor.process_pending(
            hours=hours,
            limit=curation_limit,
        )
        result.curation = _stage_dump(curation)
        result.failures.extend(curation.failures)
        if curation.failed:
            result.status = "curation_failed"
            return result

        email: EmailProcessingResult = self.email_processor.process_pending(
            hours=hours,
            limit=email_limit,
        )
        result.email = email
        result.failures.extend(email.failures)
        if email.failed or not email.generated or email.email is None:
            result.status = "no_email" if not email.generated else "email_generation_failed"
            return result

        delivery = self.email_sender.send(email.email)
        result.delivery = delivery
        if delivery.sent and email.digest_ids:
            try:
                self.email_processor.mark_digests_sent(
                    email.digest_ids,
                    sent_at=datetime.now(UTC),
                )
            except Exception as exc:  # noqa: BLE001 - delivery happened; surface tracking failure
                result.failures.append(f"{type(exc).__name__}: {exc}")
                result.status = "delivery_tracking_failed"
                return result
        result.status = "sent" if delivery.sent else "delivery_failed"
        return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the complete daily AI news pipeline.")
    parser.add_argument(
        "--hours",
        type=int,
        default=int(os.getenv("DIGEST_HOURS", "24")),
        help="Look-back window (default: DIGEST_HOURS or 24).",
    )
    parser.add_argument("--content-batch-size", type=int, default=100)
    parser.add_argument("--digest-limit", type=int, default=100)
    parser.add_argument("--curation-limit", type=int, default=100)
    parser.add_argument("--email-limit", type=int, default=10)
    args = parser.parse_args()

    create_tables()
    result = DailyDigestPipeline().run(
        hours=args.hours,
        content_batch_size=args.content_batch_size,
        digest_limit=args.digest_limit,
        curation_limit=args.curation_limit,
        email_limit=args.email_limit,
    )
    print(json.dumps(result.model_dump(mode="json"), indent=2, ensure_ascii=False))
    if result.status in {
        "curation_failed",
        "email_generation_failed",
        "delivery_failed",
        "delivery_tracking_failed",
    }:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
