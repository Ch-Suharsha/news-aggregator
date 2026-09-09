"""SMTP delivery for the generated daily digest email."""

from __future__ import annotations

import smtplib
import ssl
from email.message import EmailMessage

from pydantic import BaseModel, ConfigDict, Field

from agent.email_agent import DailyDigestEmail
from app.core.config import settings


class EmailSendResult(BaseModel):
    """Structured result of one SMTP delivery attempt."""

    model_config = ConfigDict(extra="forbid")

    sent: bool
    recipient: str = Field(min_length=1)
    subject: str = Field(min_length=1)
    error: str | None = None


class EmailSender:
    """Send a DailyDigestEmail through Gmail SMTP using an App Password."""

    def __init__(
        self,
        *,
        smtp_host: str | None = None,
        smtp_port: int | None = None,
        username: str | None = None,
        password: str | None = None,
        recipient: str | None = None,
        from_address: str | None = None,
    ) -> None:
        self.smtp_host = settings.smtp_host if smtp_host is None else smtp_host
        self.smtp_port = settings.smtp_port if smtp_port is None else smtp_port
        self.username = settings.smtp_username if username is None else username
        self.password = settings.smtp_password if password is None else password
        self.recipient = settings.digest_recipient_email if recipient is None else recipient
        configured_from = settings.email_from if from_address is None else from_address
        self.from_address = configured_from or self.username

    def _validate_configuration(self) -> None:
        missing = [
            name
            for name, value in (
                ("SMTP_USERNAME", self.username),
                ("SMTP_PASSWORD", self.password),
                ("DIGEST_RECIPIENT_EMAIL", self.recipient),
            )
            if not value
        ]
        if missing:
            raise ValueError(f"Missing email configuration: {', '.join(missing)}")
        if not self.from_address:
            raise ValueError("EMAIL_FROM or SMTP_USERNAME is required")

    def _message(self, email: DailyDigestEmail) -> EmailMessage:
        self._validate_configuration()
        message = EmailMessage()
        message["Subject"] = email.subject
        message["From"] = self.from_address
        message["To"] = self.recipient
        # Markdown is the plain-text part; HTML is provided as a richer alternative.
        message.set_content(email.markdown)
        message.add_alternative(email.html_body, subtype="html")
        return message

    def send(self, email: DailyDigestEmail) -> EmailSendResult:
        """Send one email and return a safe, non-secret delivery result."""
        message = self._message(email)
        try:
            tls_context = ssl.create_default_context()
            with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=30) as smtp:
                smtp.ehlo()
                smtp.starttls(context=tls_context)
                smtp.ehlo()
                smtp.login(self.username, self.password)
                smtp.send_message(message)
        except (OSError, smtplib.SMTPException) as exc:
            return EmailSendResult(
                sent=False,
                recipient=self.recipient,
                subject=email.subject,
                error=f"{type(exc).__name__}: {exc}",
            )

        return EmailSendResult(
            sent=True,
            recipient=self.recipient,
            subject=email.subject,
        )
