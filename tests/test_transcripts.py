from types import SimpleNamespace

from app.services import transcripts


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

    monkeypatch.setattr(transcripts, "YouTubeTranscriptApi", lambda: FakeTranscriptApi())

    assert transcripts.get_transcript_text(" video123 ") == "First sentence\nSecond sentence"
