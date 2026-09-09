"""DeepSeek Responses API agent for creating a daily news email."""

from __future__ import annotations

from datetime import UTC, date, datetime
from html import escape
from pathlib import Path

from openai import OpenAI
from pydantic import BaseModel, ConfigDict, Field, PositiveInt, computed_field

from app.core.config import settings
from app.db.models import DigestItem

PROMPT_PATH = Path(__file__).with_name("email_agent_system_prompt.md")
USER_INSIGHTS_PATH = Path(__file__).with_name("user_insights.md")


class EmailIntroOutput(BaseModel):
    """Structured subject and introduction returned by the LLM."""

    model_config = ConfigDict(extra="forbid")

    subject: str = Field(min_length=1, max_length=120)
    intro: str = Field(min_length=1, max_length=700)


class EmailArticle(BaseModel):
    """One ranked article rendered into the email."""

    model_config = ConfigDict(extra="forbid")

    rank: PositiveInt
    relevance_score: int = Field(ge=0, le=100)
    source: str = Field(min_length=1)
    title: str = Field(min_length=1)
    url: str = Field(min_length=1)
    summary: str = Field(min_length=1)


class DailyDigestEmail(BaseModel):
    """The delivery-ready structure produced for one daily digest."""

    model_config = ConfigDict(extra="forbid")

    subject: str = Field(min_length=1)
    greeting: str = Field(min_length=1)
    intro: str = Field(min_length=1)
    articles: list[EmailArticle] = Field(min_length=1, max_length=10)

    @computed_field
    @property
    def markdown(self) -> str:
        """The section-based Markdown body that can be sent as an email."""
        return self.to_markdown()

    @computed_field
    @property
    def text_body(self) -> str:
        """A plain-text fallback for email clients that do not render Markdown."""
        return self.to_plain_text()

    @computed_field
    @property
    def html_body(self) -> str:
        """An HTML fallback for delivery providers."""
        return self.to_html()

    def to_markdown(self) -> str:
        """Render the email as headings and sections rather than a bullet list."""
        sections = [
            f"# {self.subject}",
            self.greeting,
            "## Today's overview",
            self.intro,
        ]
        for article in self.articles:
            sections.extend(
                [
                    f"## {article.rank}. {article.title}",
                    f"**Source:** {article.source}",
                    f"**Relevance score:** {article.relevance_score}/100",
                    "### Summary",
                    article.summary,
                    f"[Read the original source]({article.url})",
                ]
            )
        return "\n\n".join(sections)

    def to_plain_text(self) -> str:
        """Render a readable text-only email body."""
        sections = [self.greeting, "", self.intro, ""]
        for article in self.articles:
            sections.extend(
                [
                    f"{article.rank}. {article.title}",
                    f"Source: {article.source} | Relevance: {article.relevance_score}/100",
                    article.summary,
                    article.url,
                    "",
                ]
            )
        return "\n".join(sections).strip()

    def to_html(self) -> str:
        """Render a minimal HTML email body suitable for a delivery provider."""
        article_markup = []
        for article in self.articles:
            article_markup.append(
                f"<section><h2>{article.rank}. <a href=\"{escape(article.url, quote=True)}\">"
                f"{escape(article.title)}</a></h2>"
                f"<p><small>{escape(article.source)} · "
                f"Relevance: {article.relevance_score}/100</small></p>"
                f"<h3>Summary</h3>"
                f"<p>{escape(article.summary)}</p>"
                "</section>"
            )
        return (
            "<html><body>"
            f"<h1>{escape(self.subject)}</h1>"
            f"<p>{escape(self.greeting)}</p>"
            "<h2>Today's overview</h2>"
            f"<p>{escape(self.intro)}</p>"
            f"{''.join(article_markup)}"
            "</body></html>"
        )


class EmailAgent:
    """Create a structured email from the curator's ranked digest items."""

    def __init__(
        self,
        *,
        client: OpenAI | None = None,
        model: str | None = None,
        system_prompt: str | None = None,
        recipient_name: str | None = None,
    ) -> None:
        if client is None:
            if not settings.deepseek_api_key:
                raise ValueError("DEEPSEEK_API_KEY is required to create the email intro")
            client = OpenAI(
                api_key=settings.deepseek_api_key,
                base_url=settings.deepseek_base_url,
            )
        self.client = client
        self.model = model or settings.deepseek_model
        self.system_prompt = system_prompt or self._load_system_prompt()
        self.recipient_name = (recipient_name or settings.digest_recipient_name).strip() or "Harsha"

    @staticmethod
    def _load_system_prompt() -> str:
        prompt = PROMPT_PATH.read_text(encoding="utf-8").strip()
        insights = USER_INSIGHTS_PATH.read_text(encoding="utf-8").strip()
        return f"{prompt}\n\nUser insights:\n{insights}"

    @staticmethod
    def _candidate_input(items: list[DigestItem]) -> str:
        candidates: list[str] = []
        for item in items:
            article = item.article
            source = article.source if article else None
            candidates.append(
                f"Rank: {item.rank}\n"
                f"Relevance score: {item.relevance_score}\n"
                f"Source: {source.name if source else 'Unknown source'}\n"
                f"Title: {item.title}\n"
                f"URL: {item.url}\n"
                f"Summary: {item.summary}"
            )
        return "Write the opening introduction for these ranked articles:\n\n" + "\n\n---\n\n".join(candidates)

    def generate_intro(self, items: list[DigestItem]) -> EmailIntroOutput:
        """Generate only the short thematic introduction with structured output."""
        if not items:
            raise ValueError("At least one ranked digest item is required")

        response = self.client.responses.parse(
            model=self.model,
            instructions=self.system_prompt,
            input=self._candidate_input(items),
            text_format=EmailIntroOutput,
            temperature=0.2,
            store=False,
        )
        parsed = response.output_parsed
        if parsed is None:
            raise ValueError("DeepSeek returned no structured email introduction")
        return parsed

    def build_email(
        self,
        items: list[DigestItem],
        *,
        digest_date: date | None = None,
    ) -> DailyDigestEmail:
        """Generate the intro and build the deterministic delivery structure."""
        if not items:
            raise ValueError("At least one ranked digest item is required")

        ordered_items = sorted(items, key=lambda item: (item.rank or 10**9, item.id))[:10]
        if any(item.rank is None or item.relevance_score is None for item in ordered_items):
            raise ValueError("Every email item must have a curator rank and relevance score")

        intro = self.generate_intro(ordered_items)
        date_label = (digest_date or datetime.now(UTC).date()).isoformat()
        articles = [
            EmailArticle(
                rank=item.rank,
                relevance_score=item.relevance_score,
                source=item.article.source.name if item.article and item.article.source else "Unknown source",
                title=item.title,
                url=item.url,
                summary=item.summary,
            )
            for item in ordered_items
        ]
        return DailyDigestEmail(
            subject=f"{intro.subject.strip()} - {date_label}",
            greeting=f"Hey {self.recipient_name}, here is today's AI news digest.",
            intro=intro.intro,
            articles=articles,
        )
