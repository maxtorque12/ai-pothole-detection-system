"""Configuration loader for the Edge Detection module.

Reads environment variables with sensible defaults and provides structured,
type-annotated access to camera streams, GPS telemetry endpoints,
YOLO model parameters, defect classification thresholds, and backend routes.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Tuple

from dotenv import load_dotenv

# Search for .env in current working directory and repo root
_env_path = Path(__file__).resolve().parent.parent / ".env"
if _env_path.exists():
    load_dotenv(dotenv_path=_env_path)
else:
    load_dotenv()


@dataclass(frozen=True)
class EdgeConfig:
    """Immutable edge detection runtime configuration."""

    # Telemetry Endpoints (Smartphone IP Webcam)
    PHONE_STREAM_URL: str = os.getenv(
        "PHONE_STREAM_URL", "http://192.168.1.100:8080/video"
    )
    PHONE_GPS_URL: str = os.getenv(
        "PHONE_GPS_URL", "http://192.168.1.100:8080/sensors.json"
    )

    # Backend Ingestion API Endpoint
    BACKEND_API_URL: str = os.getenv(
        "BACKEND_API_URL", "http://127.0.0.1:5000/api/v1/potholes"
    )

    # Fallback Coordinates (Mayur Vihar Phase 2, East Delhi)
    MOCK_COORDINATES: Tuple[float, float] = (28.6186, 77.3013)
    GPS_POLL_INTERVAL: float = float(os.getenv("GPS_POLL_INTERVAL", "1.0"))
    GPS_REQUEST_TIMEOUT: float = float(os.getenv("GPS_REQUEST_TIMEOUT", "2.0"))

    # Local Hardware & Model
    EDGE_DEVICE: str = os.getenv("EDGE_DEVICE", "0")
    MODEL_PATH: str = os.getenv("MODEL_PATH", "yolov8n.pt")
    CONFIDENCE_THRESHOLD: float = float(os.getenv("CONFIDENCE_THRESHOLD", "0.35"))

    # Local Webcam Fallback
    USE_WEBCAM: bool = os.getenv("USE_WEBCAM", "false").strip().lower() in (
        "true",
        "1",
        "yes",
    )
    WEBCAM_INDEX: int = int(os.getenv("WEBCAM_INDEX", "0"))

    # Severity Boundaries (Bounding Box Area / Frame Area)
    # Low: < 2% of frame
    # Medium: 2% - 6% of frame
    # High: > 6% of frame
    LOW_SEVERITY_MAX_RATIO: float = 0.02
    MEDIUM_SEVERITY_MAX_RATIO: float = 0.06

    # Operational Parameters
    ALERT_COOLDOWN_SECONDS: float = float(os.getenv("ALERT_COOLDOWN_SECONDS", "3.0"))
    DISPATCH_COOLDOWN_SECONDS: float = float(
        os.getenv("DISPATCH_COOLDOWN_SECONDS", "2.0")
    )
    HTTP_POST_TIMEOUT: float = float(os.getenv("HTTP_POST_TIMEOUT", "3.0"))

    # Stream Buffer & Performance
    FRAME_QUEUE_SIZE: int = 1
    MAX_CONNECT_RETRIES: int = 3
    RECONNECT_DELAY_SECONDS: float = 2.0


# Default shared singleton instance
config = EdgeConfig()
