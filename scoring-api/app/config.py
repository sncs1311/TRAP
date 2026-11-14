"""Runtime settings (env-overridable)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]


def _i(k: str, d: int) -> int:
    return int(os.getenv(k, d))


def _f(k: str, d: float) -> float:
    return float(os.getenv(k, d))


@dataclass(frozen=True)
class Settings:
    redis_url: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    database_url: str = os.getenv(
        "DATABASE_URL", "postgresql://sentinel:sentinel@localhost:5433/sentinelstream")
    model_path: Path = BASE / "artifacts" / "model.json"
    meta_path: Path = BASE / "artifacts" / "metadata.json"

    stream: str = "txn:events"
    dlq_stream: str = "txn:dlq"
    group: str = "scorers"
    consumer: str = os.getenv("CONSUMER_NAME", f"worker-{os.getpid()}")

    review_score: float = _f("REVIEW_SCORE", 0.5)   # >= this -> "review"; >= model threshold -> "decline"
    batch_size: int = _i("BATCH_SIZE", 100)
    block_ms: int = 1000
    max_retries: int = 3
    claim_idle_ms: int = 5000

    psi_window_min: int = _i("PSI_WINDOW_MIN", 5)
    psi_min_samples: int = _i("PSI_MIN_SAMPLES", 200)
    psi_snapshot_secs: int = 15

    cors_origins: tuple = ("http://localhost:3010", "http://127.0.0.1:3010")


settings = Settings()