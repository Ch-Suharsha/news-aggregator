"""Stage 4 processing: rank recent digest items for the user."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from agent.news_curator_agent import NewsCurationOutput, NewsCuratorAgent
from app.db.repository import NewsRepository
from app.db.session import SessionLocal


@dataclass
class CurationProcessingResult:
    """Summary of one news-curation run."""

    requested: int = 0
    ranked: int = 0
    failed: int = 0
    ranked_items: list[dict[str, int | str]] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)


class CurationProcessor:
    """Rank recent digest items and persist their relevance metadata."""

    def __init__(self, *, agent: NewsCuratorAgent | None = None) -> None:
        self.agent = agent or NewsCuratorAgent()

    @staticmethod
    def _validate_output(output: NewsCurationOutput, expected_ids: set[int]) -> None:
        returned_ids = [ranking.digest_item_id for ranking in output.rankings]
        if len(returned_ids) != len(expected_ids) or set(returned_ids) != expected_ids:
            raise ValueError("Curator must return every candidate exactly once")

        expected_ranks = set(range(1, len(expected_ids) + 1))
        returned_ranks = [ranking.rank for ranking in output.rankings]
        if set(returned_ranks) != expected_ranks or len(returned_ranks) != len(expected_ranks):
            raise ValueError("Curator ranks must be unique and cover 1 through the candidate count")

    def process_pending(
        self,
        *,
        hours: int = 24,
        limit: int = 100,
        session: Session | None = None,
    ) -> CurationProcessingResult:
        """Rank unranked digest items published within the look-back window."""
        if hours < 1:
            raise ValueError("hours must be at least 1")
        if limit < 1:
            raise ValueError("limit must be at least 1")

        result = CurationProcessingResult()

        def process_with_session(active_session: Session) -> None:
            repository = NewsRepository(active_session)
            now = datetime.now(timezone.utc)
            items = repository.list_recent_digest_items_for_ranking(
                since=now - timedelta(hours=hours),
                until=now,
                limit=limit,
            )
            result.requested = len(items)
            if not items:
                return

            try:
                output = self.agent.rank(items)
                self._validate_output(output, {item.id for item in items})
                rankings_by_id = {ranking.digest_item_id: ranking for ranking in output.rankings}
                for item in items:
                    ranking = rankings_by_id[item.id]
                    repository.save_digest_item_ranking(
                        item,
                        rank=ranking.rank,
                        relevance_score=ranking.relevance_score,
                        ranking_reason=ranking.reasoning,
                        ranked_at=now,
                    )
                    result.ranked_items.append(
                        {
                            "digest_item_id": item.id,
                            "rank": ranking.rank,
                            "relevance_score": ranking.relevance_score,
                            "title": item.title,
                        }
                    )
                active_session.commit()
                result.ranked = len(items)
            except Exception as exc:  # keep the database unchanged on a failed batch
                active_session.rollback()
                result.ranked_items.clear()
                result.failed = 1
                result.failures.append(f"{type(exc).__name__}: {exc}")

        if session is not None:
            process_with_session(session)
        else:
            with SessionLocal() as owned_session:
                process_with_session(owned_session)
        return result
