from __future__ import annotations

import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key")
    DATABASE_URL = os.getenv(
        "DATABASE_URL",
        f"sqlite:///{BASE_DIR / 'grocery_platform.db'}",
    )
    STALE_QUERY_TTL_HOURS = int(os.getenv("STALE_QUERY_TTL_HOURS", "24"))
    JSON_SORT_KEYS = False
    FRONTEND_DIST = BASE_DIR / "frontend" / "dist"
