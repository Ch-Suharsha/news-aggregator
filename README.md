# AI News Aggregator

A Python/PostgreSQL foundation for collecting YouTube videos, blogs, and newsletters,
then producing a user-tailored daily digest with links to original sources.

## Current structure

```text
app/                 application code, models, database, and adapters
agent/               agent implementations, prompts, and editable user insights
docker/              local PostgreSQL container
main.py              production entrypoint for the scheduled pipeline
render.yaml          Render Cron Job and PostgreSQL Blueprint
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
delivery-ready Markdown email preview built from the curator's top-ranked items.
Use `PYTHONPATH=. uv run python -m app.cli.send_email --hours 24 --limit 10` to
generate and send it through Gmail SMTP. The email agent generates only the
opening subject and introduction; the ranked article sections are assembled
deterministically from the database.

To run the complete pipeline as one command, use:

```bash
PYTHONPATH=. uv run python -m app.cli.daily_digest --hours 24
```

This runs collection, Markdown/transcript extraction, digest summarization,
user-interest ranking, email generation, and Gmail delivery in that order. It
does not send an email when the ranking stage fails.

## Scheduling

On macOS or Linux, schedule the single command with cron. For example, this
runs at 08:00 according to the machine's cron timezone:

```cron
0 8 * * * cd /Users/Checkout/Documents/projects/news-aggregator && PYTHONPATH=. /absolute/path/to/uv run python -m app.cli.daily_digest --hours 24 >> daily_digest.log 2>&1
```

For production, the repository includes a Render Blueprint. It defines a Docker
Cron Job and a managed Render PostgreSQL database. The Cron Job uses the Docker
image's `python main.py` command and the schedule in `render.yaml`:

```bash
python main.py
```

Render provides the production `DATABASE_URL` to the container through the
database connection defined in the Blueprint. The local Docker Compose database
is only for development; it is not used by the deployed Cron Job. Change the
Render `schedule` or `DIGEST_HOURS` value when you need a different daily run
time or look-back window.

The deployment uses a fresh production database. It does not copy the local
development database automatically.

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

The local container is PostgreSQL only. In production, Render runs the Python
Docker container as a Cron Job and provides a separate managed PostgreSQL service.

## Planned next slices

1. Add source management and ingestion commands.
2. Add YouTube Data API and HTML/RSS/newsletter adapters with deduplication.
3. Add Alembic migrations when the schema begins changing regularly.

Keep API keys, SMTP credentials, and database URLs in environment variables; prompts
and user insights are version-controlled project configuration.

## Provider choices

The initial LLM provider is DeepSeek. Its API is OpenAI-compatible, so the project
can use the familiar `openai` Python SDK with `https://api.deepseek.com` as the base
URL and `DEEPSEEK_API_KEY` from the environment.

For delivery, the current implementation uses Gmail SMTP with a Google App
Password. Set `SMTP_USERNAME`, `SMTP_PASSWORD`, and `DIGEST_RECIPIENT_EMAIL` in
`.env`; `SMTP_PASSWORD` must be the App Password, not your normal Gmail password.
The `send-email` command uses the Markdown body as the plain-text part and the
same content's HTML rendering as the rich-email alternative.

Blog ingestion will retain the complete cleaned page context in the database without
LLM summarization or arbitrary truncation. The system prompt and user-specific
instructions remain in the separate `agent/` directory.
