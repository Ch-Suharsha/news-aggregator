"""Production entrypoint for the scheduled daily news digest."""

from app.cli.daily_digest import main

if __name__ == "__main__":
    main()
