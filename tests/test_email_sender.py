from typing import ClassVar

from agent.email_agent import DailyDigestEmail, EmailArticle
from app.services.email_sender import EmailSender


def _email() -> DailyDigestEmail:
    return DailyDigestEmail(
        subject="AI News Digest - 2026-09-09",
        greeting="Hey Harsha, here is today's AI news digest.",
        intro="A short overview of today's most relevant AI developments.",
        articles=[
            EmailArticle(
                rank=1,
                relevance_score=95,
                source="OpenAI News RSS",
                title="A useful AI update",
                url="https://example.com/article",
                summary="A short article summary.",
            )
        ],
    )


class FakeSMTP:
    messages: ClassVar[list] = []

    def __init__(self, host, port, timeout):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.started_tls = False
        self.logged_in_as = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def ehlo(self):
        pass

    def starttls(self, context):
        self.started_tls = True

    def login(self, username, password):
        self.logged_in_as = (username, password)

    def send_message(self, message):
        self.messages.append((self, message))


def test_sender_uses_gmail_smtp_and_markdown_body(monkeypatch):
    FakeSMTP.messages = []
    monkeypatch.setattr("app.services.email_sender.smtplib.SMTP", FakeSMTP)

    result = EmailSender(
        smtp_host="smtp.gmail.com",
        smtp_port=587,
        username="me@gmail.com",
        password="app-password",
        recipient="me@gmail.com",
        from_address="AI News Digest <me@gmail.com>",
    ).send(_email())

    assert result.sent is True
    smtp, message = FakeSMTP.messages[0]
    assert smtp.started_tls is True
    assert smtp.logged_in_as == ("me@gmail.com", "app-password")
    assert message["To"] == "me@gmail.com"
    assert "## 1. A useful AI update" in message.get_body(preferencelist=("plain",)).get_content()
    assert "<h1>" in message.get_body(preferencelist=("html",)).get_content()


def test_sender_rejects_missing_configuration():
    try:
        EmailSender(username="", password="", recipient="", from_address="").send(_email())
    except ValueError as exc:
        assert "SMTP_USERNAME" in str(exc)
    else:
        raise AssertionError("Expected missing SMTP configuration to fail")
