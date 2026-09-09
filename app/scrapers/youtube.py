"""Typed YouTube channel scraper for RSS videos and transcripts."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import urlparse

import feedparser
import httpx
from bs4 import BeautifulSoup
from pydantic import BaseModel, ConfigDict
from youtube_transcript_api import YouTubeTranscriptApi

CHANNEL_ID_PATTERN = re.compile(r"^UC[\w-]{22}$")
CHANNEL_ID_IN_URL_PATTERN = re.compile(r"/channel/(UC[\w-]{22})")
CHANNEL_ID_ANYWHERE_PATTERN = re.compile(r"(?:channel/|channelId[\"'=: ]+)(UC[\w-]{22})")
RSS_URL = "https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"


class Transcript(BaseModel):
    """A video's transcript represented as plain text."""

    text: str


class ChannelVideo(BaseModel):
    """The normalized data collected for one channel video."""

    model_config = ConfigDict(extra="forbid")

    title: str
    url: str
    video_id: str
    published_at: datetime
    description: str
    transcript: Optional[str] = None


class YouTubeScraper:
    """Single interface for channel discovery, RSS videos, and transcripts."""

    def __init__(
        self,
        *,
        timeout: float = 20.0,
        transcript_api: YouTubeTranscriptApi | None = None,
    ) -> None:
        self.timeout = timeout
        self.transcript_api = transcript_api or YouTubeTranscriptApi()

    @staticmethod
    def _normalise_channel_input(channel: str) -> str:
        channel = channel.strip()
        if CHANNEL_ID_PATTERN.fullmatch(channel):
            return channel
        if channel.startswith("@"):
            return f"https://www.youtube.com/{channel}"
        if "://" not in channel:
            return f"https://www.youtube.com/@{channel}"
        return channel

    def resolve_channel_id(self, channel: str) -> str:
        """Resolve a channel ID, URL, or @handle to the ID required by RSS."""
        value = self._normalise_channel_input(channel)
        if CHANNEL_ID_PATTERN.fullmatch(value):
            return value

        path_match = CHANNEL_ID_IN_URL_PATTERN.search(urlparse(value).path)
        if path_match:
            return path_match.group(1)

        response = httpx.get(
            value,
            headers={"User-Agent": "news-aggregator/0.1 (+local development)"},
            follow_redirects=True,
            timeout=self.timeout,
        )
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        for tag in soup.find_all(["meta", "link"]):
            content = tag.get("content") or tag.get("href") or ""
            match = CHANNEL_ID_ANYWHERE_PATTERN.search(content)
            if match:
                return match.group(1)

        match = CHANNEL_ID_ANYWHERE_PATTERN.search(response.text)
        if match:
            return match.group(1)
        raise ValueError(f"Could not resolve a YouTube channel ID from: {channel}")

    @staticmethod
    def _entry_datetime(entry: object) -> datetime:
        published = getattr(entry, "published_parsed", None) or getattr(
            entry, "updated_parsed", None
        )
        if published is None:
            raise ValueError("YouTube RSS entry has no publication timestamp")
        return datetime(*published[:6], tzinfo=timezone.utc)

    @staticmethod
    def _is_short(url: str) -> bool:
        """Return whether a YouTube URL uses the Shorts route."""
        return urlparse(url).path.rstrip("/").startswith("/shorts/")

    def fetch_recent_videos(
        self,
        channel: str,
        *,
        hours: int = 24,
        now: datetime | None = None,
    ) -> list[ChannelVideo]:
        """Fetch videos published in the last ``hours`` from one channel."""
        channel_id = self.resolve_channel_id(channel)
        response = httpx.get(RSS_URL.format(channel_id=channel_id), timeout=self.timeout)
        response.raise_for_status()
        feed = feedparser.parse(response.text)
        if feed.bozo and not feed.entries:
            raise ValueError(f"Could not parse YouTube RSS feed for channel {channel_id}")

        current_time = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        cutoff = current_time - timedelta(hours=hours)
        videos: list[ChannelVideo] = []
        for entry in feed.entries:
            published_at = self._entry_datetime(entry)
            if cutoff <= published_at <= current_time:
                video_id = entry.get("yt_videoid") or entry.get("id", "").rsplit(":", 1)[-1]
                url = entry.get("link", f"https://www.youtube.com/watch?v={video_id}")
                if self._is_short(url):
                    continue
                videos.append(
                    ChannelVideo(
                        title=entry.get("title", "Untitled"),
                        url=url,
                        video_id=video_id,
                        published_at=published_at,
                        description=entry.get("summary", ""),
                    )
                )
        return sorted(videos, key=lambda video: video.published_at, reverse=True)

    def get_transcript(
        self,
        video_id: str,
        languages: tuple[str, ...] = ("en",),
    ) -> Transcript:
        """Fetch one video's transcript and return it as a typed model."""
        video_id = video_id.strip()
        if not video_id:
            raise ValueError("video_id cannot be empty")
        fetched = self.transcript_api.fetch(video_id, languages=list(languages))
        text = "\n".join(snippet.text.strip() for snippet in fetched if snippet.text.strip())
        return Transcript(text=text)

    def add_transcripts(
        self,
        videos: list[ChannelVideo],
        languages: tuple[str, ...] = ("en",),
    ) -> list[ChannelVideo]:
        """Add transcripts independently so one unavailable transcript does not stop the batch."""
        for video in videos:
            try:
                video.transcript = self.get_transcript(video.video_id, languages).text
            except Exception:
                video.transcript = None
        return videos


if __name__ == "__main__":
    scraper = YouTubeScraper()
    videos = scraper.fetch_recent_videos("UCn8ujwUInbJkBhffxqAPBVQ", hours=720)
    scraper.add_transcripts(videos)
    for video in videos:
        print(video.model_dump(mode="json"))
