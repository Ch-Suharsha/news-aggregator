from __future__ import annotations

import argparse
import json

from app.db.session import create_tables
from app.services.curation_processor import CurationProcessor


def main() -> None:
    parser = argparse.ArgumentParser(description="Rank recent digest items for the user.")
    parser.add_argument("--hours", type=int, default=24)
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()

    create_tables()
    result = CurationProcessor().process_pending(hours=args.hours, limit=args.limit)
    print(json.dumps(result.__dict__, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
