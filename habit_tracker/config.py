import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def _database_url() -> str:
    """Build the SQL connection string strictly from the OS environment.

    Required real SQL server (PostgreSQL or MySQL) - SQLite is intentionally
    not supported. Set DATABASE_URL, e.g.:
      postgresql+psycopg2://user:pass@localhost:5432/habit_tracker
      mysql+pymysql://user:pass@localhost:3306/habit_tracker
    """
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError(
            "DATABASE_URL is not set. Export it before running, e.g.\n"
            "  export DATABASE_URL=postgresql+psycopg2://user:pass@localhost:5432/habit_tracker"
        )
    if url.startswith("sqlite"):
        raise RuntimeError("SQLite is not supported. Use PostgreSQL or MySQL.")
    return url


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", os.urandom(32).hex())
    SQLALCHEMY_DATABASE_URI = _database_url()
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    UPLOAD_FOLDER = os.environ.get("UPLOAD_FOLDER", os.path.join(BASE_DIR, "static", "uploads"))
    MUSIC_FOLDER = os.environ.get("MUSIC_FOLDER", os.path.join(BASE_DIR, "static", "music"))
    MAX_CONTENT_LENGTH = int(os.environ.get("MAX_UPLOAD_MB", "10")) * 1024 * 1024

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.environ.get("FORCE_HTTPS_COOKIES", "false").lower() == "true"
    REMEMBER_COOKIE_HTTPONLY = True

    DEVIATION_ZSCORE_THRESHOLD = float(os.environ.get("DEVIATION_ZSCORE_THRESHOLD", "2.0"))
    MIN_HISTORY_FOR_DEVIATION = int(os.environ.get("MIN_HISTORY_FOR_DEVIATION", "5"))
