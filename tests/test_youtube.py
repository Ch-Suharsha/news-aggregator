from datetime import datetime, timezone

from app.scrapers.youtube import YouTubeScraper


def test_fetch_recent_videos_filters_rss_entries(monkeypatch):
    class Response:
        text = """<?xml version="1.0"?><feed xmlns:yt="http://www.youtube.com/xml/schemas/2015"><entry><yt:videoId>new123</yt:videoId><title>New video</title><link href="https://youtu.be/new123"/><published>2026-09-08T10:00:00+00:00</published><description>New description</description></entry><entry><yt:videoId>old123</yt:videoId><title>Old video</title><published>2026-09-06T10:00:00+00:00</published></entry></feed>"""

        def raise_for_status(self):
            pass

    def fake_get(url, **kwargs):
        assert "channel_id=UC1234567890123456789012" in url
        return Response()

    monkeypatch.setattr("app.scrapers.youtube.httpx.get", fake_get)
    videos = YouTubeScraper().fetch_recent_videos(
        "UC1234567890123456789012",
        now=datetime(2026, 9, 8, 12, tzinfo=timezone.utc),
    )
    assert [video.video_id for video in videos] == ["new123"]
