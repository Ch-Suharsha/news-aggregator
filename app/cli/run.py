from __future__ import annotations

import argparse
import json

from app.services.runner import NewsRunner
from app.db.session import create_tables


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect all configured AI news sources.")
    parser.add_argument("--hours", type=int, default=24, help="Look-back window (default: 24)")
    args = parser.parse_args()

    create_tables()
    result = NewsRunner().run(hours=args.hours)
    print(json.dumps(result.model_dump(mode="json"), indent=2, ensure_ascii=False))
