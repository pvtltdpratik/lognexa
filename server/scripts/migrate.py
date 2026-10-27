"""Apply database migrations (safe to run repeatedly; never deletes data).

Usage (from server/):
    .venv\Scripts\python -m scripts.migrate
"""

from app.database import engine
from app.migrations import upgrade_database


def main() -> None:
    print(f"Database: {engine.url.render_as_string(hide_password=True)}")
    print("Result:", upgrade_database(engine))


if __name__ == "__main__":
    main()
