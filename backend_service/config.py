"""Configuration settings for the Flask Backend Service.

Reads environment variables and establishes constants for MongoDB connections,
server port, snapshot uploads directory, and Haversine spatial clustering.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Set

from dotenv import load_dotenv

# Search for .env in current directory and repo root
_env_path = Path(__file__).resolve().parent.parent / ".env"
if _env_path.exists():
    load_dotenv(dotenv_path=_env_path)
else:
    load_dotenv()


@dataclass(frozen=True)
class BackendConfig:
    """Backend server configuration."""

    # Server binding
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "5000"))
    DEBUG: bool = os.getenv("FLASK_DEBUG", "false").strip().lower() in ("true", "1")

    # Database
    MONGO_URI: str = os.getenv(
        "MONGO_URI", "mongodb://localhost:27017/pothole_detection"
    )
    MONGO_DB_NAME: str = os.getenv("MONGO_DB_NAME", "pothole_detection")
    MONGO_COLLECTION_NAME: str = "potholes"
    MONGO_TIMEOUT_MS: int = int(os.getenv("MONGO_TIMEOUT_MS", "2500"))

    # File uploads directory
    UPLOAD_FOLDER: Path = (
        Path(__file__).resolve().parent / "uploads"
    )

    # Spatial clustering threshold (Haversine 5 meters)
    CLUSTER_RADIUS_METERS: float = 5.0

    # Domain validation constraints
    ALLOWED_STATUSES: Set[str] = frozenset({"reported", "in-progress", "repaired"})
    ALLOWED_SEVERITIES: Set[str] = frozenset({"low", "medium", "high"})


config = BackendConfig()

# Ensure uploads directory exists on disk
config.UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)
