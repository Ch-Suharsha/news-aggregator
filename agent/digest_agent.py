"""DeepSeek Responses API agent for one digest item."""

from __future__ import annotations

from pathlib import Path

from openai import OpenAI
from pydantic import BaseModel, ConfigDict, Field

from app.core.config import settings
from app.db.models import Article

PROMPT_PATH = Path(__file__).with_name("digest_item_system_prompt.md")
USER_INSIGHTS_PATH = Path(__file__).with_name("user_insights.md")


class DigestItemOutput(BaseModel):
    """Structured output requested from the LLM."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1)
    summary: str = Field(min_length=1)


class DigestAgent:
    """Generate a structured title and short summary for one article."""

    def __init__(
        self,
        *,
        client: OpenAI | None = None,
        model: str | None = None,
        system_prompt: str | None = None,
    ) -> None:
        if client is None:
            if not settings.deepseek_api_key:
                raise ValueError("DEEPSEEK_API_KEY is required to create digest summaries")
            client = OpenAI(
                api_key=settings.deepseek_api_key,
                base_url=settings.deepseek_base_url,
            )
        self.client = client
        self.model = model or settings.deepseek_model
        self.system_prompt = system_prompt or self._load_system_prompt()

    @staticmethod
    def _load_system_prompt() -> str:
        prompt = PROMPT_PATH.read_text(encoding="utf-8").strip()
        insights = USER_INSIGHTS_PATH.read_text(encoding="utf-8").strip()
        return f"{prompt}\n\nUser insights:\n{insights}"

    @staticmethod
    def _article_input(article: Article) -> str:
        source_name = article.source.name if article.source else "Unknown source"
        published_at = article.published_at.isoformat() if article.published_at else "Unknown"
        content = article.content_text or article.summary or "No source text was collected."
        return (
            "Source record:\n"
            f"Source: {source_name}\n"
            f"Title: {article.title}\n"
            f"URL: {article.url}\n"
            f"Published at: {published_at}\n"
            f"Source summary: {article.summary or 'None'}\n"
            f"Collected content or transcript:\n{content}"
        )

    def summarize(self, article: Article) -> DigestItemOutput:
        """Generate one structured digest item from an Article database row."""
        response = self.client.responses.parse(
            model=self.model,
            instructions=self.system_prompt,
            input=self._article_input(article),
            text_format=DigestItemOutput,
            temperature=0.2,
            store=False,
        )
        parsed = response.output_parsed
        if parsed is None:
            raise ValueError("DeepSeek returned no structured digest item")
        return parsed
