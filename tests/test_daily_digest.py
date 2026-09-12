from datetime import UTC, datetime

from agent.email_agent import DailyDigestEmail, EmailArticle
from app.cli.daily_digest import DailyDigestPipeline
from app.services.content_processor import ContentProcessingResult
from app.services.curation_processor import CurationProcessingResult
from app.services.digest_processor import DigestProcessingResult
from app.services.email_processor import EmailProcessingResult
from app.services.email_sender import EmailSendResult
from app.services.runner import NewsRunResult


class FakeNewsRunner:
    def __init__(self, calls):
        self.calls = calls

    def run(self, *, hours):
        self.calls.append("collect")
        return NewsRunResult(
            lookback_hours=hours,
            collected_at=datetime.now(UTC),
            youtube_videos=[],
            anthropic_articles=[],
            openai_articles=[],
        )


class FakeContentProcessor:
    def __init__(self, calls):
        self.calls = calls

    def process_pending(self, *, batch_size):
        self.calls.append("content")
        return ContentProcessingResult(requested=1, processed=1)


class FakeDigestProcessor:
    def __init__(self, calls):
        self.calls = calls

    def process_pending(self, *, limit):
        self.calls.append("digest")
        return DigestProcessingResult(requested=1, summarized=1, digest_id=1)


class FakeCurationProcessor:
    def __init__(self, calls, failed=False):
        self.calls = calls
        self.failed = failed

    def process_pending(self, *, hours, limit):
        self.calls.append("curation")
        return CurationProcessingResult(
            requested=1,
            ranked=0 if self.failed else 1,
            failed=1 if self.failed else 0,
        )


class FakeEmailProcessor:
    def __init__(self, calls):
        self.calls = calls

    def process_pending(self, *, hours, limit):
        self.calls.append("email")
        email = DailyDigestEmail(
            subject="AI Digest",
            greeting="Hey Harsha",
            intro="Overview",
            articles=[
                EmailArticle(
                    rank=1,
                    relevance_score=90,
                    source="OpenAI",
                    title="Article",
                    url="https://example.com/article",
                    summary="Summary",
                )
            ],
        )
        return EmailProcessingResult(requested=1, generated=True, email=email)


class FakeEmailSender:
    def __init__(self, calls):
        self.calls = calls

    def send(self, email):
        self.calls.append("send")
        return EmailSendResult(sent=True, recipient="me@example.com", subject=email.subject)


def test_daily_pipeline_runs_stages_in_order():
    calls = []
    result = DailyDigestPipeline(
        news_runner=FakeNewsRunner(calls),
        content_processor=FakeContentProcessor(calls),
        digest_processor=FakeDigestProcessor(calls),
        curation_processor=FakeCurationProcessor(calls),
        email_processor=FakeEmailProcessor(calls),
        email_sender=FakeEmailSender(calls),
    ).run()

    assert calls == ["collect", "content", "digest", "curation", "email", "send"]
    assert result.status == "sent"
    assert result.collection == {
        "youtube_videos": 0,
        "anthropic_articles": 0,
        "openai_articles": 0,
        "failures": [],
    }
    assert result.delivery.sent is True


def test_daily_pipeline_does_not_send_after_curation_failure():
    calls = []
    result = DailyDigestPipeline(
        news_runner=FakeNewsRunner(calls),
        content_processor=FakeContentProcessor(calls),
        digest_processor=FakeDigestProcessor(calls),
        curation_processor=FakeCurationProcessor(calls, failed=True),
        email_processor=FakeEmailProcessor(calls),
        email_sender=FakeEmailSender(calls),
    ).run()

    assert calls == ["collect", "content", "digest", "curation"]
    assert result.status == "curation_failed"
    assert result.delivery is None
