"""Read-only Streamlit dashboard for the AI news aggregator."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import streamlit as st
from sqlalchemy import create_engine, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, joinedload, sessionmaker

from app.core.config import settings
from app.db.models import Article, Digest, DigestItem


def _database_url() -> str:
    """Read the database URL from Streamlit Secrets or local settings."""
    try:
        configured_url = st.secrets["DATABASE_URL"]
    except (FileNotFoundError, KeyError):
        configured_url = settings.database_url

    if configured_url.startswith("postgres://"):
        configured_url = "postgresql://" + configured_url.removeprefix("postgres://")
    if configured_url.startswith("postgresql://"):
        configured_url = "postgresql+psycopg://" + configured_url.removeprefix("postgresql://")
    return configured_url


@st.cache_resource
def _session_factory(database_url: str) -> sessionmaker[Session]:
    """Create one cached SQLAlchemy session factory for the dashboard."""
    engine = create_engine(database_url, pool_pre_ping=True)
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def _format_datetime(value: datetime | None) -> str:
    """Format timestamps consistently for recruiter-facing output."""
    if value is None:
        return "Publication date unavailable"
    return value.astimezone(UTC).strftime("%B %-d, %Y at %-I:%M %p UTC")


def article_to_row(article: Article) -> dict[str, Any]:
    """Convert an Article ORM object into a safe table row."""
    source = article.source
    return {
        "source": source.name if source else "Unknown source",
        "type": str(source.source_type) if source else "unknown",
        "title": article.title,
        "published": _format_datetime(article.published_at),
        "content_status": "Extracted" if article.content_text else "Metadata only",
        "url": article.url,
    }


def digest_to_row(item: DigestItem) -> dict[str, Any]:
    """Convert a ranked DigestItem ORM object into a display row."""
    article = item.article
    source = article.source if article else None
    return {
        "rank": item.rank,
        "relevance_score": item.relevance_score,
        "source": source.name if source else "Unknown source",
        "title": item.title,
        "summary": item.summary,
        "url": item.url,
        "published_at": article.published_at if article else None,
    }


def _load_snapshot(hours: int) -> dict[str, Any]:
    """Load the dashboard's read-only snapshot from PostgreSQL."""
    now = datetime.now(UTC)
    since = now - timedelta(hours=hours)
    factory = _session_factory(_database_url())

    with factory() as session:
        total_articles = session.scalar(select(func.count()).select_from(Article)) or 0
        extracted_articles = (
            session.scalar(
                select(func.count()).select_from(Article).where(Article.content_text.is_not(None))
            )
            or 0
        )
        digest_runs = session.scalar(select(func.count()).select_from(Digest)) or 0

        recent_articles = session.scalars(
            select(Article)
            .options(joinedload(Article.source))
            .where(Article.published_at >= since, Article.published_at <= now)
            .order_by(Article.published_at.desc())
            .limit(100)
        ).all()

        recent_digest_items = session.scalars(
            select(DigestItem)
            .join(DigestItem.article)
            .join(DigestItem.digest)
            .options(
                joinedload(DigestItem.article).joinedload(Article.source),
                joinedload(DigestItem.digest),
            )
            .where(
                DigestItem.rank.is_not(None),
                Article.published_at >= since,
                Article.published_at <= now,
                Digest.sent_at.is_not(None),
            )
            .order_by(DigestItem.rank.asc(), DigestItem.id.asc())
            .limit(10)
        ).all()

        latest_digest = session.scalar(select(Digest).order_by(Digest.created_at.desc()).limit(1))

        return {
            "metrics": {
                "total_articles": total_articles,
                "extracted_articles": extracted_articles,
                "digest_runs": digest_runs,
                "ranked_articles": len(recent_digest_items),
            },
            "recent_articles": [article_to_row(article) for article in recent_articles],
            "ranked_items": [digest_to_row(item) for item in recent_digest_items],
            "latest_digest": {
                "created_at": latest_digest.created_at if latest_digest else None,
                "sent_at": latest_digest.sent_at if latest_digest else None,
                "period_start": latest_digest.period_start if latest_digest else None,
                "period_end": latest_digest.period_end if latest_digest else None,
            }
            if latest_digest
            else None,
        }


@st.cache_data(ttl=60)
def load_snapshot(hours: int) -> dict[str, Any]:
    """Cache dashboard data briefly while allowing manual refresh."""
    return _load_snapshot(hours)


def render_dashboard() -> None:
    """Render the recruiter-facing dashboard."""
    st.set_page_config(
        page_title="AI News Aggregator",
        page_icon="🗞️",
        layout="wide",
    )

    st.title("AI News Aggregator")
    st.caption("A read-only view of the collection, enrichment, summarization, ranking, and delivery pipeline.")

    with st.sidebar:
        st.header("Dashboard settings")
        hours = st.selectbox(
            "Look-back window",
            options=(24, 48, 168, 336),
            format_func=lambda value: f"Last {value} hours",
            index=2,
        )
        if st.button("Refresh data", use_container_width=True):
            load_snapshot.clear()
            st.rerun()

    try:
        snapshot = load_snapshot(hours)
    except (SQLAlchemyError, ValueError):
        st.error("The dashboard could not connect to the database.")
        st.info("Configure DATABASE_URL in Streamlit Secrets and try again.")
        return

    metrics = snapshot["metrics"]
    metric_columns = st.columns(4)
    metric_columns[0].metric("Articles stored", metrics["total_articles"])
    metric_columns[1].metric("Content extracted", metrics["extracted_articles"])
    metric_columns[2].metric("Digest runs", metrics["digest_runs"])
    metric_columns[3].metric("Ranked in window", metrics["ranked_articles"])

    st.divider()
    st.subheader("Top-ranked news")
    ranked_items = snapshot["ranked_items"]
    if not ranked_items:
        st.info("No sent, ranked digest items were found in this time window.")
    else:
        for item in ranked_items:
            with st.container(border=True):
                st.markdown(f"### {item['rank']}. {item['title']}")
                published = _format_datetime(item["published_at"])
                st.caption(
                    f"{item['source']} · Published {published} · "
                    f"Relevance score: {item['relevance_score']}/100"
                )
                st.write(item["summary"])
                st.markdown(f"[Read the original source]({item['url']})")

    st.divider()
    st.subheader("Recently collected items")
    recent_articles = snapshot["recent_articles"]
    if recent_articles:
        st.dataframe(
            recent_articles,
            use_container_width=True,
            hide_index=True,
            column_config={
                "url": st.column_config.LinkColumn("Original URL"),
            },
        )
    else:
        st.info("No collected items were found in this time window.")

    latest_digest = snapshot["latest_digest"]
    if latest_digest:
        with st.expander("Latest pipeline digest metadata"):
            st.write(f"Created: {_format_datetime(latest_digest['created_at'])}")
            st.write(f"Sent: {_format_datetime(latest_digest['sent_at'])}")
            st.write(f"Period start: {_format_datetime(latest_digest['period_start'])}")
            st.write(f"Period end: {_format_datetime(latest_digest['period_end'])}")


if __name__ == "__main__":
    render_dashboard()
