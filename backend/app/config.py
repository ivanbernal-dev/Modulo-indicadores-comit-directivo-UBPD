from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    db_path: Path
    host: str
    port: int
    cors_origin: str
    session_hours: int


def load_settings() -> Settings:
    backend_root = Path(__file__).resolve().parents[1]
    configured_path = os.getenv("UBPD_DB_PATH")
    db_path = Path(configured_path) if configured_path else backend_root / "data" / "ubpd_indicadores.db"
    if not db_path.is_absolute():
        db_path = (backend_root / db_path).resolve()
    return Settings(
        db_path=db_path,
        host=os.getenv("UBPD_HOST", "127.0.0.1"),
        port=int(os.getenv("UBPD_PORT", "8000")),
        cors_origin=os.getenv("UBPD_CORS_ORIGIN", "http://127.0.0.1:4173"),
        session_hours=int(os.getenv("UBPD_SESSION_HOURS", "8")),
    )
