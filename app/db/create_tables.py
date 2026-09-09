"""Initialize all SQLAlchemy tables in the configured database."""

from .session import create_tables


def main() -> None:
    create_tables()
    print("Database tables created successfully.")


if __name__ == "__main__":
    main()
