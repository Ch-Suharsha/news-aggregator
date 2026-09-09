"""DeepSeek Responses API agent for ranking recent digest items."""

from __future__ import annotations

from pathlib import Path

from openai import OpenAI
from pydantic import BaseModel, ConfigDict, Field, PositiveInt

from app.core.config import settings
from app.db.models import DigestItem

PROMPT_PATH = Path(__file__).with_name("news_curator_system_prompt.md")
USER_INSIGHTS_PATH = Path(__file__).with_name("user_insights.md")


class RankedDigestItem(BaseModel):
    """One ranked digest item returned by the curator."""

    model_config = ConfigDict(extra="forbid")

    digest_item_id: PositiveInt
    rank: PositiveInt
    relevance_score: int = Field(ge=0, le=100)
    reasoning: str = Field(min_length=1)


class NewsCurationOutput(BaseModel):
    """Structured ranking returned for a candidate list."""

    model_config = ConfigDict(extra="forbid")

    rankings: list[RankedDigestItem] = Field(min_length=1)


class NewsCuratorAgent:
    """Rank digest items according to the user's profile and interests."""

    def __init__(
        self,
        *,
        client: OpenAI | None = None,
        model: str | None = None,
        system_prompt: str | None = None,
    ) -> None:
        if client is None:
            if not settings.deepseek_api_key:
                raise ValueError("DEEPSEEK_API_KEY is required to create news rankings")
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
    def _candidate_input(items: list[DigestItem]) -> str:
        candidates: list[str] = []
        for item in items:
            article = item.article
            source = article.source if article else None
            published_at = article.published_at.isoformat() if article and article.published_at else "Unknown"
            candidates.append(
                f"Candidate digest_item_id: {item.id}\n"
                f"Source: {source.name if source else 'Unknown'}\n"
                f"Source type: {source.source_type if source else 'Unknown'}\n"
                f"Published at: {published_at}\n"
                f"Title: {item.title}\n"
                f"URL: {item.url}\n"
                f"Digest summary: {item.summary}"
            )
        return "Rank these candidate digest items:\n\n" + "\n\n---\n\n".join(candidates)

    def rank(self, items: list[DigestItem]) -> NewsCurationOutput:
        """Return a validated ranking for all supplied digest items."""
        if not items:
            raise ValueError("At least one digest item is required for ranking")
        response = self.client.responses.parse(
            model=self.model,
            instructions=self.system_prompt,
            input=self._candidate_input(items),
            text_format=NewsCurationOutput,
            temperature=0.1,
            store=False,
        )
        parsed = response.output_parsed
        if parsed is None:
            raise ValueError("DeepSeek returned no structured news ranking")
        return parsed
