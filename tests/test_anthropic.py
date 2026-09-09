from datetime import datetime, timezone

from app.scrapers.anthropic import AnthropicScraper, AnthropicTopic


def test_fetch_recent_articles_combines_and_filters_feeds(monkeypatch):
    class Response:
        def __init__(self, title, url, published_at):
            self.text = f"""<?xml version="1.0"?><rss><channel><item><title>{title}</title><description>Summary</description><link>{url}</link><guid>{url}</guid><pubDate>{published_at}</pubDate></item></channel></rss>"""

        def raise_for_status(self):
            pass

    responses = {
        "news.xml": Response("News item", "https://anthropic.com/news/item", "Tue, 08 Sep 2026 10:00:00 GMT"),
        "research.xml": Response("Research item", "https://anthropic.com/research/item", "Tue, 08 Sep 2026 09:00:00 GMT"),
        "engineering.xml": Response("Engineering item", "https://anthropic.com/engineering/item", "Sun, 06 Sep 2026 09:00:00 GMT"),
        "red.xml": Response("Old red-team item", "https://red.anthropic.com/item", "Sun, 06 Sep 2026 08:00:00 GMT"),
    }

    def fake_get(url, **kwargs):
        return responses[url.rsplit("/", 1)[-1]]

    feeds = {
        AnthropicTopic.NEWS: "https://example.com/news.xml",
        AnthropicTopic.RESEARCH: "https://example.com/research.xml",
        AnthropicTopic.ENGINEERING: "https://example.com/engineering.xml",
        AnthropicTopic.FRONTIER_RED_TEAM: "https://example.com/red.xml",
    }
    monkeypatch.setattr("app.scrapers.anthropic.httpx.get", fake_get)

    articles = AnthropicScraper(feeds=feeds).fetch_recent_articles(
        now=datetime(2026, 9, 8, 12, tzinfo=timezone.utc),
    )

    assert [article.title for article in articles] == ["News item", "Research item"]
    assert articles[0].topic == AnthropicTopic.NEWS
