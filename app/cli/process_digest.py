from __future__ import annotations

import argparse
import json

from app.db.session import create_tables
from app.services.digest_processor import DigestProcessor


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate structured digest items for collected articles.")
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()

    create_tables()
    result = DigestProcessor().process_pending(limit=args.limit)
    print(json.dumps(result.__dict__, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
