"""Simulator settings (env-overridable)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Settings:
    redis_url: str = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")
    scoring_api_url: str = os.getenv("SCORING_API_URL", "http://127.0.0.1:8010")
    stream: str = "txn:events"          # must match scoring-api/app/config.py
    group: str = "scorers"              # must match scoring-api/app/config.py
    stream_maxlen: int = 200_000
    max_backlog: int = int(os.getenv("MAX_BACKLOG", 20_000))
    pool_size: int = int(os.getenv("POOL_SIZE", 3_000_000))
    base_rps: float = float(os.getenv("BASE_RPS", 20))
    autostart: bool = os.getenv("AUTOSTART", "1") == "1"
    seed: int = 42
    data_dir: Path = BASE / "data"
    cors_origins: tuple = ("http://localhost:3010", "http://127.0.0.1:3010")


settings = Settings()