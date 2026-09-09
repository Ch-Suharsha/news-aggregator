from __future__ import annotations

import argparse
import json

from app.scrapers.youtube import YouTubeScraper


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Fetch recent YouTube videos and transcripts.")
    parser.add_argument("channels", nargs="+", help="Channel ID, @handle, channel URL, or handle")
    parser.add_argument("--hours", type=int, default=24, help="Look-back window (default: 24)")
    parser.add_argument("--language", action="append", default=None, help="Transcript language, repeatable")
    parser.add_argument("--no-transcripts", action="store_true", help="Skip transcript requests")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    languages = tuple(args.language or ["en"])
    scraper = YouTubeScraper()
    results = []
    for channel in args.channels:
        videos = scraper.fetch_recent_videos(channel, hours=args.hours)
        if not args.no_transcripts:
            scraper.add_transcripts(videos, languages)
        results.extend(video.model_dump(mode="json") for video in videos)
    print(json.dumps(results, indent=2, ensure_ascii=False))
