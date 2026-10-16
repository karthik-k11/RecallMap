
import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent


class Config:
    SECRET_KEY = os.environ.get(
        "RECALLMAP_SECRET_KEY",
        "recallmap-local-development-key",
    )

    DATABASE_PATH = BASE_DIR / "instance" / "recallmap.db"

    TESTING = False