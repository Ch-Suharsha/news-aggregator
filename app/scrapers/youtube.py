"""YouTube channel RSS ingestion and transcript retrieval."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

import feedparser
import httpx
from bs4 import BeautifulSoup
from app.services.transcripts import get_transcript_text

CHANNEL_ID_PATTERN = re.compile(r"^UC[\w-]{22}$")
CHANNEL_ID_IN_URL_PATTERN = re.compile(r"/channel/(UC[\w-]{22})")
CHANNEL_ID_ANYWHERE_PATTERN = re.compile(r"(?:channel/|channelId[\"'=: ]+)(UC[\w-]{22})")
RSS_URL = "https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"


@dataclass(slots=True)
class YouTubeVideo:
    channel_id: str
    video_id: str
    title: str
    url: str
    published_at: datetime
    description: str = ""
    transcript: str | None = None

    def to_dict(self) -> dict[str, object]:
        result = asdict(self)
        result["published_at"] = self.published_at.isoformat()
        return result


def _normalise_channel_input(channel: str) -> str:
    channel = channel.strip()
    if CHANNEL_ID_PATTERN.fullmatch(channel):
        return channel
    if channel.startswith("@"):
        return f"https://www.youtube.com/{channel}"
    if "://" not in channel:
        return f"https://www.youtube.com/@{channel}"
    return channel


def resolve_channel_id(channel: str, *, timeout: float = 20.0) -> str:
    """Resolve a channel ID, URL, or @handle to the ID required by RSS."""
    value = _normalise_channel_input(channel)
    if CHANNEL_ID_PATTERN.fullmatch(value):
        return value

    path_match = CHANNEL_ID_IN_URL_PATTERN.search(urlparse(value).path)
    if path_match:
        return path_match.group(1)

    response = httpx.get(
        value,
        headers={"User-Agent": "news-aggregator/0.1 (+local development)"},
        follow_redirects=True,
        timeout=timeout,
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


def _entry_datetime(entry: object) -> datetime:
    published = getattr(entry, "published_parsed", None) or getattr(entry, "updated_parsed", None)
    if published is None:
        raise ValueError("YouTube RSS entry has no publication timestamp")
    return datetime(*published[:6], tzinfo=timezone.utc)


def fetch_recent_videos(
    channel: str,
    *,
    hours: int = 24,
    now: datetime | None = None,
    timeout: float = 20.0,
) -> list[YouTubeVideo]:
    """Fetch videos published in the last ``hours`` from one channel."""
    channel_id = resolve_channel_id(channel, timeout=timeout)
    response = httpx.get(RSS_URL.format(channel_id=channel_id), timeout=timeout)
    response.raise_for_status()
    feed = feedparser.parse(response.text)
    if feed.bozo and not feed.entries:
        raise ValueError(f"Could not parse YouTube RSS feed for channel {channel_id}")

    current_time = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    cutoff = current_time - timedelta(hours=hours)
    videos: list[YouTubeVideo] = []
    for entry in feed.entries:
        published_at = _entry_datetime(entry)
        if cutoff <= published_at <= current_time:
            video_id = entry.get("yt_videoid") or entry.get("id", "").rsplit(":", 1)[-1]
            videos.append(
                YouTubeVideo(
                    channel_id=channel_id,
                    video_id=video_id,
                    title=entry.get("title", "Untitled"),
                    url=entry.get("link", f"https://www.youtube.com/watch?v={video_id}"),
                    published_at=published_at,
                    description=entry.get("summary", ""),
                )
            )
    return sorted(videos, key=lambda video: video.published_at, reverse=True)


def fetch_transcript(video_id: str, languages: tuple[str, ...] = ("en",)) -> str:
    """Fetch and flatten a YouTube transcript into text."""
    return get_transcript_text(video_id, languages)


def add_transcripts(videos: list[YouTubeVideo], languages: tuple[str, ...] = ("en",)) -> list[YouTubeVideo]:
    """Fetch transcripts independently so one unavailable transcript does not stop the batch."""
    for video in videos:
        try:
            video.transcript = fetch_transcript(video.video_id, languages)
        except Exception:
            video.transcript = None
    return videos
