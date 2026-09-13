from datetime import UTC, datetime
from types import SimpleNamespace

from app.dashboard import article_to_row, digest_to_row


def test_article_to_row_reports_source_and_content_status():
    article = SimpleNamespace(
        title="A stored article",
        url="https://example.com/article",
        published_at=datetime(2026, 9, 12, 12, 0, tzinfo=UTC),
        content_text="Full context",
        source=SimpleNamespace(name="Example News", source_type="blog"),
    )

    assert article_to_row(article) == {
        "source": "Example News",
        "type": "blog",
        "title": "A stored article",
        "published": "September 12, 2026 at 12:00 PM UTC",
        "content_status": "Extracted",
        "url": "https://example.com/article",
    }


def test_digest_to_row_keeps_rank_summary_and_original_url():
    item = SimpleNamespace(
        rank=1,
        relevance_score=92,
        title="Ranked article",
        summary="A short summary.",
        url="https://example.com/article",
        article=SimpleNamespace(
            published_at=datetime(2026, 9, 12, 12, 0, tzinfo=UTC),
            source=SimpleNamespace(name="Example News"),
        ),
    )

    assert digest_to_row(item) == {
        "rank": 1,
        "relevance_score": 92,
        "source": "Example News",
        "title": "Ranked article",
        "summary": "A short summary.",
        "url": "https://example.com/article",
        "published_at": datetime(2026, 9, 12, 12, 0, tzinfo=UTC),
    }
