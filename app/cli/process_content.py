from __future__ import annotations

import argparse
import json

from app.db.session import create_tables
from app.services.content_processor import ContentProcessor


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract Markdown and YouTube transcripts.")
    parser.add_argument("--batch-size", type=int, default=50)
    parser.add_argument("--retry-failed", action="store_true")
    args = parser.parse_args()

    create_tables()
    result = ContentProcessor().process_pending(
        batch_size=args.batch_size,
        retry_failed=args.retry_failed,
    )
    print(json.dumps(result.__dict__, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
