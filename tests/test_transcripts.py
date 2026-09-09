from types import SimpleNamespace

from app.scrapers.youtube import YouTubeScraper


def test_get_transcript_text_returns_plain_text(monkeypatch):
    class FakeTranscriptApi:
        def fetch(self, video_id, languages):
            assert video_id == "video123"
            assert languages == ["en"]
            return [
                SimpleNamespace(text=" First sentence "),
                SimpleNamespace(text=""),
                SimpleNamespace(text="Second sentence"),
            ]

    scraper = YouTubeScraper()
    scraper.transcript_api = FakeTranscriptApi()

    transcript = scraper.get_transcript(" video123 ")

    assert transcript.text == "First sentence\nSecond sentence"
