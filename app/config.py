import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent


class Config:
    # Flask session secret
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-insecure-change-me")

    # Database
    DB_PATH = os.getenv("DB_PATH", str(BASE_DIR / "charity.sqlite3"))
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL", f"sqlite:///{DB_PATH}")
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
    }

    # Bootstrap / QR payment info (UPI-style)
    UPI_PAYEE = os.getenv("UPI_PAYEE", "charity@example@upi")
    UPI_PAYER_NAME = os.getenv("UPI_PAYER_NAME", "Charity Trust")
    UPI_PURPOSE_PREFIX = os.getenv("UPI_PURPOSE_PREFIX", "Donation")

    # Admin defaults (set env vars for real use)
    ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
    ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")

    # App flags
    AUTO_CREATE_DB = os.getenv("AUTO_CREATE_DB", "1") in {"1", "true", "True", "yes", "YES"}
    SEED_DUMMY_DATA = os.getenv("SEED_DUMMY_DATA", "1") in {"1", "true", "True", "yes", "YES"}

    # Uploads
    UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", str(BASE_DIR / "app" / "static" / "uploads")))

    # Pagination defaults
    DEFAULT_PAGE_SIZE = int(os.getenv("DEFAULT_PAGE_SIZE", "10"))

