"""Services for retrieving YouTube transcripts."""

from youtube_transcript_api import YouTubeTranscriptApi


def get_transcript_text(video_id: str, languages: tuple[str, ...] = ("en",)) -> str:
    """Return a YouTube video's transcript as plain text."""
    video_id = video_id.strip()
    if not video_id:
        raise ValueError("video_id cannot be empty")

    transcript = YouTubeTranscriptApi().fetch(video_id, languages=list(languages))
    return "\n".join(snippet.text.strip() for snippet in transcript if snippet.text.strip())
