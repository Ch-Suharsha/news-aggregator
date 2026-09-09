# AI News Aggregator

A Python/PostgreSQL foundation for collecting YouTube videos, blogs, and newsletters,
then producing a user-tailored daily digest with links to original sources.

## Current structure

```text
app/                 application code, models, database, and adapters
agent/               agent implementations, prompts, and editable user insights
docker/              local PostgreSQL container
```

The initial collection workflow is exposed through `app/services/runner.py`.
Configured YouTube channel IDs live in `app/core/sources.py`. The runner collects
metadata first and stores it in PostgreSQL; transcripts, full article content, and
LLM summarization are intentionally separate processing steps. Run
`PYTHONPATH=. uv run python -m app.cli.process_content` for Stage 2 content
extraction and `PYTHONPATH=. uv run python -m app.cli.process_digest` for Stage 3
per-article digest summaries. Run `PYTHONPATH=. uv run python -m app.cli.process_curation --hours 24`
for Stage 4 user-interest ranking. Run
`PYTHONPATH=. uv run python -m app.cli.process_email --hours 24 --limit 10` for a
delivery-ready email preview built from the curator's top-ranked items. The
email agent generates only the opening subject and introduction; the ranked
article list is assembled deterministically from the database.

The article model reserves `content_text` and `content_html` for full page context.
Collection stores source metadata and summaries first; later processing can populate
those fields without changing the original article record. YouTube sources can be
represented by `youtube_channel_id`, while blog and newsletter sources use their
configured feed URL.

## Run locally

```bash
cp .env.example .env
docker compose -f docker/docker-compose.yml up -d
uv sync
uv run python -c "from app.db import create_tables; create_tables()"
```

The only container currently needed is PostgreSQL. This keeps the local setup close
to a managed Postgres deployment while leaving the Python app and scheduled worker
free to run as a Render web service or cron job later.

## Planned next slices

1. Add source management and ingestion commands.
2. Add YouTube Data API and HTML/RSS/newsletter adapters with deduplication.
3. Add SMTP/Resend delivery, a daily Render cron entry, and Alembic migrations.

Keep API keys, SMTP credentials, and database URLs in environment variables; prompts
and user insights are version-controlled project configuration.

## Provider choices

The initial LLM provider is DeepSeek. Its API is OpenAI-compatible, so the project
can use the familiar `openai` Python SDK with `https://api.deepseek.com` as the base
URL and `DEEPSEEK_API_KEY` from the environment.

For delivery, the recommended beginner-friendly option is Resend. Its free plan is
currently sufficient for one daily digest, and it can be called with a small HTTP
client instead of configuring Gmail OAuth or SMTP. For production sending, verify a
domain in Resend and set `EMAIL_FROM` to an address on that domain. The default
`onboarding@resend.dev` value is intended for initial testing.

Blog ingestion will retain the complete cleaned page context in the database without
LLM summarization or arbitrary truncation. The system prompt and user-specific
instructions remain in the separate `agent/` directory.
