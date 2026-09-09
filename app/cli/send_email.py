from __future__ import annotations

import argparse
import json

from app.db.session import create_tables
from app.services.email_processor import EmailProcessor
from app.services.email_sender import EmailSender


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate and send the daily AI news email.")
    parser.add_argument("--hours", type=int, default=24)
    parser.add_argument("--limit", type=int, default=10, help="Number of ranked articles (maximum 10).")
    args = parser.parse_args()

    create_tables()
    generation = EmailProcessor().process_pending(hours=args.hours, limit=args.limit)
    output = {"generation": generation.model_dump(mode="json"), "delivery": None}
    if generation.email is not None and generation.generated:
        try:
            output["delivery"] = EmailSender().send(generation.email).model_dump(mode="json")
        except ValueError as exc:
            output["delivery"] = {
                "sent": False,
                "subject": generation.email.subject,
                "error": str(exc),
            }
    print(json.dumps(output, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
