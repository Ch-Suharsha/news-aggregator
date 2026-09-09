from datetime import datetime, timezone

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from agent.news_curator_agent import NewsCurationOutput, NewsCuratorAgent, RankedDigestItem
from app.db.models import Article, Digest, DigestItem, Source, SourceType
from app.db.session import Base
from app.services.curation_processor import CurationProcessor


class FakeCurator:
    def rank(self, items):
        return NewsCurationOutput(
            rankings=[
                RankedDigestItem(
                    digest_item_id=item.id,
                    rank=index,
                    relevance_score=100 - index,
                    reasoning=f"Reason for {item.title}",
                )
                for index, item in enumerate(items, start=1)
            ]
        )


class FakeResponses:
    def __init__(self):
        self.calls = []

    def parse(self, **kwargs):
        self.calls.append(kwargs)

        class Response:
            output_parsed = NewsCurationOutput(
                rankings=[
                    RankedDigestItem(
                        digest_item_id=1,
                        rank=1,
                        relevance_score=95,
                        reasoning="Strong match.",
                    )
                ]
            )

        return Response()


class FakeClient:
    def __init__(self):
        self.responses = FakeResponses()


def test_curator_uses_responses_structured_output():
    client = FakeClient()
    agent = NewsCuratorAgent(client=client, model="deepseek-v4-flash", system_prompt="Test")

    source = Source(name="OpenAI", source_type=SourceType.BLOG, url="https://openai.com/rss")
    article = Article(source=source, title="Article", url="https://example.com", external_id="a")
    item = DigestItem(article=article, title="Digest item", url=article.url, summary="Useful summary.")
    result = agent.rank([item])

    assert result.rankings[0].relevance_score == 95
    call = client.responses.calls[0]
    assert call["model"] == "deepseek-v4-flash"
    assert call["text_format"] is NewsCurationOutput
    assert call["store"] is False


def test_curation_processor_persists_rankings():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    now = datetime.now(timezone.utc)

    with Session(engine) as session:
        source = Source(name="OpenAI", source_type=SourceType.BLOG, url="https://openai.com/rss")
        session.add(source)
        session.flush()
        article = Article(
            source_id=source.id,
            external_id="article-1",
            title="Original article",
            url="https://example.com/article-1",
            published_at=now,
        )
        session.add(article)
        session.flush()
        digest = Digest(period_start=now, period_end=now, prompt_version="test", content="")
        session.add(digest)
        session.flush()
        session.add(DigestItem(
            digest_id=digest.id,
            article_id=article.id,
            title="Digest item",
            url=article.url,
            summary="Useful summary.",
        ))
        session.commit()

    with Session(engine) as session:
        result = CurationProcessor(agent=FakeCurator()).process_pending(
            hours=24,
            session=session,
        )
        item = session.scalar(select(DigestItem))

    assert result.requested == 1
    assert result.ranked == 1
    assert result.failed == 0
    assert item.rank == 1
    assert item.relevance_score == 99
    assert item.ranking_reason == "Reason for Digest item"
    assert item.ranked_at is not None


def test_curation_processor_reranks_the_complete_window():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    now = datetime.now(timezone.utc)

    with Session(engine) as session:
        source = Source(name="OpenAI", source_type=SourceType.BLOG, url="https://openai.com/rss")
        session.add(source)
        session.flush()
        article = Article(
            source_id=source.id,
            external_id="article-1",
            title="Original article",
            url="https://example.com/article-1",
            published_at=now,
        )
        session.add(article)
        session.flush()
        digest = Digest(period_start=now, period_end=now, prompt_version="test", content="")
        session.add(digest)
        session.flush()
        session.add(DigestItem(
            digest_id=digest.id,
            article_id=article.id,
            title="Digest item",
            url=article.url,
            summary="Useful summary.",
            rank=4,
            relevance_score=40,
            ranking_reason="Old ranking.",
            ranked_at=now,
        ))
        session.commit()

    with Session(engine) as session:
        result = CurationProcessor(agent=FakeCurator()).process_pending(
            hours=24,
            session=session,
        )

    assert result.requested == 1
    assert result.ranked == 1
    assert result.failed == 0
