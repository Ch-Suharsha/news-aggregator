from datetime import datetime, timezone

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.db.models import Article, Digest, DigestItem, Source, SourceType
from app.db.session import Base
from app.services.digest_processor import DigestProcessor
from agent.digest_agent import DigestAgent, DigestItemOutput


class FakeDigestAgent:
    def summarize(self, article):
        return DigestItemOutput(
            title=f"Digest: {article.title}",
            summary="First sentence. Second sentence.",
        )


class FakeResponses:
    def __init__(self):
        self.calls = []

    def parse(self, **kwargs):
        self.calls.append(kwargs)

        class Response:
            output_parsed = DigestItemOutput(
                title="Structured title",
                summary="First sentence. Second sentence.",
            )

        return Response()


class FakeClient:
    def __init__(self):
        self.responses = FakeResponses()


def test_digest_agent_uses_responses_structured_output():
    source = Source(name="OpenAI", source_type=SourceType.BLOG, url="https://openai.com/rss")
    article = Article(
        source=source,
        external_id="article-1",
        title="Original article",
        url="https://example.com/article-1",
        content_text="Article context.",
    )
    client = FakeClient()
    agent = DigestAgent(
        client=client,
        model="deepseek-v4-flash",
        system_prompt="Test instructions",
    )

    result = agent.summarize(article)

    assert result.title == "Structured title"
    call = client.responses.calls[0]
    assert call["model"] == "deepseek-v4-flash"
    assert call["instructions"] == "Test instructions"
    assert call["text_format"] is DigestItemOutput
    assert call["store"] is False


def test_digest_processor_links_structured_items_to_articles():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    now = datetime(2026, 9, 8, tzinfo=timezone.utc)

    with Session(engine) as session:
        source = Source(name="OpenAI", source_type=SourceType.BLOG, url="https://openai.com/rss")
        session.add(source)
        session.flush()
        session.add(Article(
            source_id=source.id,
            external_id="article-1",
            title="Original article",
            url="https://example.com/article-1",
            published_at=now,
            content_text="Article context.",
        ))
        session.commit()

    with Session(engine) as session:
        result = DigestProcessor(agent=FakeDigestAgent()).process_pending(session=session)
        digest = session.scalar(select(Digest))
        item = session.scalar(select(DigestItem))

    assert result.requested == 1
    assert result.summarized == 1
    assert result.failed == 0
    assert digest is not None
    assert item is not None
    assert item.digest_id == digest.id
    assert item.article_id == 1
    assert item.title == "Digest: Original article"
    assert item.url == "https://example.com/article-1"
