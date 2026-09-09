from datetime import UTC, datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from agent.email_agent import DailyDigestEmail, EmailAgent, EmailIntroOutput
from app.db.models import Article, Digest, DigestItem, Source, SourceType
from app.db.session import Base
from app.services.email_processor import EmailProcessor


class FakeResponses:
    def __init__(self):
        self.calls = []

    def parse(self, **kwargs):
        self.calls.append(kwargs)

        class Response:
            output_parsed = EmailIntroOutput(
                subject="Practical AI news for builders",
                intro="Today's digest focuses on practical AI product and engineering changes."
            )

        return Response()


class FakeClient:
    def __init__(self):
        self.responses = FakeResponses()


class FakeEmailAgent:
    def build_email(self, items, *, digest_date=None):
        return DailyDigestEmail(
            subject="Test digest",
            greeting="Hey Harsha, here is today's AI news digest.",
            intro="A useful selection of AI news.",
            articles=[
                {
                    "rank": item.rank,
                    "relevance_score": item.relevance_score,
                    "source": item.article.source.name,
                    "title": item.title,
                    "url": item.url,
                    "summary": item.summary,
                }
                for item in items
            ],
        )


def _seed_ranked_items(session: Session, count: int = 3) -> None:
    source = Source(name="OpenAI", source_type=SourceType.BLOG, url="https://openai.com/rss")
    session.add(source)
    session.flush()
    now = datetime.now(UTC)
    digest = Digest(period_start=now, period_end=now, prompt_version="test", content="")
    session.add(digest)
    session.flush()
    for index in range(1, count + 1):
        article = Article(
            source_id=source.id,
            external_id=f"article-{index}",
            title=f"Original {index}",
            url=f"https://example.com/{index}",
            published_at=now,
        )
        session.add(article)
        session.flush()
        session.add(
            DigestItem(
                digest_id=digest.id,
                article_id=article.id,
                title=f"Digest {index}",
                url=article.url,
                summary=f"Summary {index}",
                rank=index,
                relevance_score=100 - index,
                ranking_reason="Useful",
                ranked_at=now,
            )
        )
    session.commit()


def test_email_agent_uses_structured_responses_output():
    client = FakeClient()
    agent = EmailAgent(client=client, model="deepseek-v4-flash", system_prompt="Test")

    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        _seed_ranked_items(session, count=1)
        item = session.query(DigestItem).one()
        email = agent.build_email([item], digest_date=datetime(2026, 9, 9, tzinfo=UTC).date())

    assert email.articles[0].rank == 1
    assert email.greeting.startswith("Hey Harsha")
    call = client.responses.calls[0]
    assert call["model"] == "deepseek-v4-flash"
    assert call["text_format"] is EmailIntroOutput
    assert call["store"] is False


def test_email_processor_selects_ranked_items_in_order():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        _seed_ranked_items(session, count=3)
        result = EmailProcessor(agent=FakeEmailAgent()).process_pending(hours=24, limit=2, session=session)

    assert result.requested == 2
    assert result.generated is True
    assert result.failed == 0
    assert [item.rank for item in result.email.articles] == [1, 2]
    assert result.email.articles[0].title == "Digest 1"
    assert "## 1. Digest 1" in result.email.markdown
    assert "[Read the original source]" in result.email.markdown
    assert "<article style=" in result.email.html_body
    assert "<strong>#1</strong>" in result.email.html_body
    assert "Today's overview" in result.email.html_body
