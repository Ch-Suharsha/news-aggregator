from datetime import datetime, timezone

from app.scrapers.openai import OpenAIScraper


def test_fetch_recent_articles_parses_and_filters_rss(monkeypatch):
    class Response:
        text = """<?xml version="1.0"?><rss><channel><item><title>New article</title><description>Summary</description><link>https://openai.com/index/new-article</link><guid>https://openai.com/index/new-article</guid><category>Research</category><pubDate>Tue, 08 Sep 2026 10:00:00 GMT</pubDate></item><item><title>Old article</title><description>Old summary</description><link>https://openai.com/index/old-article</link><guid>https://openai.com/index/old-article</guid><pubDate>Sun, 06 Sep 2026 10:00:00 GMT</pubDate></item></channel></rss>"""

        def raise_for_status(self):
            pass

    def fake_get(url, **kwargs):
        assert url == "https://openai.com/news/rss.xml"
        return Response()

    monkeypatch.setattr("app.scrapers.openai.httpx.get", fake_get)
    articles = OpenAIScraper().fetch_recent_articles(
        now=datetime(2026, 9, 8, 12, tzinfo=timezone.utc),
    )

    assert len(articles) == 1
    assert articles[0].title == "New article"
    assert articles[0].category == "Research"
