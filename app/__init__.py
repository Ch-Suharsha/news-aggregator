"""News aggregator application package."""

from .core.config import settings


def main() -> None:
    print(f"News aggregator configured for {settings.database_url}")
