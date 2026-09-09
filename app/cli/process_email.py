from __future__ import annotations

import argparse
import json

from app.db.session import create_tables
from app.services.email_processor import EmailProcessor


def main() -> None:
    parser = argparse.ArgumentParser(description="Build an email from curator-ranked news items.")
    parser.add_argument("--hours", type=int, default=24)
    parser.add_argument("--limit", type=int, default=10, help="Number of ranked articles (maximum 10).")
    args = parser.parse_args()

    create_tables()
    result = EmailProcessor().process_pending(hours=args.hours, limit=args.limit)
    print(json.dumps(result.__dict__, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
